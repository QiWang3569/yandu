"""Evaluate independent full-catalog LLM rankings on the frozen 28-query holdout."""
import argparse
import concurrent.futures
import json
import os
import random
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
PROMPT = ('根据买家的整句查询，从给定商品中选出符合需求的商品，按推荐顺序最多返回三件。'
          '区分主体与配件、必须项、排除项和偏好。没有合适商品返回空数组。'
          '只使用提供的商品信息，只返回 JSON 对象 {"ranked":["商品编号"]}。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--m3e-top5', action='store_true')
    parser.add_argument('--latency-trial', action='store_true', help='Compare three rankers on identical priced M3E candidates')
    parser.add_argument('--nano-check', action='store_true', help='Test stricter inclusion criteria for the fast ranker')
    args = parser.parse_args()
    prompt = PROMPT
    if args.nano_check:
        args.latency_trial = True
        prompt += ('逐件核对实际卖的东西、必需属性和排除项，兼容或附带不等于出售用户要的主体。'
                   '商品说明中否认某项功能表示它没有该功能。可只选一件，不凑数。')
    if args.latency_trial:
        args.m3e_top5 = True
    candidates = None
    if args.m3e_top5:
        candidates = json.loads((HERE/'server.json').read_text(encoding='utf8'))['rows']['holdout']
    arms = ['with_price'] if args.m3e_top5 else ['text','with_price']
    data = json.loads((HERE/'holdout.json').read_text(encoding='utf8'))
    config = json.loads((HERE.parents[1]/'models.search.openlux.json').read_text(encoding='utf8'))
    model = next(m for m in config['models'] if m['id']=='deepseek-flash')
    if args.latency_trial:
        arms = [model['model'], 'gpt-4.1-nano', 'gemini-2.5-flash-lite']
    if args.nano_check:
        arms = ['gpt-4.1-nano']
    auth = {'Authorization': 'Bearer '+os.environ[model['api_key_env']]}
    def run(job):
        arm, index, query = job
        items = data['items'][:]
        random.Random(7000+index).shuffle(items)
        if candidates is not None:
            ids = candidates[query['id']]['ranked']
            items = [item for item in items if item['id'] in ids]
            assert len(items) == len(set(ids)) == 5
        codes = {f'P{i+1:02d}':item['id'] for i,item in enumerate(items)}
        catalog = []
        for code,item in zip(codes,items):
            record = dict(id=code,title=item['title'],description=item['description'],tags=item['tags'])
            if arm=='with_price' or args.latency_trial:
                record['price_yuan'] = item['price_cents']/100
            catalog.append(record)
        payload = dict(model=model['model'],temperature=model['temperature'],thinking={'type':'disabled'},
                       max_tokens=200,response_format={'type':'json_object'},
                       messages=[{'role':'system','content':prompt},{'role':'user','content':json.dumps(
                           dict(query=query['query'],catalog=catalog),ensure_ascii=False)}])
        if args.latency_trial:
            payload['model'] = arm
            if arm != model['model']:
                payload.pop('thinking')
        result = dict(arm=arm,id=query['id'],query=query['query'],ranked=None,attempts=[])
        if candidates is not None:
            result['retrieved'] = candidates[query['id']]['ranked']
        call_start = time.monotonic()
        for attempt in range(2):
            start=time.monotonic()
            error=None
            retry=False
            try:
                response=client.post(model['base_url']+'/chat/completions',json=payload)
                response.raise_for_status()
                body=response.json()
                choice=body['choices'][0]
                out=json.loads(choice['message']['content'])['ranked']
                if (choice['finish_reason']!='stop' or not isinstance(out,list) or len(out)>3
                    or not all(isinstance(k,str) and k in codes for k in out) or len(set(out))!=len(out)):
                    raise ValueError('invalid list')
                result['ranked']=[codes[k] for k in out]
                result['usage']=body.get('usage')
            except httpx.TransportError as exc:
                error=type(exc).__name__
                retry=True
            except httpx.HTTPStatusError as exc:
                status=exc.response.status_code
                error=f'http_{status}'
                retry=status in (408,429) or status>=500
            except (ValueError,TypeError,KeyError,IndexError):
                error='invalid_output'
            result['attempts'].append(dict(error=error,seconds=round(time.monotonic()-start,3)))
            if not retry:break
            if attempt==0:time.sleep(1)
        result['call_seconds'] = round(time.monotonic()-call_start,3)
        return result
    jobs=[(arm,i,q) for i,q in enumerate(data['queries']) for arm in arms]
    random.Random(104).shuffle(jobs)
    with httpx.Client(headers=auth,timeout=35) as client, concurrent.futures.ThreadPoolExecutor(3) as pool:
        rows=list(pool.map(run,jobs))
    gold={q['id']:q['gold'] for q in data['queries']}
    titles={i['id']:i['title'] for i in data['items']}
    summary={}
    for arm in arms:
        chosen=[r for r in rows if r['arm']==arm]
        for r in chosen:
            r['gold']=gold[r['id']]
            r['expected_titles']=[titles[k] for k in r['gold']]
            r['returned_titles']=[titles[k] for k in r['ranked']] if r['ranked'] is not None else None
        summary[arm]=dict(top1=sum(bool(set((r['ranked'] or [])[:1]) & set(r['gold'])) for r in chosen),
                          hit3=sum(bool(set(r['ranked'] or []) & set(r['gold'])) for r in chosen),
                          empty_ok=sum(r['ranked']==[] and not r['gold'] for r in chosen),
                          errors=sum(r['ranked'] is None for r in chosen),
                          exact=sum(r['ranked'] is not None and set(r['ranked'])==set(r['gold']) for r in chosen))
    result=dict(model=model['model'],platform='OpenLux',prompt=prompt,summary=summary,records=rows)
    output = 'm3e-llm-ranking.json' if args.m3e_top5 else 'llm-ranking.json'
    if args.latency_trial:
        result['model'] = arms
        output = 'm3e-latency-trial.json'
    if args.nano_check:
        output = 'm3e-nano-check.json'
    (HERE/output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(summary)


if __name__=='__main__':
    main()
