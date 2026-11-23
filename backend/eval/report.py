"""Render evaluation results as JSON, CSV and Markdown."""
import csv
import json
from pathlib import Path


def _fmt(value):
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return f'{value:.3f}'
    return str(value)


def write_report(out_dir, manifest, runs, checks):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (out_dir / 'results.json').write_text(
        json.dumps({'manifest': manifest, 'runs': runs, 'checks': checks}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    with (out_dir / 'results.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['candidate', 'node', 'id', 'split', 'stratum', 'ok', 'error', 'latency_ms', 'output'])
        for run in runs:
            for sample in run['samples']:
                writer.writerow([run['candidate'], run['node'], sample['id'], sample['split'],
                                 sample.get('stratum'), sample['ok'], sample['error'] or '',
                                 f"{sample['latency_ms']:.1f}",
                                 json.dumps(sample['output'], ensure_ascii=False)])
    (out_dir / 'summary.md').write_text(render_summary(manifest, runs, checks), encoding='utf-8')
    return out_dir


def render_summary(manifest, runs, checks):
    lines = ['# AI pipeline evaluation summary', '']
    lines.append(f"- dataset version: `{manifest.get('dataset_version')}`")
    lines.append(f"- dataset verified: `{manifest.get('dataset_verified')}`")
    lines.append(f"- git sha: `{manifest.get('git_sha')}`")
    lines.append(f"- mode: `{'fixture' if manifest.get('fixture') else 'real'}`")
    lines.append(f"- generated at: `{manifest.get('generated_at')}`")
    lines.append(f"- prompt versions: `{json.dumps(manifest.get('prompt_versions'), ensure_ascii=False)}`")
    lines.append('')
    lines.append('## Metrics')
    lines.append('')
    lines.append('| candidate | node | split | metric | value | rule | pass |')
    lines.append('|---|---|---|---|---:|---|---|')
    by_candidate = {}
    for run in runs:
        by_candidate.setdefault(run['candidate'], {})[run['node']] = run
    for candidate, node_runs in by_candidate.items():
        for node, run in node_runs.items():
            for name, entry in checks.get(node, {}).items():
                rule = entry['rule']
                rule_text = ', '.join(f'{key}={value}' for key, value in rule.items() if key != 'hard')
                lines.append(f"| {candidate} | {node} | {run['split']} | {name} | {_fmt(entry['value'])} | "
                             f"{rule_text} | {_fmt(entry['pass'])} |")
    lines.append('')
    lines.append('## Usage')
    lines.append('')
    lines.append('| candidate | node | samples | calls | input tokens | output tokens | failures |')
    lines.append('|---|---|---:|---:|---:|---:|---:|')
    for candidate, node_runs in by_candidate.items():
        for node, run in node_runs.items():
            usage = run['usage']
            lines.append(f"| {candidate} | {node} | {len(run['samples'])} | {usage['calls']} | "
                         f"{usage['input_tokens']} | {usage['output_tokens']} | {usage['failures']} |")
    lines.append('')
    lines.append('## Failure samples')
    lines.append('')
    failures = [(run['candidate'], run['node'], sample) for run in runs for sample in run['samples'] if not sample['ok']]
    if not failures:
        lines.append('None.')
    else:
        lines.append('| candidate | node | sample | error |')
        lines.append('|---|---|---|---|')
        for candidate, node, sample in failures:
            lines.append(f"| {candidate} | {node} | {sample['id']} | {sample['error']} |")
    lines.append('')
    return '\n'.join(lines)


def verify_report(out_dir):
    path = Path(out_dir) / 'results.json'
    if not path.exists():
        return False, ['results.json missing']
    data = json.loads(path.read_text(encoding='utf-8'))
    problems = []
    if data.get('manifest', {}).get('fixture'):
        problems.append('fixture run cannot be a final result')
    if not data.get('manifest', {}).get('dataset_verified'):
        problems.append('dataset hash was not verified')
    if not data.get('runs'):
        problems.append('no runs recorded')
    return not problems, problems