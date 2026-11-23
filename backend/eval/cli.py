"""Command line entry point: ``python -m eval.cli <command>``.

Real model calls require an explicit --real flag. Fixture runs exist only to test
the harness and are rejected by ``verify`` as final evidence.
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from app import buyer_agent, services
from app.config import Settings
from app.vision import SYSTEM_PROMPT, VisionDraft, VisionService

from . import adapters, datasets, report, runner

HERE = Path(__file__).resolve().parent
NODES = ('1.1', '1.2', '2.1', '2.3', '2.4')
KIND = {'1.1': 'text', '2.1': 'text', '2.4': 'text', '1.2': 'vision', '2.3': 'program'}


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def load_models(path):
    return load_json(path)


def load_thresholds(path):
    return load_json(path)


def resolve_candidate(candidate):
    return {
        'id': candidate['id'],
        'model': os.getenv(candidate.get('model_env', ''), ''),
        'url': os.getenv(candidate.get('base_url_env', ''), ''),
        'key': os.getenv(candidate.get('key_env', ''), ''),
        'label': candidate.get('label', candidate['id']),
    }


def available(candidate):
    return bool(candidate['model'] and candidate['url'] and candidate['key'])


def settings_for(kind, base, candidate):
    if kind == 'text':
        return adapters.text_settings(base, candidate['model'], candidate['url'], candidate['key'])
    if kind == 'vision':
        return adapters.vision_settings(base, candidate['model'], candidate['url'], candidate['key'])
    return adapters.embedding_settings(base, candidate['model'], candidate['url'], candidate['key'])


def selected_nodes(value):
    if value in (None, 'all'):
        return list(NODES)
    nodes = [item.strip() for item in value.split(',') if item.strip()]
    unknown = [node for node in nodes if node not in NODES]
    if unknown:
        raise SystemExit(f'unknown nodes: {unknown}')
    return nodes


def cmd_freeze(args):
    manifest = datasets.build_manifest(args.version, args.frozen_at, args.annotator)
    datasets.MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def cmd_check_models(args):
    config = load_models(args.config)
    base = Settings()
    results = {}
    for kind in ('text', 'vision', 'embedding'):
        for raw in config.get(kind, []):
            candidate = resolve_candidate(raw)
            if not available(candidate):
                missing = [raw.get('model_env'), raw.get('base_url_env'), raw.get('key_env')]
                results[candidate['id']] = {'status': 'UNAVAILABLE', 'missing_env': missing}
                continue
            settings = settings_for(kind, base, candidate)
            try:
                if kind == 'text':
                    buyer_agent.chat_json('只返回 JSON {"ok": true}', {'ping': '1'}, settings, max_tokens=32)
                elif kind == 'vision':
                    image = adapters.render_image({'shape': 'lamp', 'label': 'Lamp'})
                    asyncio.run(VisionService(settings)._complete([image], '', SYSTEM_PROMPT, VisionDraft, 300))
                else:
                    vector = services.embed('ping', settings)
                    if not vector or len(vector) != 1536:
                        raise ValueError('bad embedding')
                results[candidate['id']] = {'status': 'OK', 'model': candidate['model']}
            except Exception as exc:
                results[candidate['id']] = {'status': 'FAIL', 'model': candidate['model'],
                                            'error': type(exc).__name__}
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


def cmd_dry_run(args):
    nodes = selected_nodes(args.node)
    counts = {}
    for node in nodes:
        rows = datasets.load_rows(node, args.split)
        problems = datasets.validate_rows(node, rows)
        if problems:
            print('\n'.join(problems), file=sys.stderr)
            return 2
        counts[node] = len(rows)
    ok, details = datasets.verify_manifest()
    calls = sum(counts.values())
    print(json.dumps({'split': args.split, 'rows': counts, 'estimated_model_calls': calls,
                      'dataset_manifest_ok': ok, 'dataset_manifest': details}, ensure_ascii=False, indent=2))
    return 0


def cmd_real(args):
    if not args.real and not args.fixture:
        print('refusing to run: pass --real for provider calls or --fixture for harness plumbing', file=sys.stderr)
        return 2
    nodes = selected_nodes(args.node)
    config = load_models(args.config)
    thresholds = load_thresholds(args.thresholds)
    ok, details = datasets.verify_manifest()
    if args.real and not ok:
        print(f'refusing real run: dataset manifest mismatch {details}', file=sys.stderr)
        return 2
    base = Settings()
    manifest = json.loads(datasets.MANIFEST_PATH.read_text(encoding='utf-8')) if datasets.MANIFEST_PATH.exists() else {}
    model_rows = {'text': [], 'vision': []}
    unavailable = []
    runs = []
    prompt_versions = {
        '1.1': services.ITEM_PROMPT_VERSION,
        '1.2': __import__('app.vision', fromlist=['PROMPT_VERSION']).PROMPT_VERSION,
        '2.1': services.INTENT_PROMPT_VERSION,
        '2.3': 'lexical-alias-1',
        '2.4': buyer_agent.REVIEW_PROMPT_VERSION,
    }
    for kind in ('text', 'vision'):
        for raw in config.get(kind, []):
            if args.candidate and raw['id'] not in args.candidate:
                continue
            candidate = resolve_candidate(raw)
            if not available(candidate):
                unavailable.append(candidate['id'])
                print(f"UNAVAILABLE {candidate['id']}: missing {raw.get('model_env')}/"
                      f"{raw.get('base_url_env')}/{raw.get('key_env')}")
                continue
            model_rows[kind].append({'id': candidate['id'], 'model': candidate['model']})
            settings = settings_for(kind, base, candidate)
            for node in nodes:
                if KIND[node] != kind:
                    continue
                print(f'running {node} on {candidate["id"]} ({candidate["model"]})', file=sys.stderr)
                runs.append(runner.run_node(node, args.split, settings, candidate,
                                            fixture=args.fixture, attempts=args.attempts))
    if '2.3' in nodes:
        print('running 2.3 (programmatic lexical recall)', file=sys.stderr)
        runs.append(runner.run_node('2.3', args.split, base, None,
                                    fixture=args.fixture, attempts=1))
    metrics_by_node = {run['node']: run['metrics'] for run in runs}
    checks = runner.evaluate_checks(metrics_by_node, thresholds)
    eval_manifest = {
        'dataset_version': manifest.get('version'),
        'dataset_sha': {name: meta['sha256'] for name, meta in manifest.get('files', {}).items()},
        'dataset_verified': ok,
        'git_sha': datasets.git_sha(),
        'git_dirty': datasets.git_dirty(),
        'prompt_versions': prompt_versions,
        'models': model_rows,
        'unavailable': unavailable,
        'fixture': bool(args.fixture),
        'split': args.split,
        'generated_at': runner.now_iso(),
        'thresholds': thresholds,
    }
    report.write_report(args.out, eval_manifest, runs, checks)
    print(json.dumps({'out': str(args.out), 'runs': len(runs), 'unavailable': unavailable,
                      'checks': checks}, ensure_ascii=False, indent=2))
    return 0


def cmd_verify(args):
    ok, problems = report.verify_report(args.path)
    dataset_ok, details = datasets.verify_manifest()
    print(json.dumps({'report_ok': ok, 'problems': problems,
                      'dataset_manifest_ok': dataset_ok, 'dataset': details}, ensure_ascii=False, indent=2))
    return 0 if ok and dataset_ok else 1


def build_parser():
    parser = argparse.ArgumentParser(prog='eval')
    sub = parser.add_subparsers(dest='command', required=True)

    freeze = sub.add_parser('freeze-datasets')
    freeze.add_argument('--version', required=True)
    freeze.add_argument('--frozen-at', required=True)
    freeze.add_argument('--annotator', required=True)
    freeze.set_defaults(func=cmd_freeze)

    check = sub.add_parser('check-models')
    check.add_argument('--config', default=str(HERE / 'models.json'))
    check.set_defaults(func=cmd_check_models)

    dry = sub.add_parser('dry-run')
    dry.add_argument('--node', default='all')
    dry.add_argument('--split', default='sealed_test', choices=['all', 'dev', 'sealed_test'])
    dry.set_defaults(func=cmd_dry_run)

    real = sub.add_parser('run')
    real.add_argument('--node', default='all')
    real.add_argument('--split', default='sealed_test', choices=['all', 'dev', 'sealed_test'])
    real.add_argument('--config', default=str(HERE / 'models.json'))
    real.add_argument('--thresholds', default=str(HERE / 'thresholds.json'))
    real.add_argument('--candidate', action='append', default=[])
    real.add_argument('--out', required=True)
    real.add_argument('--attempts', type=int, default=3)
    real.add_argument('--real', action='store_true')
    real.add_argument('--fixture', action='store_true')
    real.set_defaults(func=cmd_real)

    verify = sub.add_parser('verify')
    verify.add_argument('path')
    verify.set_defaults(func=cmd_verify)
    return parser


def sanitize_proxy_env():
    """httpx mis-parses the bracketed IPv6 form ``[::1]`` as a port in NO_PROXY."""
    value = os.environ.get('NO_PROXY') or os.environ.get('no_proxy')
    if value and '[::1]' in value:
        os.environ['NO_PROXY'] = ','.join(part for part in value.split(',') if part.strip() != '[::1]')
        os.environ.pop('no_proxy', None)


def main(argv=None):
    sanitize_proxy_env()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())