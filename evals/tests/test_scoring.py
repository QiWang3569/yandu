import json
from decimal import Decimal

import pytest

from evals.schema import Case, validate_cases
from evals.scoring import score_case


def parse_case(**changes):
    case = {'id': 'mouse-1', 'task': 'intent_parse', 'enabled': True,
            'split': 'dev', 'family': 'mouse-basic', 'tags': ['negation'],
            'source': 'synthetic', 'rationale': 'Separate hard features from preferences.',
            'label_status': 'reviewed', 'input': {'text': '万柳300以内无线鼠标，最好静音'},
            'expected': {'fields': {'max_price': 300, 'campus': '万柳学区'},
                         'sets': {'keywords': [['鼠标', 'mouse'], ['无线']], 'excluded_keywords': [],
                                  'preferences': [['静音']]}}}
    case.update(changes)
    return case


def output(**changes):
    value = {'max_price': 300, 'campus': '万柳学区', 'keywords': ['鼠标', '无线'],
             'excluded_keywords': [], 'preferences': ['静音']}
    value.update(changes)
    return value


def review_case():
    return parse_case(task='candidate_review', input={
        'intent': {'keywords': ['鼠标'], 'excluded_keywords': [], 'preferences': ['静音']},
        'items': [{'id': 'one', 'title': '无线鼠标', 'description': '静音无线鼠标，功能正常。',
                   'tags': ['鼠标'], 'price_cents': 20000, 'campus': '万柳学区', 'condition_grade': '95新'},
                  {'id': 'two', 'title': '机械键盘', 'description': '这是一把机械键盘。',
                   'tags': ['键盘'], 'price_cents': 20000, 'campus': '万柳学区', 'condition_grade': '95新'}]},
        expected={'verdicts': {'one': 'MATCH', 'two': 'NO_MATCH'}})


def reviews():
    return [{'item_id': 'one', 'verdict': 'MATCH', 'evidence': [{'criterion': '鼠标', 'quote': '无线鼠标'}], 'questions': []},
            {'item_id': 'two', 'verdict': 'NO_MATCH', 'evidence': [{'criterion': '鼠标', 'quote': '机械键盘'}], 'questions': []}]


def test_case_and_exact_alias_scoring():
    case = Case.model_validate(parse_case()).model_dump()
    result = score_case(case, output(keywords=[' MOUSE ', '无线']))
    assert result['passed'] and result['score'] == 1
    assert result['metrics']['schema_valid']
    result = score_case(case, output(keywords=['静音鼠标', '无线']))
    assert not result['passed']
    assert result['metrics']['set_precision']['keywords'] == 0.5
    assert result['metrics']['set_recall']['keywords'] == 0.5


def test_extra_and_missing_terms_each_reduce_score():
    case = parse_case()
    missing = score_case(case, output(keywords=['鼠标']))
    extra = score_case(case, output(keywords=['鼠标', '无线', '游戏']))
    assert not missing['passed'] and 0 < missing['score'] < 1
    assert not extra['passed'] and 0 < extra['score'] < 1
    assert any(c['actual'] == {'missing': True} for c in missing['checks'])
    assert any(c['field'].startswith('keywords.extra') for c in extra['checks'])


def test_execution_error_keeps_failed_case_in_denominator():
    result = score_case(parse_case(), output(), error='timeout')
    assert result['score'] == 0 and not result['passed']
    assert result['metrics']['check_count'] == 1
    assert result['metrics']['passed_checks'] == 0
    reviewed = score_case(review_case(), None, error='timeout')
    assert reviewed['metrics']['non_match_count'] == 1
    assert all(pair['actual'] is None for pair in reviewed['metrics']['verdict_pairs'])


@pytest.mark.parametrize('bad', [None, [], {'keywords': '鼠标'}, {'max_price': True},
                                 {'max_price': float('inf')}, {'unknown': 1},
                                 {'keywords': ['鼠标', '鼠标']}])
def test_bad_outputs_are_zero_not_exceptions(bad):
    result = score_case(parse_case(), bad)
    assert result['score'] == 0 and not result['metrics']['schema_valid']


def test_missing_null_is_not_counted_as_present_null():
    case = parse_case(expected={'fields': {'category': None}})
    assert score_case(case, {'category': None})['passed']
    assert not score_case(case, {})['passed']


def test_decimal_json_output_compares_numerically():
    assert score_case(parse_case(), output(max_price='300.00'))['passed']
    result = score_case(parse_case(), output(max_price=Decimal('300.00')))
    assert result['passed']
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('patch', [
    {'enabled': 'true'}, {'task': 'other'}, {'split': 'test'}, {'label_status': 'accepted'},
    {'expected': {}}, {'expected': {'fields': {'title': '鼠标'}}},
    {'expected': {'fields': {'max_price': '300'}}}, {'expected': {'fields': {'max_price': True}}},
    {'expected': {'fields': {'max_price': float('nan')}}},
    {'expected': {'fields': {'category': '其他'}}},
    {'expected': {'sets': {'keywords': [[]]}}},
    {'expected': {'sets': {'keywords': [['鼠标'], [' 鼠标 ']]}}},
    {'expected': {'sets': {'keywords': [['鼠标']], 'excluded_keywords': [['鼠标']]}}},
    {'expected': {'clarification': None}}, {'input': {'text': '短'}},
    {'input': {'text': '鼠标', 'extra': 1}}, {'extra': True},
])
def test_invalid_case_contracts_rejected(patch):
    with pytest.raises(ValueError):
        Case.model_validate(parse_case(**patch))


