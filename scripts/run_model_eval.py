"""Manage cases, execute evaluations, and compare immutable run directories."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))

from evals import SCORER_VERSION
from evals.common import canonical_json, digest, read_json, write_json
from evals.providers import load_profiles, resolve_profile
from evals.schema import validate_cases


def csv_values(value):
    return [x.strip() for x in value.split(',') if x.strip()]


def git_info():
    def command(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, stderr=subprocess.DEVNULL).strip()
    try:
        return command('rev-parse', 'HEAD'), bool(command('status', '--porcelain'))
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, None


def implementation_hash():
    import hashlib
    paths = sorted((ROOT / 'evals').glob('*.py')) + [ROOT / 'scripts/run_model_eval.py']
    paths += [ROOT / 'backend/app' / name for name in ('services.py', 'buyer_agent.py', 'schemas.py')]
    return digest({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def select_cases(cases, args):
    selected = [c for c in cases if c['enabled'] and (args.split == 'all' or c['split'] == args.split)]
    tasks = set(csv_values(args.tasks))
    tags = set(csv_values(args.tags))
    ids = set(csv_values(args.case_ids))
    if tasks - {c['task'] for c in cases}:
        raise ValueError('Unknown task filter')
    if ids - {c['id'] for c in cases}:
        raise ValueError('Unknown case ID filter')
    if tasks:
        selected = [c for c in selected if c['task'] in tasks]
    if tags:
        selected = [c for c in selected if tags & set(c['tags'])]
    if ids:
        selected = [c for c in selected if c['id'] in ids]
    if not selected:
        raise ValueError('No enabled cases match the filters')
    return selected


def redact(value, keys):
    if isinstance(value, str):
        for key in keys:
            if key:
                value = value.replace(key, '[REDACTED]')
        return value
    if isinstance(value, list):
        return [redact(v, keys) for v in value]
    if isinstance(value, dict):
        return {redact(k, keys): redact(v, keys) for k, v in value.items()}
    return value


def run(args):
    from evals.adapters import evaluate
    from evals.reporting import validate_policy, write_reports
    from evals.scoring import score_case

    if not 1 <= args.repeats <= 20 or args.max_requests < 0:
        raise ValueError('repeats must be 1–20 and max-requests must be nonnegative')
    cases = select_cases(validate_cases(args.cases), args)
    profiles = load_profiles(args.model_config)
    requested = csv_values(args.models)
    if not requested or len(set(requested)) != len(requested):
        raise ValueError('Choose unique model profile IDs')
    by_id = {p.id: p for p in profiles}
    if set(requested) - set(by_id):
        raise ValueError('Unknown model profile ID')
    chosen = [by_id[name] for name in requested]
    if any(p.mode == 'remote' for p in chosen) and not args.allow_remote:
        raise ValueError('Remote calls require --allow-remote and configured EVAL_* variables')
    for profile in chosen:
        if not any(c['task'] in profile.tasks for c in cases):
            raise ValueError(f'{profile.id}: no selected task is supported')
    cases = [c for c in cases if any(c['task'] in p.tasks for p in chosen)]
    # Reject the entire run before spending tokens if its worst-case request count exceeds the cap.
    upper_bound = sum(sum(c['task'] in p.tasks for c in cases) * args.repeats * (p.retries + 1)
                      for p in chosen if p.mode == 'remote')
    if upper_bound > args.max_requests:
        raise ValueError(f'Worst-case remote requests {upper_bound} exceed --max-requests {args.max_requests}')
    resolved = [resolve_profile(p) for p in chosen]
    policy = read_json(args.policy)
    if not isinstance(policy, dict):
        raise ValueError('Selection policy must be a JSON object')
    validate_policy(policy)
    created = datetime.now(timezone.utc)
    run_id = created.strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    destination = Path(args.output) if args.output else ROOT / 'evals/results' / run_id
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Output directory must be empty; previous runs are immutable')
    destination.mkdir(parents=True, exist_ok=True)
    sha, dirty = git_info()
    case_hashes = {c['id']: digest(c) for c in cases}
    manifest = {
        'run_id': run_id, 'created_at': created.isoformat(), 'git_sha': sha, 'dirty': dirty,
        'implementation_hash': implementation_hash(), 'dataset_hash': digest(cases),
        'scorer_version': SCORER_VERSION, 'policy_hash': digest(policy),
        'models': [p for p, _ in resolved],
        'cases': [{'id': c['id'], 'hash': case_hashes[c['id']], 'task': c['task'], 'split': c['split'],
                   'label_status': c['label_status']} for c in cases],
        'repeats': args.repeats, 'seed': args.seed, 'concurrency': 1,
        'max_remote_requests': args.max_requests, 'worst_case_remote_requests': upper_bound,
        'complete': False,
    }
    write_json(destination / 'manifest.json', manifest)
    write_json(destination / 'cases.json', cases)
    write_json(destination / 'policy.json', policy)
    records = []
    keys = [key.get_secret_value() for _, key in resolved]
    rng = random.Random(args.seed)
    schedule = []
    for repeat in range(1, args.repeats + 1):
        ordered_cases = list(cases)
        rng.shuffle(ordered_cases)
        for case in ordered_cases:
            eligible = [(p, key) for p, key in resolved if case['task'] in p['tasks']]
            rng.shuffle(eligible)
            schedule.extend((repeat, case, p, key) for p, key in eligible)
    interrupted = False
    try:
        with (destination / 'records.jsonl').open('w', encoding='utf-8') as stream:
            for number, (repeat, case, profile, key) in enumerate(schedule, 1):
                value = evaluate(case, profile, key)
                raw_score_output = value.pop('raw_score_output')
                value['application_score'] = score_case(case, value['output'])
                value['score'] = score_case(case, value['output'], error=value['error'])
                value['raw_score'] = None if profile['mode'] == 'local' else score_case(
                    case, raw_score_output if raw_score_output is not None else value['raw_output'], error=value['error'])
                record = dict(value, case_id=case['id'], case_hash=case_hashes[case['id']],
                              task=case['task'], split=case['split'], label_status=case['label_status'],
                              model=profile['id'], repeat=repeat)
                record = redact(record, keys)
                stream.write(canonical_json(record) + '\n')
                stream.flush()
                records.append(record)
                print(f'{number}/{len(schedule)} {profile["id"]} {case["id"]} '
                      f'{"PASS" if record["score"]["passed"] else "FAIL"} {record["latency_ms"]:.1f}ms', flush=True)
        manifest['complete'] = True
    except KeyboardInterrupt:
        interrupted = True
        manifest['interrupted'] = True
    finally:
        manifest['completed_records'] = len(records)
        manifest['expected_records'] = len(schedule)
        write_reports(destination, records, manifest, policy)
    print(f'Report: {(destination / "report.md").resolve()}')
    if interrupted:
        return 130
    if args.require_pass and any(not r['score']['passed'] for r in records):
        return 1
    return 0


def parser():
    top = argparse.ArgumentParser(description=__doc__)
    commands = top.add_subparsers(dest='command', required=True)
    for name in ('validate', 'list', 'run'):
        cmd = commands.add_parser(name)
        cmd.add_argument('--cases', default=str(ROOT / 'evals/cases'))
        cmd.add_argument('--model-config', default=str(ROOT / 'evals/models.json'))
        if name in {'list', 'run'}:
            cmd.add_argument('--tasks', default='')
            cmd.add_argument('--tags', default='')
            cmd.add_argument('--case-ids', default='')
            cmd.add_argument('--split', choices=['dev', 'holdout', 'all'], default='dev')
        if name == 'run':
            cmd.add_argument('--models', default='local-rules')
            cmd.add_argument('--policy', default=str(ROOT / 'evals/selection_policy.json'))
            cmd.add_argument('--repeats', type=int, default=1)
            cmd.add_argument('--seed', type=int, default=20261115)
            cmd.add_argument('--max-requests', type=int, default=200)
            cmd.add_argument('--allow-remote', action='store_true')
            cmd.add_argument('--require-pass', action='store_true', help='Exit 1 for any failed case; diagnostics otherwise exit 0')
            cmd.add_argument('--output')
    compare = commands.add_parser('compare')
    compare.add_argument('--baseline', required=True)
    compare.add_argument('--current', required=True)
    compare.add_argument('--output', required=True)
    compare.add_argument('--fail-on-regression', action='store_true')
    return top


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == 'validate':
            cases = validate_cases(args.cases)
            models = load_profiles(args.model_config)
            print(f'Valid: {len(cases)} cases ({sum(c["enabled"] for c in cases)} enabled), {len(models)} model profiles')
            return 0
        if args.command == 'list':
            for case in select_cases(validate_cases(args.cases), args):
                print(f'{case["id"]}\t{case["task"]}\t{case["split"]}\t{case["label_status"]}\t{",".join(case["tags"])}')
            return 0
        if args.command == 'run':
            return run(args)
        from evals.reporting import compare_runs
        result = compare_runs(args.baseline, args.current, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if args.fail_on_regression and result.get('has_regressions') else 0
    except (ValueError, OSError) as exc:
        # Pydantic validation errors can include input values: do not print arbitrary model config contents.
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            print('Validation error: ' + '; '.join(f'{e["loc"]}: {e["type"]}' for e in exc.errors(include_input=False)), file=sys.stderr)
        else:
            print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    raise SystemExit(main())
