"""Export shareable aggregates from a completed run, without dataset text or model replies.

Pairwise bootstrap keeps all repeats and paraphrases within their original family.
It describes uncertainty on this development set; it does not create a holdout.
"""
import argparse
import hashlib
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'backend'))
from evals.common import digest, read_json, write_json
from evals.reporting import _gate, _percentile


def average(values):
    return sum(values) / len(values) if values else None


def parse_pass(row):
    checks = [c for c in row['score']['checks'] if c['field'] not in {'retrieval_exact', 'around_price'}]
    return row['status'] == 'ok' and bool(checks) and all(c['passed'] for c in checks)


def basic(rows):
    return {
        'records': len(rows), 'cases': len({r['case_id'] for r in rows}),
        'passed': sum(r['status'] == 'ok' and r['score']['passed'] for r in rows),
        'pass_rate': average([r['status'] == 'ok' and r['score']['passed'] for r in rows]),
        'error_count': sum(r['status'] != 'ok' for r in rows),
        'errors': dict(Counter(r['error'] for r in rows if r['status'] != 'ok')),
        'p50_latency_ms': _percentile([r['latency_ms'] for r in rows], .5),
        'p95_latency_ms': _percentile([r['latency_ms'] for r in rows], .95),
    }


def model_diagnostics(rows, cases):
    from evals.adapters import ParsedIntent, ParsedItem
    attempts = [a for r in rows for a in r.get('attempts', [])]
    usages = [a['usage'] for a in attempts if isinstance(a.get('usage'), dict)]
    counts = {}
    for name in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        known = [u[name] for u in usages if isinstance(u.get(name), int)]
        counts[name] = {'reported_sum': sum(known), 'known_attempts': len(known)}
    counts['nonadditive_attempts'] = sum(
        all(isinstance(u.get(k), int) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
        and u['prompt_tokens'] + u['completion_tokens'] != u['total_tokens'] for u in usages)
    counts['cache_partition_mismatches'] = sum(
        all(isinstance(u.get(k), int) for k in ('prompt_tokens', 'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens'))
        and u['prompt_cache_hit_tokens'] + u['prompt_cache_miss_tokens'] != u['prompt_tokens'] for u in usages)
    search = [r for r in rows if r['task'] == 'smart_search']
    partitions = defaultdict(list)
    for r in rows:
        tags = cases[r['case_id']]['tags']
        part = 'taodescribe' if 'taodescribe' in tags else r['task']
        partitions[part].append(r)
    fence_decodable, fence_schema_checked, fence_schema_valid = 0, 0, 0
    schema_issues = Counter()
    for row in rows:
        schema = ParsedItem if row['task'] == 'item_parse' else ParsedIntent
        is_parse = row['task'] in {'smart_search', 'intent_parse', 'item_parse', 'wanted_parse'}
        if row.get('error') == 'invalid_json_response':
            match = re.fullmatch(r'\s*```(?:json)?\s*\n(.*?)\n```\s*', row.get('raw_content') or '', re.S)
            if match:
                try:
                    decoded = json.loads(match.group(1))
                    json.dumps(decoded, allow_nan=False)
                    if isinstance(decoded, dict):
                        fence_decodable += 1
                        if is_parse:
                            fence_schema_checked += 1
                            schema.model_validate(decoded)
                            fence_schema_valid += 1
                except (ValueError, TypeError):
                    pass
        if row.get('error') == 'schema_error' and is_parse:
            try:
                schema.model_validate(row.get('raw_output'))
            except ValueError as exc:
                if hasattr(exc, 'errors'):
                    for issue in exc.errors(include_input=False):
                        schema_issues[(row['task'], '.'.join(map(str, issue['loc'])) or '<object>', issue['type'])] += 1
    return {
        **basic(rows), 'partitions': {k: basic(v) for k, v in sorted(partitions.items())},
        'by_repeat': {str(i): basic([r for r in rows if r['repeat'] == i])
                      for i in sorted({r['repeat'] for r in rows})},
        'search_parse_pass_count': sum(parse_pass(r) for r in search),
        'search_parse_pass_rate': average([parse_pass(r) for r in search]),
        'search_count': len(search),
        'returned_models': dict(Counter(a.get('returned_model') for a in attempts)),
        'reasoning_token_positive_attempts': sum(
            ((a.get('usage') or {}).get('completion_tokens_details') or {}).get('reasoning_tokens', 0) > 0
            for a in attempts),
        'reasoning_text_positive_attempts': sum((a.get('reasoning_char_count') or 0) > 0 for a in attempts),
        'reasoning_token_known_attempts': sum(
            'reasoning_tokens' in ((a.get('usage') or {}).get('completion_tokens_details') or {}) for a in attempts),
        'attempt_count': len(attempts), 'usage': counts,
        'fenced_json_failures': sum(r.get('error') == 'invalid_json_response'
            and (r.get('raw_content') or '').lstrip().startswith('```') for r in rows),
        'fence_diagnostic_only': {'decodable_objects': fence_decodable,
            'parse_schema_checked': fence_schema_checked, 'parse_schema_valid': fence_schema_valid,
            'note': 'Only a full enclosing code fence is removed offline. No experiment score is replaced; '
                    'schema validity does not establish semantic correctness.'},
        'schema_issues': [{'task': t, 'field': f, 'type': kind, 'count': count}
                          for (t, f, kind), count in sorted(schema_issues.items())],
    }


def paired_bootstrap(rows_a, rows_b, cases, metric, iterations, seed):
    def values(rows):
        by_case = defaultdict(list)
        for row in rows:
            value = (float(row['status'] == 'ok' and row['score']['passed']) if metric == 'pass_rate'
                     else row['score']['metrics'].get(metric))
            if value is not None:
                by_case[row['case_id']].append(value)
        return {cid: average(values) for cid, values in by_case.items()}
    a, b = values(rows_a), values(rows_b)
    if set(a) != set(b):
        raise ValueError('Paired metric requires the same eligible cases')
    if not a:
        raise ValueError('Paired metric has no eligible cases')
    families = defaultdict(list)
    for cid in sorted(a):
        families[cases[cid]['family']].append(a[cid] - b[cid])
    clusters = [(sum(v), len(v)) for v in families.values()]
    rng = random.Random(seed)
    simulated = []
    for _ in range(iterations):
        selected = rng.choices(clusters, k=len(clusters))
        simulated.append(sum(x for x, _ in selected) / sum(n for _, n in selected))
    return {
        'difference_a_minus_b': average([a[cid] - b[cid] for cid in a]),
        'ci95_low': _percentile(simulated, .025), 'ci95_high': _percentile(simulated, .975),
        'cases': len(a), 'families': len(families), 'resamples': iterations, 'seed': seed,
    }


def export(run, destination, iterations=5000, seed=20261115):
    manifest = read_json(run / 'manifest.json')
    if not manifest.get('complete'):
        raise ValueError('Export requires a completed run')
    cases = {c['id']: c for c in read_json(run / 'cases.json')}
    summary = read_json(run / 'summary.json')
    policy = read_json(run / 'policy.json')
    rows = [json.loads(line) for line in (run / 'records.jsonl').read_text(encoding='utf-8').splitlines()]
    profiles = {p['id']: p for p in manifest['models']}
    expected = {(m, c['id'], repeat) for m, p in profiles.items() for c in cases.values()
                if c['task'] in p['tasks'] for repeat in range(1, manifest['repeats'] + 1)}
    actual = {(r['model'], r['case_id'], r['repeat']) for r in rows}
    if not manifest.get('complete') or len(rows) != len(expected) or actual != expected:
        raise ValueError('Export requires a complete, unique case/model/repeat matrix')
    if not summary.get('complete') or summary['record_count'] != len(rows):
        raise ValueError('Summary does not match the completed records')
    if any(r['case_hash'] != digest(cases[r['case_id']]) for r in rows):
        raise ValueError('Case snapshot hash mismatch')
    by_model = {m: [r for r in rows if r['model'] == m] for m in profiles}
    diagnostics = {m: model_diagnostics(rs, cases) for m, rs in by_model.items()}
    searches = {m: [r for r in rs if r['task'] == 'smart_search'] for m, rs in by_model.items()
                if profiles[m]['mode'] == 'remote'}
    comparisons = []
    for a, b in combinations(sorted(searches), 2):
        for metric in ('pass_rate', 'mrr', 'ap_at_5', 'recall_at_10'):
            comparisons.append({'a': a, 'b': b, 'metric': metric,
                **paired_bootstrap(searches[a], searches[b], cases, metric, iterations, seed)})
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Export destination must be empty')
    destination.mkdir(parents=True, exist_ok=True)
    provenance = {k: v for k, v in manifest.items() if k not in {'catalog', 'cases', 'relations'}}
    provenance['cases'] = [{k: c[k] for k in ('id', 'task', 'split', 'family', 'label_status', 'tags', 'source')}
                           | {'hash': digest(c)} for c in cases.values()]
    provenance['raw_record_sha256'] = hashlib.sha256((run / 'records.jsonl').read_bytes()).hexdigest()
    provenance['analysis_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance['raw_records_local_directory'] = str(run.resolve())
    if (run / 'environment.json').exists():
        provenance['environment'] = read_json(run / 'environment.json')
    write_json(destination / 'provenance.json', provenance)
    write_json(destination / 'summary.json', summary)
    write_json(destination / 'policy.json', policy)
    search_rules = policy.get('tasks', {}).get('smart_search')
    gates = {g['model']: _gate(g, search_rules) for g in summary['groups']
             if search_rules and g['task'] == 'smart_search' and profiles[g['model']]['mode'] == 'remote'}
    write_json(destination / 'analysis.json', {'models': diagnostics, 'paired_search_bootstrap': comparisons,
        'search_draft_gate_failures': gates, 'frozen_search_rules': search_rules,
        'bootstrap_note': 'Post-hoc paired family-cluster bootstrap; all repeats and paraphrases stay together. '
                          'Unadjusted 95% intervals, not independent tests or holdout evidence.'})
    print(json.dumps({'run_id': manifest['run_id'], 'records': len(rows), 'output': str(destination.resolve())}, ensure_ascii=False))


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.run, args.output)
