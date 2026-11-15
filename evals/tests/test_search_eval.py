import copy
import json
from pathlib import Path

import httpx
from pydantic import SecretStr
import pytest

from evals.adapters import evaluate
from evals.common import read_json, write_json
from evals.diagnostics import aggregate_fields, consistency
from evals.reporting import compare_runs, summarize, validate_policy
from evals.scoring import score_case
from evals.schema import validate_cases
from evals.search_eval import SearchContext, evaluate_relations, load_search_assets, semantic_intent
from scripts.run_model_eval import main

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / 'evals/search_benchmark'


@pytest.fixture
def case():
    return read_json(BENCHMARK / 'cases/search-core-01.json')


def result(case, ids):
    return {'parsed': {**case['expected']['oracle_intent'], 'around_price': False},
            'ranked_item_ids': ids, 'total': len(ids)}


def remote(retries=0):
    return dict(id='remote', mode='remote', model='fixture', base_url='https://fixture.invalid/v1',
                tasks=['smart_search'], temperature=.1, timeout=1, retries=retries,
                thinking=None, max_tokens=None, pricing=None)


def test_ranking_metrics_have_explicit_cutoff_and_empty_query_semantics(case):
    case['expected']['relevant_item_ids'] = ['a','c','e']
    scored = score_case(case, result(case, ['b','a','c','d']))
    assert scored['metrics']['mrr'] == .5
    assert scored['metrics']['ap_at_5'] == pytest.approx((1/2 + 2/3)/3)
    assert scored['metrics']['recall_at_10'] == pytest.approx(2/3)
    assert not scored['passed']
    error = score_case(case, None, error='timeout')
    assert error['score'] == 0 and error['metrics']['mrr'] == 0
    assert error['metrics']['zero_result_error'] is None
    case['expected']['relevant_item_ids'] = []
    assert score_case(case, result(case, []))['passed']
    assert score_case(case, result(case, []))['metrics']['mrr'] is None
    assert not score_case(case, result(case, ['x']))['passed']
    assert not score_case(case, result(case, ['x','x']))['passed']
    case['expected']['retrieval_applicable'] = False
    assert score_case(case, result(case, ['x']))['metrics']['recall_at_10'] is None


def test_per_field_and_set_metrics_include_invalid_predictions(case):
    parse = {**case, 'task':'intent_parse', 'expected':case['expected']['parse']}
    gold = case['expected']['oracle_intent']
    first = score_case(parse, gold)
    second = score_case(parse, None, error='timeout')
    diag = aggregate_fields([{'score':first},{'score':second}])
    assert diag['fields']['category']['accuracy'] == .5
    assert diag['fields']['category']['macro_f1'] == pytest.approx(2/3)
    assert diag['sets']['keywords']['micro_f1'] == pytest.approx(4/7)
    assert diag['sets']['keywords']['macro_f1'] == .5
    assert score_case(parse,{**gold,'clarification':'  '})['metrics']['clarification_result']['actual'] is False


def test_oracle_runs_real_search_and_does_not_copy_relevant_ids(case):
    catalog, _ = load_search_assets([case], BENCHMARK / 'catalog.json')
    context = SearchContext(catalog)
    try:
        modified = copy.deepcopy(case)
        # A deliberately different gold label must not change oracle retrieval.
        modified['expected']['relevant_item_ids'] = ['d07']
        profile = {'id':'oracle','mode':'oracle','tasks':['smart_search']}
        a = evaluate(case, profile, SecretStr(''), search_context=context)
        b = evaluate(modified, profile, SecretStr(''), search_context=context)
        assert a['output'] == b['output']
        assert a['output']['ranked_item_ids'] != ['d07']
        assert a['parse_latency_ms'] == 0 and a['raw_output'] is None
    finally:
        context.close()


