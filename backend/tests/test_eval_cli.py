import json

import pytest

from app import concept_learning
from app.config import Settings
from eval import adapters, cli, datasets, report


def test_validate_rows_reports_structural_errors():
    rows = [
        {'id': 'x1', 'node': '1.1', 'split': 'dev', 'input': {}, 'gold': {}},
        {'id': 'x1', 'node': '2.1', 'split': 'test', 'input': {}, 'gold': {}},
        {'id': 'x2', 'node': '1.1', 'input': {}, 'gold': {}},
    ]
    problems = datasets.validate_rows('1.1', rows)
    assert any('node mismatch' in problem for problem in problems)
    assert any('bad split' in problem for problem in problems)
    assert any('missing split' in problem for problem in problems)
    assert any('duplicate id' in problem for problem in problems)


def test_validate_rows_requires_vision_files(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, 'DATASET_DIR', tmp_path)
    row = {'id': 'v1', 'node': '1.2', 'split': 'dev', 'gold': {},
           'input': {'images': [{'file': 'images/missing.jpg'}]}}
    problems = datasets.validate_rows('1.2', [row])
    assert any('missing image' in problem for problem in problems)


def test_manifest_freeze_detects_tampering(tmp_path, monkeypatch):
    data_dir = tmp_path / 'datasets'
    (data_dir / 'images').mkdir(parents=True)
    for name in (*datasets.NODE_FILES.values(), datasets.POOL_FILE):
        (data_dir / name).write_text('{"id":"x"}\n', encoding='utf-8')
    (data_dir / 'images' / 'one.jpg').write_bytes(b'image-bytes')
    monkeypatch.setattr(datasets, 'DATASET_DIR', data_dir)
    monkeypatch.setattr(datasets, 'MANIFEST_PATH', data_dir / 'manifest.json')
    monkeypatch.setattr(datasets, 'IMAGES_DIR', data_dir / 'images')

    manifest = datasets.build_manifest('test-v1', '2026-01-01T00:00:00Z', 'A')
    assert manifest['files']['images/one.jpg']['sha256']
    datasets.MANIFEST_PATH.write_text(json.dumps(manifest), encoding='utf-8')
    assert datasets.verify_manifest()[0] is True

    (data_dir / 'images' / 'one.jpg').write_bytes(b'tampered')
    ok, details = datasets.verify_manifest()
    assert ok is False
    assert details['mismatches'][0]['file'] == 'images/one.jpg'


def test_real_run_requires_explicit_flag(tmp_path, capsys):
    code = cli.main(['run', '--node', '1.1', '--out', str(tmp_path)])
    assert code == 2
    assert 'refusing' in capsys.readouterr().err


