"""Aggregate field diagnostics without changing existing assertion pass rules."""
from collections import defaultdict
from decimal import Decimal

from .common import canonical_json
from .schema import normalize_term, validate_business_payload


def parse_diagnostics(case, output, error):
    target = case['expected']
    valid = error is None
    try:
        validate_business_payload(case['task'], output, output=True)
    except (ValueError, TypeError):
        valid = False
    result = {'field_results': {}, 'set_counts': {}, 'clarification_result': None}
    for field, expected in target.get('fields', {}).items():
        actual = output.get(field) if valid else None
        present = valid and field in output
        if field in {'price', 'max_price', 'budget'}:
            expected = str(Decimal(str(expected)).normalize()) if expected is not None else None
            actual = str(Decimal(str(actual)).normalize()) if actual is not None else None
        result['field_results'][field] = dict(expected=expected, actual=actual, valid=bool(present),
                                             passed=bool(present and expected == actual))
    for field, groups in target.get('sets', {}).items():
        if not valid or field not in output:
            result['set_counts'][field] = dict(tp=0, fp=1, fn=len(groups), f1=0.0, valid=False)
            continue
        terms = [normalize_term(t) for t in output[field]]
        used = set()
        for alternatives in groups:
            accepted = {normalize_term(t) for t in alternatives}
            match = next((i for i, t in enumerate(terms) if i not in used and t in accepted), None)
            if match is not None:
                used.add(match)
        tp, fp, fn = len(used), len(terms) - len(used), len(groups) - len(used)
        result['set_counts'][field] = dict(tp=tp, fp=fp, fn=fn, valid=True,
                                          f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0)
    if 'clarification' in target:
        result['clarification_result'] = dict(expected=target['clarification'],
            actual=bool(output.get('clarification') and output['clarification'].strip()) if valid else None,
            valid=valid and 'clarification' in output)
    return result


def aggregate_fields(rows):
    fields, sets, clarification = defaultdict(list), defaultdict(list), []
    for row in rows:
        metrics = (row.get('score') or {}).get('metrics', {})
        for field, pair in metrics.get('field_results', {}).items():
            fields[field].append(pair)
        for field, counts in metrics.get('set_counts', {}).items():
            sets[field].append(counts)
        if metrics.get('clarification_result') is not None:
            clarification.append(metrics['clarification_result'])
    result = {'fields': {}, 'sets': {}, 'clarification': None}
    for field, pairs in fields.items():
        labels = sorted({canonical_json(p['expected']) for p in pairs})
        f1s, supports = [], {}
        for label in labels:
            tp = sum(p['valid'] and canonical_json(p['actual']) == label == canonical_json(p['expected']) for p in pairs)
            fp = sum(p['valid'] and canonical_json(p['actual']) == label != canonical_json(p['expected']) for p in pairs)
            fn = sum(canonical_json(p['expected']) == label and (not p['valid'] or canonical_json(p['actual']) != label) for p in pairs)
            f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
            supports[label] = tp + fn
        result['fields'][field] = {'count': len(pairs), 'accuracy': sum(p['passed'] for p in pairs) / len(pairs),
            'macro_f1': sum(f1s) / len(f1s) if field in {'category', 'campus', 'condition_grade'} else None,
            'label_support': supports}
    for field, counts in sets.items():
        tp, fp, fn = (sum(c[k] for c in counts) for k in ('tp', 'fp', 'fn'))
        result['sets'][field] = {'count': len(counts), 'tp': tp, 'fp': fp, 'fn': fn,
            'micro_precision': tp / (tp + fp) if tp + fp else 1.0,
            'micro_recall': tp / (tp + fn) if tp + fn else 1.0,
            'micro_f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 1.0,
            'macro_f1': sum(c['f1'] for c in counts) / len(counts)}
    if clarification:
        tp = sum(p['valid'] and p['actual'] is True and p['expected'] for p in clarification)
        fp = sum(not p['expected'] and p['valid'] and p['actual'] is True for p in clarification)
        fn = sum(p['expected'] and (not p['valid'] or p['actual'] is not True) for p in clarification)
        result['clarification'] = {'count': len(clarification), 'tp': tp, 'fp': fp, 'fn': fn,
            'f1': 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            'positive_count': sum(p['expected'] for p in clarification),
            'invalid_count': sum(not p['valid'] for p in clarification),
            'accuracy': sum(p['valid'] and p['actual'] == p['expected'] for p in clarification) / len(clarification)}
    return result


def consistency(rows, manifest):
    if manifest.get('repeats', 1) < 2:
        return {'consistency_rate': None, 'consistency_case_count': 0}
    first = rows[0]
    profiles = {p['id']: p for p in manifest.get('models', [])}
    expected = [c['id'] for c in manifest['cases'] if c['task'] == first['task'] and c['split'] == first['split']
                and c['task'] in profiles.get(first['model'], {}).get('tasks', [first['task']])]
    by_case = defaultdict(list)
    for row in rows:
        by_case[row['case_id']].append(row)
    consistent = 0
    for cid in expected:
        attempts = by_case[cid]
        if (len(attempts) == manifest['repeats'] and {r['repeat'] for r in attempts} == set(range(1, manifest['repeats'] + 1))
            and all(r['status'] == 'ok' and r.get('output') is not None for r in attempts)
            and len({canonical_json(r['output']) for r in attempts}) == 1):
            consistent += 1
    return {'consistency_rate': consistent / len(expected) if expected else None,
            'consistency_case_count': len(expected), 'consistent_case_count': consistent}


def baseline_comparisons(records, manifest):
    profiles = {p['id']: p for p in manifest['models']}
    groups = defaultdict(list)
    for r in records:
        groups[r['model'], r['task'], r['split']].append(r)
    result = []
    for (baseline, task, split), base_rows in groups.items():
        if profiles[baseline]['mode'] != 'local':
            continue
        base = {(r['case_id'], r['repeat']): r for r in base_rows}
        for (model, other_task, other_split), rows in groups.items():
            if model == baseline or (other_task, other_split) != (task, split):
                continue
            current = {(r['case_id'], r['repeat']): r for r in rows}
            if set(current) != set(base):
                continue
            a = sum(r['status'] == 'ok' and r['score']['passed'] for r in base_rows) / len(base_rows)
            b = sum(r['status'] == 'ok' and r['score']['passed'] for r in rows) / len(rows)
            item = dict(baseline=baseline, model=model, task=task, split=split, count=len(rows),
                pass_rate_gain=b-a, error_rate_reduction=(b-a)/(1-a) if a < 1 else None)
            for metric in ('mrr', 'ap_at_5', 'recall_at_10'):
                pairs = [(base[k]['score']['metrics'].get(metric), current[k]['score']['metrics'].get(metric)) for k in base]
                pairs = [(x, y) for x, y in pairs if x is not None and y is not None]
                item[metric + '_gain'] = sum(y-x for x,y in pairs) / len(pairs) if pairs else None
            result.append(item)
    return result
