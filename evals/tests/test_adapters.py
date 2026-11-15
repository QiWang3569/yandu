import json

import httpx
from pydantic import SecretStr
import pytest

from evals.adapters import evaluate
from evals.providers import Profile, load_profiles, resolve_profile, usage_cost, usage_metadata


def profile(**changes):
    value = {'id': 'fake', 'mode': 'remote', 'model': 'fixture-model', 'base_url': 'https://fixture.invalid/v1',
             'tasks': ['intent_parse', 'item_parse', 'wanted_parse', 'candidate_review'],
             'temperature': 0.1, 'timeout': 2, 'retries': 0, 'max_tokens': None, 'thinking': None, 'pricing': None}
    value.update(changes)
    return value


def case(task='intent_parse'):
    return {'task': task, 'input': {'text': '医学部收200元以内的无线耳机'}}


def answer(value):
    return httpx.Response(200, json={'model': 'fixture-model', 'choices': [{'finish_reason': 'stop',
        'message': {'content': json.dumps(value, ensure_ascii=False)}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 30, 'total_tokens': 130}})


def test_reuses_production_prompt_and_records_usage():
    def handler(request):
        body = json.loads(request.content)
        assert '不擅自增加用户未说的条件' in body['messages'][0]['content']
        assert body['model'] == 'fixture-model'
        assert '医学部' in body['messages'][1]['content']
        return answer({'category': '数码与影音', 'max_price': 200, 'campus': '医学部', 'keywords': ['耳机', '无线']})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = evaluate(case(), profile(), SecretStr('test-secret'), client=client)
    assert result['status'] == 'ok'
    assert result['raw_output']['max_price'] == 200
    assert result['usage']['total_tokens'] == 130
    assert result['cost_cny'] is None
    assert result['prompt_hash']
    assert 'test-secret' not in json.dumps(result)


@pytest.mark.parametrize('task', ['item_parse', 'wanted_parse'])
def test_fallback_is_recorded_as_model_error(task):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        result = evaluate(case(task), profile(), SecretStr('key'), client=client)
    assert result['status'] == 'error' and result['error'] == 'http_503'
    assert result['fallback_used'] and result['output'] is not None
    assert result['cost_cny'] is None


def test_schema_failure_keeps_raw_and_fallback():
    with httpx.Client(transport=httpx.MockTransport(lambda _: answer({'category': '不存在的分类'}))) as client:
        result = evaluate(case('item_parse'), profile(), SecretStr('key'), client=client)
    assert result['error'] == 'schema_error'
    assert result['raw_output']['category'] == '不存在的分类'
    assert result['fallback_used']


def test_retry_failure_count_and_unknown_cost_are_retained():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429) if len(calls) == 1 else answer({'keywords': ['耳机']})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = evaluate(case(), profile(retries=1), SecretStr('key'), client=client, sleep=lambda _: None)
    assert result['status'] == 'ok' and len(result['attempts']) == 2
    assert result['attempts'][0]['error'] == 'http_429'
    assert result['usage'] is None and result['cost_cny'] is None


def test_production_guard_does_not_overwrite_raw_verdict():
    review = {'task': 'candidate_review', 'input': {'intent': {'keywords': ['耳机', '无线'],
        'excluded_keywords': [], 'preferences': []}, 'items': [{'id': 'one', 'title': '耳机',
        'description': '功能正常', 'tags': []}]}}
    raw = {'assessments': [{'item_id': 'one', 'verdict': 'MATCH',
        'evidence': [{'criterion': '耳机', 'quote': '耳机'}], 'questions': []}]}
    with httpx.Client(transport=httpx.MockTransport(lambda _: answer(raw))) as client:
        result = evaluate(review, profile(), SecretStr('key'), client=client)
    assert result['status'] == 'ok'
    assert result['raw_output']['assessments'][0]['verdict'] == 'MATCH'
    assert result['output']['assessments'][0]['verdict'] == 'UNCERTAIN'


def test_wanted_raw_is_projected_from_intent_without_second_call():
    raw = {'category': '数码与影音', 'max_price': 200, 'campus': '医学部', 'keywords': ['耳机']}
    with httpx.Client(transport=httpx.MockTransport(lambda _: answer(raw))) as client:
        result = evaluate(case('wanted_parse'), profile(), SecretStr('key'), client=client)
    assert len(result['attempts']) == 1
    assert result['raw_output']['max_price'] == 200
    assert result['raw_score_output']['budget'] == '200'


def test_cost_handles_cached_and_unknown_tokens():
    price = {'input_per_million_cny': 2, 'output_per_million_cny': 4}
    assert usage_cost({'prompt_tokens': 100, 'completion_tokens': 25}, price) == pytest.approx(0.0003)
    assert usage_cost(None, price) is None
    assert usage_cost({'prompt_tokens': True, 'completion_tokens': 1}, price) is None
    assert usage_cost({'prompt_tokens': 100, 'completion_tokens': 25,
                       'prompt_tokens_details': {'cached_tokens': 50}}, price) is None


def test_invalid_usage_does_not_corrupt_result_serialization():
    assert usage_metadata({'prompt_tokens': float('nan')}) is None
    assert usage_metadata({'prompt_tokens': 1, 'arbitrary_provider_metadata': float('nan')}) == {'prompt_tokens': 1}


def test_overflowing_json_number_is_recorded_without_stopping_run():
    def handler(_):
        return httpx.Response(200, json={'choices': [{'message': {
            'content': '{"max_price":1e999,"keywords":["耳机"]}'}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = evaluate(case(), profile(), SecretStr('key'), client=client)
    assert result['error'] == 'invalid_json_response'
    assert result['raw_output'] is None
    assert '1e999' in result['raw_content']
    json.dumps(result, allow_nan=False)


def test_secret_is_not_in_resolved_profile(monkeypatch):
    monkeypatch.setenv('EVAL_TEST_KEY', 'dont-print-this')
    value = Profile(id='fixture', mode='remote', tasks=['intent_parse'],
                    model='fixture', base_url='https://fixture.invalid/v1', api_key_env='EVAL_TEST_KEY')
    public, key = resolve_profile(value)
    assert key.get_secret_value() == 'dont-print-this'
    assert 'dont-print-this' not in json.dumps(public)


def test_invalid_or_inline_credentials_are_rejected():
    with pytest.raises(ValueError):
        Profile(id='fixture', mode='remote', tasks=['intent_parse'], model='x',
                base_url='https://fixture.invalid', api_key='inline-secret')
    with pytest.raises(ValueError):
        Profile(id='fixture', mode='local', tasks=['candidate_review'])
