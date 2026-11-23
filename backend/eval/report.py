"""Render evaluation results as JSON, CSV and Markdown."""
import csv
import json
from pathlib import Path

from . import metrics


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
            node_checks = checks.get(candidate, {}).get(node) or checks.get(node, {})
            for name, entry in node_checks.items():
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


def _short(value, limit=90):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _input_summary(node, row):
    data = row.get('input') or {}
    if node == '1.1':
        return _short(data.get('raw', ''), 60)
    if node == '1.2':
        return _short(' | '.join(image.get('file', '') for image in data.get('images', [])), 60)
    if node == '2.1':
        return _short(data.get('query', ''), 60)
    if node == '2.4':
        intent = data.get('intent') or {}
        item = data.get('item') or {}
        return _short('需求：' + '/'.join(intent.get('keywords') or []) + ' ↔ ' + str(item.get('title', '')), 60)
    if node == '1.4':
        item = data.get('item') or {}
        return _short(str(item.get('title', '')) + ' ' + str(item.get('description', '')), 60)
    return _short(data, 60)


def _verdict(node, row, sample):
    """Adjudication-level pass rule per node; returns (correct, differences)."""
    if not sample.get('ok'):
        return False, [f"error:{sample.get('error') or 'unknown'}"]
    gold, out = row.get('gold') or {}, sample.get('output') or {}
    diff = []
    if node == '1.1':
        for field in ('category', 'price', 'campus', 'condition_grade'):
            left, right = gold.get(field), out.get(field)
            if field == 'price':
                left, right = _number(left), _number(right)
            if left != right:
                diff.append(field)
    elif node == '1.2':
        if gold.get('status') != out.get('status'):
            diff.append('status')
        if gold.get('status') == 'ready':
            if gold.get('category') != out.get('category'):
                diff.append('category')
            text = ' '.join(filter(None, [out.get('title'), out.get('description'), *(out.get('tags') or [])]))
            hits = [term for term in gold.get('forbidden_terms', []) if term and term.lower() in text.lower()]
            if hits:
                diff.append('forbidden:' + ','.join(hits))
    elif node == '2.1':
        for field in ('category', 'campus', 'condition_grade', 'max_price'):
            left, right = gold.get(field), out.get(field)
            if field == 'max_price':
                left, right = _number(left), _number(right)
            if left != right:
                diff.append(field)
        if metrics.quote_recall(gold.get('gold_quotes', []), out.get('quotes') or []) < 1:
            diff.append('quotes')
    elif node == '2.4':
        if gold.get('verdict') != out.get('verdict'):
            diff.append('verdict')
        item = row['input']['item']
        sources = [item.get('title') or '', item.get('description') or '', *(item.get('tags') or [])]
        quotes = [evidence.get('quote', '') for evidence in out.get('evidence') or []]
        if metrics.grounding_rate(quotes, sources) < 1:
            diff.append('grounding')
        if gold.get('verdict') == 'NO_MATCH' and out.get('verdict') == 'MATCH':
            diff.append('exclusion_false_accept')
    elif node == '1.4':
        decision = out.get('decision')
        if decision != gold.get('decision'):
            diff.append('decision')
        if decision == 'reject' and gold.get('reason') and out.get('reason') != gold.get('reason'):
            diff.append('reason')
        if decision == 'apply':
            families = {family.get('name') for family in out.get('families') or []}
            missing = sorted(name for name in {family.get('name') for family in gold.get('families') or []}
                             if name not in families)
            if missing:
                diff.append('missing:' + ','.join(missing))
            if gold.get('reason') == 'no_family' and families:
                diff.append('unexpected_family')
            item = row['input']['item']
            text = ' '.join([item.get('title') or '', item.get('description') or '',
                             *(item.get('tags') or [])]).lower()
            bad = sorted({alias for family in out.get('families') or []
                          for alias in family.get('aliases') or [] if alias.lower() not in text})
            if bad:
                diff.append('ungrounded_alias:' + ','.join(bad[:3]))
    return not diff, diff


def case_rows(run, rows):
    by_id = {row['id']: row for row in rows}
    cases = []
    for sample in run.get('samples', []):
        row = by_id.get(sample['id'])
        if row is None:
            continue
        correct, differences = _verdict(run['node'], row, sample)
        cases.append({
            'id': sample['id'],
            'split': sample.get('split'),
            'stratum': sample.get('stratum'),
            'input': _input_summary(run['node'], row),
            'gold': _short(row.get('gold'), 90),
            'actual': _short(sample.get('output'), 90),
            'differences': differences,
            'correct': correct,
        })
    return cases


def render_cases(cases):
    lines = ['| 样本 | split | 输入 | 金标 | 实际 | 差异字段 | 判定 |',
             '|---|---|---|---|---|---|---|']
    for case in cases:
        lines.append(f"| {case['id']} | {case['split'] or ''} | {case['input']} | {case['gold']} | "
                     f"{case['actual']} | {', '.join(case['differences']) or '—'} | "
                     f"{'正确' if case['correct'] else '错误'} |")
    correct = [case['id'] for case in cases if case['correct']]
    wrong = [case['id'] for case in cases if not case['correct']]
    lines.append('')
    lines.append(f"正确 {len(correct)} 条：{', '.join(correct) or '无'}；"
                 f"错误 {len(wrong)} 条：{', '.join(wrong) or '无'}")
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