def test_real_run_refuses_when_manifest_does_not_match(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(datasets, 'verify_manifest', lambda: (False, {'mismatches': ['x']}))
    code = cli.main(['run', '--node', '1.1', '--out', str(tmp_path), '--real'])
    assert code == 2
    assert 'manifest mismatch' in capsys.readouterr().err


def test_check_models_marks_missing_credentials_unavailable(capsys):
    # conftest clears provider variables, so no network call is attempted.
    assert cli.main(['check-models']) == 0
    results = json.loads(capsys.readouterr().out)
    assert results
    assert {entry['status'] for entry in results.values()} == {'UNAVAILABLE'}


def test_models_config_contains_no_literal_secrets():
    config = json.loads((cli.HERE / 'models.json').read_text(encoding='utf-8'))
    for kind in ('text', 'vision', 'embedding'):
        for candidate in config[kind]:
            assert candidate['key_env'].endswith('_KEY') or candidate['key_env'].endswith('_KEY_B')
            assert set(candidate) <= {'id', 'label', 'model', 'model_env', 'base_url_env', 'key_env',
                                      'price_per_1k_input', 'price_per_1k_output'}


def test_git_state_is_recorded_for_traceability():
    assert isinstance(datasets.git_sha(), (str, type(None)))
    assert isinstance(datasets.git_dirty(), (bool, type(None)))


DUMMY_RUN = {'node': '1.1', 'candidate': 'c', 'split': 'dev', 'samples': [],
             'usage': {'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'failures': 0}}


def test_fixture_report_cannot_be_verified_as_final(tmp_path):
    report.write_report(tmp_path, {'fixture': True, 'dataset_verified': True}, [DUMMY_RUN], {})
    ok, problems = report.verify_report(tmp_path)
    assert ok is False
    assert 'fixture run cannot be a final result' in problems


def test_unverified_report_rejected(tmp_path):
    report.write_report(tmp_path, {'fixture': False, 'dataset_verified': False}, [DUMMY_RUN], {})
    ok, problems = report.verify_report(tmp_path)
    assert ok is False
    assert 'dataset hash was not verified' in problems


def test_summary_reads_checks_per_candidate():
    runs = [dict(DUMMY_RUN, candidate='a'), dict(DUMMY_RUN, candidate='b')]
    checks = {'a': {'1.1': {'valid_rate': {'value': 1.0, 'rule': {'min': 0.98}, 'pass': True}}},
              'b': {'1.1': {'valid_rate': {'value': 0.5, 'rule': {'min': 0.98}, 'pass': False}}}}
    text = report.render_summary({}, runs, checks)
    assert '| a | 1.1 | dev | valid_rate | 1.000 |' in text
    assert '| b | 1.1 | dev | valid_rate | 0.500 |' in text


def test_case_rows_counts_correct_and_wrong_examples():
    rows = [
        {'id': 'c1', 'node': '1.1', 'split': 'dev', 'input': {'raw': 'x'},
         'gold': {'category': '数码', 'price': 100, 'campus': '主校区', 'condition_grade': '95新'}},
        {'id': 'c2', 'node': '1.1', 'split': 'dev', 'input': {'raw': 'y'},
         'gold': {'category': '书籍', 'price': 20, 'campus': '主校区', 'condition_grade': '95新'}},
    ]
    run = {'node': '1.1', 'candidate': 'c', 'split': 'dev', 'samples': [
        {'id': 'c1', 'split': 'dev', 'ok': True,
         'output': {'category': '数码', 'price': 100.0, 'campus': '主校区', 'condition_grade': '95新'}},
        {'id': 'c2', 'split': 'dev', 'ok': True,
         'output': {'category': '数码', 'price': 20.0, 'campus': '主校区', 'condition_grade': '95新'}},
    ]}
    cases = report.case_rows(run, rows)
    assert [case['id'] for case in cases if case['correct']] == ['c1']
    assert [case['id'] for case in cases if not case['correct']] == ['c2']
    rendered = report.render_cases(cases)
    assert '正确 1 条：c1' in rendered
    assert '错误 1 条：c2' in rendered


def test_concept_adapter_validates_without_writing(monkeypatch):
    def proposal(item, catalog, settings, observer=None):
        return {'assignments': [{'name': '手账本', 'definition': '记录用手册',
                                 'aliases': ['笔记本'], 'evidence': '笔记本'}]}

    monkeypatch.setattr(concept_learning, 'propose', proposal)
    data = {'item': {'title': '笔记本内页 网格', 'description': '手账用', 'tags': ['笔记本']},
            'catalog': [{'name': '笔记本电脑', 'definition': '便携式计算机',
                         'category': '数码与影音', 'aliases': ['笔记本']}]}
    output = adapters.run_concept(data, Settings(), [])
    assert output['decision'] == 'reject'
    assert output['reason'] == 'alias_conflict'
    assert output['schema_valid'] is True


def test_case_rows_flags_ungrounded_concept_alias():
    rows = [{'id': 'k1', 'node': '1.4', 'split': 'dev',
             'input': {'item': {'title': '雪纺半身裙', 'description': '', 'tags': []}},
             'gold': {'decision': 'apply', 'reason': None,
                      'families': [{'name': '半身裙', 'parent': '裙子', 'aliases': []}]}}]
    run = {'node': '1.4', 'candidate': 'c', 'split': 'dev', 'samples': [
        {'id': 'k1', 'split': 'dev', 'ok': True,
         'output': {'decision': 'apply', 'reason': 'learned',
                    'families': [{'name': '半身裙', 'parent': '裙子', 'aliases': ['连衣裙']}],
                    'aliases': ['连衣裙'], 'evidence_grounded': True}}]}
    cases = report.case_rows(run, rows)
    assert cases[0]['correct'] is False
    assert any(problem.startswith('ungrounded_alias') for problem in cases[0]['differences'])
