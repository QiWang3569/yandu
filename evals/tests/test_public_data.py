import hashlib
import json
from pathlib import Path

import httpx
from PIL import Image
from pydantic import SecretStr
import pytest

from backend.app.vision import SYSTEM_PROMPT, VisionDraft
from evals.adapters import evaluate
from evals.assets import prepare_assets
from evals.common import read_json, write_json
from evals.datasets import build_cases, sample_products, sample_text, write_sample
from evals.providers import Profile
from evals.schema import Case, validate_cases
from evals.scoring import score_case
from scripts.run_model_eval import main


def image_case(tmp_path):
    path = tmp_path / 'photo.jpg'
    Image.new('RGB', (12, 12), 'blue').save(path)
    return {'id': 'vision-fixture', 'task': 'vision_draft', 'enabled': True, 'split': 'dev',
            'family': 'fixture', 'tags': ['test'], 'source': 'test fixture', 'rationale': 'test only',
            'label_status': 'draft', 'input': {'images': [{'path': 'photo.jpg',
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}], 'note': ''},
            'expected': {'fields': {'status': 'ready', 'category': '数码与影音'},
                         'required_mentions': [['鼠标', '滑鼠']], 'forbidden_mentions': ['功能正常']}}


def good_output():
    return {'status': 'ready', 'title': '蓝色鼠标', 'category': '数码与影音',
            'description': '蓝色外壳的鼠标。', 'tags': ['鼠标', '蓝色'], 'uncertainties': []}


def remote_profile():
    return {'id': 'vision-test', 'mode': 'remote', 'model': 'fixture', 'base_url': 'https://fixture.invalid/v1',
            'tasks': ['vision_draft'], 'temperature': .1, 'timeout': 2, 'retries': 0,
            'max_tokens': None, 'thinking': None, 'pricing': None}


def test_vision_uses_production_prompt_multimodal_input_and_no_cache(tmp_path):
    case = image_case(tmp_path)
    images = prepare_assets([case], tmp_path)[case['id']]
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert body['messages'][0]['content'] == SYSTEM_PROMPT
        assert body['max_tokens'] == 1200
        content = body['messages'][1]['content']
        assert isinstance(content, list) and content[0]['type'] == 'text'
        assert content[1]['image_url']['url'].startswith('data:image/jpeg;base64,')
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps(good_output(), ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 20, 'completion_tokens': 10, 'total_tokens': 30}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        for _ in range(2):
            result = evaluate(case, remote_profile(), SecretStr('secret'), client=client, vision_images=images)
            assert result['status'] == 'ok' and not result['fallback_used']
            assert result['usage']['total_tokens'] == 30
            assert score_case(case, result['output'])['passed']
            assert 'base64' not in json.dumps(result)
    assert len(calls) == 2


def test_vision_failure_retains_error_without_local_fallback(tmp_path):
    case = image_case(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503))) as client:
        result = evaluate(case, remote_profile(), SecretStr('key'), client=client, vision_images=[b'fixture'])
    assert result['error'] == 'http_503' and result['output'] is None
    assert not result['fallback_used']


def test_vision_requires_complete_response_like_production(tmp_path):
    case = image_case(tmp_path)
    def handler(_):
        return httpx.Response(200, json={'choices': [{'finish_reason': 'content_filter',
            'message': {'content': json.dumps(good_output())}}]})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = evaluate(case, remote_profile(), SecretStr('key'), client=client, vision_images=[b'fixture'])
    assert result['error'] == 'incomplete_output' and result['output'] is None


def test_raw_nonready_hallucination_not_hidden_by_business_guard(tmp_path):
    case = image_case(tmp_path)
    case['expected'] = {'fields': {'status': 'unclear', 'category': None}, 'uncertainty_required': True}
    raw = {**good_output(), 'status': 'unclear', 'uncertainties': ['请补拍']}
    assert not score_case(case, raw)['passed']
    guarded = VisionDraft.model_validate(raw).model_dump()
    assert score_case(case, guarded)['passed']


def test_visual_facts_and_schema_are_scored(tmp_path):
    case = image_case(tmp_path)
    assert not score_case(case, {**good_output(), 'description': '鼠标功能正常。'})['passed']
    wrong = {**good_output(), 'title': '蓝色键盘', 'description': '蓝色键盘外壳。', 'tags': ['键盘']}
    assert not score_case(case, wrong)['passed']
    assert not score_case(case, {**good_output(), 'price': 50})['metrics']['schema_valid']
    assert not score_case(case, None, error='timeout')['passed']


def test_assets_fail_before_request_on_missing_tampering_or_escape(tmp_path):
    case = image_case(tmp_path)
    assert prepare_assets([case], tmp_path)
    (tmp_path / 'photo.jpg').write_bytes(b'changed')
    with pytest.raises(ValueError, match='SHA256'):
        prepare_assets([case], tmp_path)
    for path in ['../secret.jpg', 'C:/secret.jpg', 'https://x/img.jpg', '/secret.jpg']:
        case['input']['images'][0]['path'] = path
        with pytest.raises(ValueError):
            Case.model_validate(case)
    case['input']['images'][0]['path'] = 'missing.jpg'
    with pytest.raises(ValueError, match='missing'):
        prepare_assets([case], tmp_path)


