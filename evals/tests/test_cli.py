import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.run_model_eval import main, redact

ROOT = Path(__file__).resolve().parents[2]


def test_full_offline_cli_run_and_comparison(tmp_path):
    before, after, diff = (tmp_path / name for name in ('before', 'after', 'diff'))
    arguments = ['run', '--models', 'local-rules', '--case-ids', 'intent-001,item-001']
    assert main([*arguments, '--output', str(before)]) == 0
    assert main([*arguments, '--output', str(after)]) == 0
    manifest = json.loads((before / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['complete'] and manifest['expected_records'] == 2
    assert (before / 'report.md').exists()
    assert (before / 'cases.json').exists()
    assert main(['compare', '--baseline', str(before), '--current', str(after),
                 '--output', str(diff), '--fail-on-regression']) == 0
    result = json.loads((diff / 'comparison.json').read_text(encoding='utf-8'))
    assert result['comparable_record_count'] == 2 and not result['has_regressions']
    assert main([*arguments, '--output', str(before)]) == 2


def test_remote_is_opt_in_and_cap_is_checked_before_credentials(tmp_path, capsys):
    output = tmp_path / 'no-calls'
    assert main(['run', '--models', 'text-a', '--output', str(output)]) == 2
    assert '--allow-remote' in capsys.readouterr().err
    assert main(['run', '--models', 'text-a', '--allow-remote', '--max-requests', '0', '--output', str(output)]) == 2
    assert 'exceed' in capsys.readouterr().err
    assert not output.exists()


def test_filters_and_unknown_models_fail_clearly(capsys):
    assert main(['list', '--tasks', 'candidate_review']) == 0
    assert len(capsys.readouterr().out.splitlines()) == 8
    assert main(['run', '--models', 'typo']) == 2
    assert main(['list', '--case-ids', 'typo']) == 2
    assert main(['run', '--tasks', 'candidate_review']) == 2


def test_secret_redaction_covers_keys_and_values():
    assert redact({'secret-value': ['Bearer secret-value']}, ['secret-value']) == {
        '[REDACTED]': ['Bearer [REDACTED]']}


def test_cli_does_not_read_application_env(tmp_path):
    # Run with unrelated production/SMTP/model environment set. Offline execution
    # must not construct application Settings or connect to external services.
    import os
    env = dict(os.environ, AI_MODE='remote', APP_ENV='production', VISION_ENABLED='true',
               CHAT_EMAIL_ENABLED='true', MODEL_TIMEOUT_SECONDS='invalid', DEEPSEEK_API_KEY='not-a-real-key')
    process = subprocess.run([sys.executable, str(ROOT / 'scripts/run_model_eval.py'), 'run',
        '--models', 'local-rules', '--case-ids', 'intent-001', '--output', str(tmp_path / 'result')],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert process.returncode == 0, process.stderr
    assert 'not-a-real-key' not in process.stdout + process.stderr