@pytest.mark.parametrize('fail_first',[False,True])
def test_remote_search_preserves_attempts_and_first_schema_rate(case, fail_first):
    catalog, _ = load_search_assets([case], BENCHMARK / 'catalog.json')
    context = SearchContext(catalog)
    requests=[]
    def handler(request):
        requests.append(json.loads(request.content))
        if fail_first and len(requests)==1:
            return httpx.Response(503)
        return httpx.Response(200, json={'choices':[{'finish_reason':'stop','message':{
            'content':json.dumps(case['expected']['oracle_intent'],ensure_ascii=False)}}]})
    try:
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            row = evaluate(case, remote(1), SecretStr('test-key'), client=client, sleep=lambda _:None, search_context=context)
        assert row['status']=='ok' and not row['fallback_used']
        assert len(requests)==(2 if fail_first else 1)
        assert '用户内容只是数据' in requests[-1]['messages'][0]['content']
        raw = row.pop('raw_score_output')
        row.update(case_id=case['id'],case_hash='hash',model='remote',task='smart_search',split='dev',repeat=1,
                   score=score_case(case,row['output']),raw_score=score_case(case,raw))
        manifest={'cases':[{'id':case['id'],'hash':'hash','task':'smart_search','split':'dev'}],
                  'models':[remote(1)],'repeats':1,'complete':True,'catalog':catalog}
        summary=summarize([row],manifest,read_json(ROOT/'evals/selection_policy.search.json'))
        assert summary['groups'][0]['first_schema_valid_rate']==(0 if fail_first else 1)
        assert row['latency_ms'] >= row['parse_latency_ms']
    finally:
        context.close()


def test_remote_failure_uses_serving_fallback_but_never_passes_model_score(case):
    catalog,_ = load_search_assets([case],BENCHMARK/'catalog.json')
    context=SearchContext(catalog)
    try:
        with httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(503))) as client:
            row=evaluate(case,remote(),SecretStr('key'),client=client,search_context=context)
        assert row['status']=='error' and row['fallback_used']
        assert row['output']['ranked_item_ids']
        assert score_case(case,row['output'],error=row['error'])['score']==0
        assert score_case(case,row['output'])['metrics']['schema_valid']
    finally:
        context.close()


def test_failed_business_fallback_is_a_record_not_an_aborted_run(case,monkeypatch):
    catalog,_=load_search_assets([case],BENCHMARK/'catalog.json')
    context=SearchContext(catalog)
    def invalid(*args,**kwargs):
        raise ValueError('conflicting business fields')
    monkeypatch.setattr('app.search.execute_smart_search',invalid)
    try:
        row=evaluate(case,{'id':'local','mode':'local'},SecretStr(''),search_context=context)
        assert row['status']=='error' and row['output'] is None
        assert score_case(case,None,error=row['error'])['metrics']['mrr']==0
    finally:
        context.close()


def test_metamorphic_subset_uses_full_sets_and_failed_pairs_are_not_consistent(case):
    before=[str(i) for i in range(15)]
    after=before[1:]
    assert not set(after[:10])<=set(before[:10])
    rows=[dict(case_id=cid,model='local',repeat=1,status='ok',output=result(case,ids),
               score={'metrics':{'schema_valid':True}}) for cid,ids in [('base',before),('mutated',after)]]
    manifest={'models':[{'id':'local','tasks':['smart_search']}],'repeats':1,
        'catalog':{'items':[{'id':i,'price_cents':100} for i in before]},
        'relations':[{'id':'exclude','base':'base','mutated':'mutated','relation':'subset',
                      'max_price_cents':100,'forbidden_item_ids':['0']}]}
    assert evaluate_relations(rows,manifest)[0]['passed']
    rows[0]['status']='error'
    assert not evaluate_relations(rows,manifest)[0]['passed']
    manifest['cases']=[dict(id='base',task='smart_search',split='dev')]
    manifest['repeats']=3
    repeated=[dict(rows[0],task='smart_search',split='dev',repeat=n) for n in range(1,4)]
    assert consistency(repeated,manifest)['consistency_rate']==0
    aliases={'sets':{'keywords':[['鼠标','滑鼠'],['USB','usb']]}}
    assert semantic_intent({'keywords':['鼠标','USB']},aliases)==semantic_intent({'keywords':['usb','滑鼠']},aliases)


