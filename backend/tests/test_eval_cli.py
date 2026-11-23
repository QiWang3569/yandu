import json

import pytest

from eval import cli, datasets, report


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
            assert set(candidate) <= {'id', 'label', 'model_env', 'base_url_env', 'key_env',
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