def test_loader_detects_duplicates_and_family_leakage(tmp_path):
    first = parse_case()
    second = parse_case()
    (tmp_path / 'a.json').write_text(json.dumps(first), encoding='utf-8')
    (tmp_path / 'b.json').write_text(json.dumps(second), encoding='utf-8')
    with pytest.raises(ValueError, match='duplicate case id'):
        validate_cases(tmp_path)
    second.update(id='mouse-2', split='holdout')
    (tmp_path / 'b.json').write_text(json.dumps(second), encoding='utf-8')
    with pytest.raises(ValueError, match='family leakage'):
        validate_cases(tmp_path)
    second['family'] = 'different-source'
    (tmp_path / 'b.json').write_text(json.dumps(second), encoding='utf-8')
    assert len(validate_cases(tmp_path)) == 2
    assert validate_cases(tmp_path / 'a.json')[0]['id'] == 'mouse-1'


def test_loader_rejects_duplicate_json_keys_and_nan(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text('{"id":"one","id":"two"}', encoding='utf-8')
    with pytest.raises(ValueError, match='duplicate JSON key'):
        validate_cases(path)
    path.write_text('{"x":NaN}', encoding='utf-8')
    with pytest.raises(ValueError, match='invalid JSON number'):
        validate_cases(path)


def test_review_gold_ids_must_be_unique_and_complete():
    case = review_case()
    Case.model_validate(case)
    case['input']['items'][1]['id'] = 'one'
    with pytest.raises(ValueError, match='unique'):
        Case.model_validate(case)
    case = review_case()
    del case['expected']['verdicts']['two']
    with pytest.raises(ValueError, match='exactly match'):
        Case.model_validate(case)


def test_review_verdicts_grounding_and_human_semantics_are_separate():
    result = score_case(review_case(), {'assessments': reviews()})
    assert result['passed']
    assert result['metrics']['evidence_valid']
    assert result['metrics']['grounded_evidence_rate'] == 1
    assert result['metrics']['requires_human_review']
    wrong = reviews()
    wrong[1] = {'item_id': 'two', 'verdict': 'MATCH',
                'evidence': [{'criterion': '鼠标', 'quote': '机械键盘'}], 'questions': []}
    result = score_case(review_case(), wrong)
    assert not result['passed']
    assert result['metrics']['false_match_count'] == 1
    assert result['metrics']['non_match_count'] == 1


@pytest.mark.parametrize('kind', ['unknown_id', 'duplicate_id', 'missing_id', 'bad_verdict', 'bad_type', 'extra_key'])
def test_bad_review_output_is_zero(kind):
    values = reviews()
    if kind == 'unknown_id': values[0]['item_id'] = 'other'
    elif kind == 'duplicate_id': values[1]['item_id'] = 'one'
    elif kind == 'missing_id': values.pop()
    elif kind == 'bad_verdict': values[0]['verdict'] = 'YES'
    elif kind == 'bad_type': values[0]['questions'] = 'why'
    elif kind == 'extra_key': values[0]['score'] = 1
    result = score_case(review_case(), values)
    assert result['score'] == 0 and not result['metrics']['schema_valid']
    assert len(result['metrics']['verdict_pairs']) == 2


@pytest.mark.parametrize('kind', ['invented_quote', 'unknown_criterion', 'missing_evidence', 'preference_rejection', 'missing_question'])
def test_invalid_evidence_rules_cannot_pass(kind):
    values = reviews()
    if kind == 'invented_quote': values[0]['evidence'][0]['quote'] = '品牌质量好'
    elif kind == 'unknown_criterion': values[0]['evidence'][0]['criterion'] = '品牌'
    elif kind == 'missing_evidence': values[0]['evidence'] = []
    elif kind == 'preference_rejection': values[1]['evidence'][0]['criterion'] = '静音'
    elif kind == 'missing_question': values[1]['verdict'] = 'UNCERTAIN'
    result = score_case(review_case(), values)
    assert not result['passed'] and not result['metrics']['evidence_valid']


def test_review_quote_cannot_be_spliced_across_fields():
    case = review_case()
    case['input']['items'][0].update(title='无线', description='鼠标，功能正常。', tags=[])
    result = score_case(case, reviews())
    assert not result['passed']
    assert result['metrics']['grounded_evidence_rate'] == 0.5