def test_same_image_cannot_cross_splits_even_with_different_family(tmp_path):
    case = image_case(tmp_path)
    cases = tmp_path / 'cases'; cases.mkdir()
    write_json(cases / 'one.json', case)
    write_json(cases / 'two.json', {**case, 'id': 'second', 'family': 'different', 'split': 'holdout'})
    with pytest.raises(ValueError, match='image content leakage'):
        validate_cases(cases)
    with pytest.raises(ValueError):
        Profile(id='local', mode='local', tasks=['vision_draft'])


def test_text_sampling_deduplicates_families_and_requires_annotation(tmp_path):
    tsv = tmp_path / 'source.tsv'
    tsv.write_text('蓝色上衣\t蓝色的长袖上衣\n蓝色上衣\t上衣另一段描述\n黑色鞋子\t黑色的运动鞋子\n', encoding='utf-8')
    rows, stats = sample_text(tsv=tsv, count=2, seed=11)
    assert rows == sample_text(tsv=tsv, count=2, seed=11)[0]
    assert stats['eligible_families'] == 2
    package = tmp_path / 'sample'
    write_sample(package, rows, {'dataset': 'taodescribe', 'source_url': 'https://example.org', 'source_version': 'v1'})
    with pytest.raises(ValueError, match='must be filled'):
        build_cases(package)
    annotation = read_json(package / 'annotations.json')
    for label in annotation['annotations']:
        label.update(expected={'fields': {'price': None}}, rationale='no price', annotator='test fixture')
    write_json(package / 'annotations.json', annotation)
    cases = build_cases(package)
    assert all(c['label_status'] == 'draft' for c in cases)
    assert len(validate_cases(package / 'cases')) == 2
    with pytest.raises(ValueError, match='empty'):
        build_cases(package)


def test_parallel_text_source_must_align(tmp_path):
    a, b = tmp_path / 'title', tmp_path / 'desc'
    a.write_text('one\ntwo\n'); b.write_text('first description\n')
    with pytest.raises(ValueError, match='line counts'):
        sample_text(titles=a, descriptions=b, count=1, seed=1)
    tsv = tmp_path / 'wrong.tsv'
    tsv.write_text('title\tdescription\textra\n')
    with pytest.raises(ValueError, match='expected title and description'):
        sample_text(tsv=tsv, count=1, seed=1)


def test_products_preserve_sku_and_image_checksum(tmp_path):
    image_case(tmp_path)
    csv = tmp_path / 'train.csv'; csv.write_text('name,class,group\nphoto.jpg,123,5\n')
    rows, _ = sample_products(csv_path=csv, images_root=tmp_path, count=1, seed=1)
    assert rows[0]['source_sku'] == '123'
    package = tmp_path / 'package'
    write_sample(package, rows, {'dataset': 'products10k'}, images_root=tmp_path)
    assert (package / rows[0]['input']['images'][0]['path']).exists()
    assert rows[0]['input']['images'][0]['sha256'] == hashlib.sha256((tmp_path / 'photo.jpg').read_bytes()).hexdigest()


def test_cli_vision_report_and_image_change_rejected_before_run(tmp_path, monkeypatch):
    case = image_case(tmp_path)
    cases = tmp_path / 'cases'; cases.mkdir(); write_json(cases / 'one.json', case)
    config = tmp_path / 'models.json'
    write_json(config, {'version': 1, 'models': [{'id': 'vision-test', 'mode': 'remote', 'tasks': ['vision_draft'],
        'model': 'fixture', 'base_url': 'https://fixture.invalid/v1', 'api_key_env': 'FIXTURE_KEY'}]})
    monkeypatch.setenv('FIXTURE_KEY', 'test-secret')
    calls = []
    def fake_evaluate(case, profile, key, *, vision_images=None):
        calls.append(vision_images)
        return {'status': 'error', 'error': 'timeout', 'output': None, 'raw_output': None,
                'raw_score_output': None, 'fallback_used': False, 'latency_ms': 1, 'attempts': [],
                'cost_cny': None, 'prompt_hash': 'fixture'}
    monkeypatch.setattr('evals.adapters.evaluate', fake_evaluate)
    arguments = ['run', '--cases', str(cases), '--assets-root', str(tmp_path), '--model-config', str(config),
                 '--models', 'vision-test', '--allow-remote', '--max-requests', '1']
    assert main([*arguments, '--output', str(tmp_path / 'run')]) == 0
    assert len(calls) == 1 and calls[0]
    summary = read_json(tmp_path / 'run/summary.json')
    assert summary['groups'][0]['category_accuracy'] == 0
    assert summary['selection'][0]['selected_model'] is None
    (tmp_path / 'photo.jpg').write_bytes(b'changed')
    assert main([*arguments, '--output', str(tmp_path / 'another')]) == 2
    assert len(calls) == 1 and not (tmp_path / 'another').exists()
