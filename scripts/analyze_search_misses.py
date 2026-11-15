"""Replay recorded searches locally and explain missed products without new model calls."""
import argparse
from collections import Counter, defaultdict
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from evals.adapters import ParsedIntent  # Imports serving modules without loading .env.
from evals.common import read_json, write_json
from evals.search_eval import SearchContext
from app import search, services


def analyze(run, destination):
    manifest = read_json(run / 'manifest.json')
    if not manifest.get('complete'):
        raise ValueError('A completed run is required')
    from scripts.run_model_eval import implementation_hash
    if implementation_hash() != manifest['implementation_hash']:
        raise ValueError('Serving/scoring implementation changed; use the recorded source version for replay')
    cases = {c['id']: c for c in read_json(run / 'cases.json')}
    catalog = read_json(run / 'catalog.json')
    items = {i['id']: i for i in catalog['items']}
    rows = [json.loads(line) for line in (run / 'records.jsonl').read_text(encoding='utf-8').splitlines()]
    context = SearchContext(catalog)
    settings = SimpleNamespace(demo_mode=True)
    def replay(value, around):
        parsed = ParsedIntent.model_validate({k:v for k,v in value.items() if k != 'around_price'})
        results, _ = search.search_items_by_intent(context.session, parsed, settings,
                                                 around=around, size=len(items))
        return [item.id for item, _ in results]
    def display(i):
        v = items[i]
        return f"{v['title']}（¥{v['price_cents']/100:g}；{v['campus']}）"
    def blockers(i, value, around):
        item = items[i]
        p = ParsedIntent.model_validate({k:v for k,v in value.items() if k != 'around_price'})
        result = []
        if p.category and p.category != item['category']:
            result.append({'stage':'category', 'detail':f"查询分类={p.category}；商品分类={item['category']}"})
        if p.campus and p.campus != '不限校区' and item['campus'] not in {p.campus, '不限校区'}:
            result.append({'stage':'campus', 'detail':f"查询校区={p.campus}；商品校区={item['campus']}"})
        cap = search.price_cap_cents(search._spec_max_price_cents(p), around=around)
        if cap is not None and item['price_cents'] > cap:
            result.append({'stage':'price', 'detail':f"商品 ¥{item['price_cents']/100:g} > 实际价格上限 ¥{cap/100:g}"})
        if not services.condition_matches(item['condition_grade'], p.condition_grade):
            result.append({'stage':'condition', 'detail':f"要求成色={p.condition_grade}；商品成色={item['condition_grade']}"})
        text = services.item_text(item)
        excluded = [w for w in p.excluded_keywords if services.term_matches(
            w, text, ignore_negated=True, negation_prefix=services.EXCLUSION_NEGATION_PREFIX)]
        if excluded:
            result.append({'stage':'exclusion', 'detail':'触发排除词：'+ '；'.join(
                f'{w} → {services.normalize(w)}' for w in excluded)})
        matched, _ = services.keyword_coverage(p.keywords, text)
        if p.keywords and not matched:
            result.append({'stage':'keyword', 'detail':f'关键词 {p.keywords} 均未作为连续子串匹配到商品文本',
                           'normalized_keywords':[services.normalize(w) for w in p.keywords],
                           'normalized_item_text':services.normalize(text)})
        return result
    stats = defaultdict(Counter)
    records = []
    replay_count = 0
    try:
        for row in rows:
            if row['task'] != 'smart_search': continue
            c = cases[row['case_id']]
            expected = c['expected']['relevant_item_ids']
            if not expected or not c['expected']['retrieval_applicable']: continue
            s = stats[row['model']]
            s['positive_executions'] += 1
            if row['status'] != 'ok' or not row['score']['metrics']['schema_valid']:
                s['execution_or_schema_errors'] += 1
                continue
            s['successful_executions'] += 1
            actual = row['output']['ranked_item_ids']
            missing = sorted(set(expected)-set(actual))
            missing10 = sorted(set(expected)-set(actual[:10]))
            s['full_result_miss_executions'] += bool(missing)
            s['top10_miss_executions'] += bool(missing10)
            if not missing10 and not missing: continue
            value = row['output']['parsed']
            around = services.is_around_price(c['input']['text'])
            assert around == value['around_price']
            assert replay(value, around) == actual, (row['model'],row['case_id'],row['repeat'])
            replay_count += 1
            gold = c['expected']['oracle_intent']
            oracle_ids = replay(gold, around)
            oracle_row = next(x for x in rows if x['model']=='oracle' and x['case_id']==row['case_id'] and x['repeat']==row['repeat'])
            assert oracle_ids == oracle_row['output']['ranked_item_ids']
            differences = {k:{'expected':v,'actual':value.get(k)} for k,v in gold.items() if value.get(k)!=v}
            single = {}
            for field in differences:
                candidate = {**value, field:gold[field]}
                try: single[field] = replay(candidate, around)
                except ValueError: single[field] = None
            normalized_shoes = copy.deepcopy(gold)
            normalized_shoes['keywords'] = [w.replace('鞋子','鞋') for w in gold['keywords']]
            controls = {'gold_parse_same_search': oracle_ids,
                        'gold_parse_expected_around_price': replay(gold, c['expected']['around_price']),
                        'gold_parse_shoe_term_normalized': replay(normalized_shoes, around),
                        'single_field_replacements': single}
            findings=[]
            for i in missing:
                why = blockers(i,value,around)
                stages={b['stage'] for b in why}
                labels=[]
                if 'price' in stages:
                    if value.get('max_price') != gold['max_price']:
                        labels.append('解析：预算误提取')
                    elif around != c['expected']['around_price']:
                        labels.append('检索：约数识别与预标注约定不一致')
                if 'category' in stages: labels.append('解析：分类与商品库约定不一致')
                if 'campus' in stages or 'condition' in stages: labels.append('解析：校区或成色约束错误')
                if 'exclusion' in stages:
                    labels.append('检索：排除词同义归一化过度泛化' if '山地车' in value['excluded_keywords']
                                  else '排除约束待复核')
                if 'keyword' in stages:
                    if i not in oracle_ids and i in controls['gold_parse_shoe_term_normalized']:
                        labels.append('检索：鞋类词形未归一化')
                    if value['keywords'] != gold['keywords']:
                        labels.append('解析与检索接口：复合物品词未拆分' if row['model']!='local-rules'
                                      else '解析：物品词提取或清理错误')
                if not labels: labels.append('原因待复核')
                findings.append({'item_id':i,'product_name':display(i),'product':items[i],
                    'blocked_by':why,'causes':labels,'gold_parse_recovers':i in oracle_ids,
                    'single_fields_that_recover':[f for f,ids in single.items() if ids is not None and i in ids]})
            for i in missing10:
                if i in actual:
                    findings.append({'item_id':i,'product_name':display(i),'product':items[i],
                        'blocked_by':[], 'causes':['排序：解析遗漏物品约束导致宽泛召回'],
                        'actual_rank':actual.index(i)+1,
                        'gold_rank':oracle_ids.index(i)+1 if i in oracle_ids else None,
                        'gold_parse_recovers':i in oracle_ids[:10]})
            records.append({'model':row['model'],'case_id':row['case_id'],'repeat':row['repeat'],
                'query':c['input']['text'],'expected_item_ids':expected,'expected_product_names':[display(i) for i in expected],
                'actual_ranked_item_ids':actual,'actual_ranked_product_names':[display(i) for i in actual],
                'missing_item_ids':missing,'missing_product_names':[display(i) for i in missing],
                'missing_from_top10_ids':missing10,'missing_from_top10_names':[display(i) for i in missing10],
                'actual_parse':value,'expected_parse':gold,'parse_differences':differences,
                'expected_around_price':c['expected']['around_price'], 'findings':findings,'controls':controls})
    finally: context.close()
    cause_counts=Counter(label for r in records for label in {x for f in r['findings'] for x in f['causes']})
    result={'run_id':manifest['run_id'],'label_status':'draft','stats':dict(stats),'records':records,
            'replayed_records':replay_count,'cause_execution_counts':dict(cause_counts),
            'method':'No new API calls. Replay actual and gold parses through unchanged production search. '
                     'Field interventions are diagnostic only; frozen scores and labels remain unchanged.'}
    destination.mkdir(parents=True,exist_ok=True)
    write_json(destination/'missed_matches.json',result)
    lines=['# 漏匹配商品与原因清单','','商品名称后列价格和校区，区分同名商品。只分析结构有效且执行成功的正例查询；超时等错误单列。全部标签仍为 draft。',
        '',f'共离线重放 {replay_count} 条记录，实际解析重放结果与原始记录逐条一致，预标注解析重放与对应 Oracle 记录一致。没有重新调用模型或改写原实验评分。',
        '','| 模型 | 正例执行 | 执行／结构错误 | 成功执行 | 完整结果存在遗漏 | 前十名存在遗漏 |',
        '| --- | ---: | ---: | ---: | ---: | ---: |']
    for m,s in sorted(stats.items()):lines.append('| '+' | '.join([m,*[str(s[k]) for k in ['positive_executions','execution_or_schema_errors','successful_executions','full_result_miss_executions','top10_miss_executions']]])+' |')
    lines += ['','次数包含三次重复；前十名遗漏可能只是排序靠后。完整逐例字段干预和商品信息见[明细 JSON](missed_matches.json)，归因解释见[原因分析](missed_match_causes.md)。',
              '','## 完整结果中的漏匹配','','同一模型、用例的三轮合并展示；商品和原因取各轮并集，逐轮对应关系见后文明细。',
              '','| 模型 | 用例／查询 | 轮次 | 漏掉的商品 | 原因 |','| --- | --- | --- | --- | --- |']
    grouped=defaultdict(list)
    for r in records:
        if r['missing_item_ids']:grouped[r['model'],r['case_id']].append(r)
    def cell(v):return str(v).replace('|','\\|').replace('\n',' ')
    for (m,cid),rs in sorted(grouped.items()):
        products=sorted({name for r in rs for name in r['missing_product_names']})
        causes=sorted({x for r in rs for f in r['findings'] for x in f['causes']})
        lines.append('| '+' | '.join(map(cell,[m,cid+'：'+rs[0]['query'],','.join(str(r['repeat']) for r in rs),'；'.join(products),'；'.join(causes)]))+' |')
    lines+=['','## 逐条诊断','','单字段替换是保持其他解析字段不变的离线干预；替换全部解析可以恢复，不等于每个不同字段都是独立原因。']
    for r in records:
        lines += ['',f"### {r['model']} · {r['case_id']} · 第 {r['repeat']} 轮",'',r['query'],
                  '', '预期商品：'+'；'.join(r['expected_product_names']),
                  '', '实际排序：'+('；'.join(r['actual_ranked_product_names']) or '空结果')]
        for f in r['findings']:
            lines += ['', '**'+f['product_name']+'**：'+'；'.join(f['causes'])+'。']
            lines += ['- '+b['detail'] for b in f['blocked_by']]
            if 'actual_rank' in f:lines += [f"- 商品已召回，排第 {f['actual_rank']}；替换成预标注解析后排第 {f['gold_rank']}。"]
            else:lines += ['- 仅替换全部解析后'+('恢复该商品。' if f['gold_parse_recovers'] else '仍然遗漏该商品。')]
            if f.get('single_fields_that_recover'):lines+=['- 单独替换这些字段各自可以恢复：'+', '.join(f['single_fields_that_recover'])+'。']
        lines+=['','解析差异：','```json',json.dumps(r['parse_differences'],ensure_ascii=False,indent=2),'```']
    (destination/'missed_matches.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'records':len(records),'causes':dict(cause_counts)},ensure_ascii=False))


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    analyze(args.run,args.output)