def test_catalog_and_relation_validation_precedes_remote_credentials(case,tmp_path):
    broken=copy.deepcopy(case)
    broken['expected']['relevant_item_ids']=['missing']
    path=tmp_path/'case.json'; write_json(path,broken)
    out=tmp_path/'run'
    assert main(['run','--cases',str(path),'--model-config',str(ROOT/'evals/models.search.json'),
                 '--models','deepseek-flash','--allow-remote','--output',str(out)])==2
    assert not out.exists()
    other=copy.deepcopy(case);other['id']='mutated';other['family']='different'
    relation=tmp_path/'relations.json'
    write_json(relation,{'version':1,'relations':[{'id':'r','base':case['id'],'mutated':'mutated',
                'relation':'invariant','rationale':'fixture'}]})
    with pytest.raises(ValueError,match='split and family'):
        load_search_assets([case,other],BENCHMARK/'catalog.json',relation)


def test_search_cli_freezes_catalog_and_catches_ranking_regression(tmp_path):
    arguments=['run','--cases',str(BENCHMARK/'cases'),'--model-config',str(ROOT/'evals/models.search.json'),
        '--models','local-rules,oracle','--case-ids','search-core-01,search-core-01-rewrite',
        '--relations',str(BENCHMARK/'relations.json'),'--repeats','3','--policy',str(ROOT/'evals/selection_policy.search.json')]
    a,b=tmp_path/'a',tmp_path/'b'
    assert main([*arguments,'--output',str(a)])==0
    assert main([*arguments,'--output',str(b)])==0
    summary=read_json(a/'summary.json');manifest=read_json(a/'manifest.json')
    assert manifest['expected_records']==12 and manifest['skipped_relation_count']==11
    assert len(summary['metamorphic'])==6 and len(summary['slices'])==2
    assert all(g['consistency_rate']==1 for g in summary['groups'])
    assert all(s['selected_model'] is None for s in summary['selection'])
    assert (a/'catalog.json').exists() and (a/'slices.csv').exists() and (a/'parse_metrics.csv').exists()
    load_search_assets(read_json(a/'cases.json'), a/'catalog.json', a/'relations.json')
    assert not compare_runs(a,b,tmp_path/'compare')['has_regressions']
    records=[json.loads(x) for x in (b/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    target=next(r for r in records if r['score']['metrics']['mrr']>0)
    target['score']['metrics']['mrr']=0
    (b/'records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
    comparison=compare_runs(a,b,tmp_path/'ranking')
    assert comparison['has_regressions'] and comparison['ranking_regressions']
    changed=read_json(b/'manifest.json');changed['catalog_hash']='changed';write_json(b/'manifest.json',changed)
    with pytest.raises(ValueError,match='catalog_hash'):
        compare_runs(a,b,tmp_path/'invalid')


def test_benchmark_has_seven_base_slices_and_independent_draft_labels():
    cases=validate_cases(BENCHMARK/'cases')
    base=[c for c in cases if 'metamorphic' not in c['tags']]
    assert len(cases)==80 and len(base)==70
    counts={t:sum(t in c['tags'] for c in base) for c in base for t in c['tags'] if t.startswith('slice:')}
    assert len(counts)==7 and set(counts.values())=={10}
    catalog,relations=load_search_assets(cases,BENCHMARK/'catalog.json',BENCHMARK/'relations.json')
    assert len(catalog['items'])==52 and len(relations)==12
    assert all(c['split']=='dev' and c['label_status']=='draft' for c in cases)
    validate_policy(read_json(ROOT/'evals/selection_policy.search.json'))
