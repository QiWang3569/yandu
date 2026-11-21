"""Compare frozen smart-search outputs with retrieval using the identical parsed intents."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]
from evals.common import read_json, write_json
from evals.search_eval import SearchContext
from app.search_intent import SearchFilters
from app.search import execute_smart_search, search_items_by_intent


def compare(run, destination, verify_baseline=False, baseline_replay=None):
    manifest = read_json(run / 'manifest.json')
    if not manifest['complete']:
        raise ValueError('Incomplete source run')
    cases = {c['id']: c for c in read_json(run / 'cases.json')}
    catalog = read_json(run / 'catalog.json')
    titles = {i['id']: i['title'] for i in catalog['items']}
    context = SearchContext(catalog)
    groups = defaultdict(Counter)
    changes = []
    remaining_errors = []
    settings = SimpleNamespace(demo_mode=True)
    previous = read_json(baseline_replay) if baseline_replay else None
    if previous and previous['run'] != manifest['run_id']:
        raise ValueError('The baseline replay must use the same source run')
    previous_changes = {(c['model'], c['case'], c['repeat']): c for c in previous['changes']} if previous else {}

    def products(ids):
        return [{'id': key, 'title': titles[key]} for key in sorted(ids)]

    try:
        with (run / 'records.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                r = json.loads(line)
                if r['task'] != 'smart_search':
                    continue
                group = groups[r['model']]
                target = cases[r['case_id']]['expected']
                if not target['retrieval_applicable']:
                    group['parse_only'] += 1
                    continue
                if r['status'] != 'ok' or not r['score']['metrics']['schema_valid']:
                    group['execution_errors'] += 1
                    continue
                group['compared'] += 1
                fields = dict(r['output']['parsed'])
                around = fields.pop('around_price')
                intent = SearchFilters.model_validate({**fields, 'around_price': around})
                before = r['output']['ranked_item_ids']
                query = cases[r['case_id']]['input']['text']
                effective = {**fields, 'around_price': around}
                if previous:
                    change = previous_changes.pop((r['model'], r['case_id'], r['repeat']), None)
                    if change:
                        if change['before'] != before:
                            raise ValueError('Source ranking differs from the baseline replay')
                        before = change['after']
                    effective, ranked, _ = execute_smart_search(
                        context.session, query, settings, parser=lambda *_: intent, size=len(titles),
                    )
                else:
                    ranked, _ = search_items_by_intent(
                        context.session, intent, settings, around=around, size=len(titles),
                    )
                after = [item.id for item, _ in ranked]
                if verify_baseline and before != after:
                    raise ValueError(f"Baseline mismatch: {r['model']} {r['case_id']}")
                gold = set(target['relevant_item_ids'])
                old, new = set(before), set(after)
                for label, ids in [('before',old), ('after',new)]:
                    group[label+'_extra_queries'] += bool(ids - gold)
                    group[label+'_miss_queries'] += bool(gold - ids)
                    group[label+'_extra_items'] += len(ids - gold)
                    group[label+'_miss_items'] += len(gold - ids)
                    group[label+'_exact'] += ids == gold
                introduced = (new-old)-gold
                lost = (old-new)&gold
                group['new_false_positives'] += len(introduced)
                group['lost_true_positives'] += len(lost)
                case_info = {'model': r['model'], 'case': r['case_id'], 'repeat': r['repeat'],
                             'query': cases[r['case_id']]['input']['text']}
                if new != gold:
                    remaining_errors.append({
                        **case_info, 'parsed': fields, 'effective': effective, 'extra': products(new - gold),
                        'missing': products(gold - new), 'newly_missing': products(lost),
                    })
                if before != after:
                    changes.append({
                        **case_info, 'before': before, 'after': after,
                        'new_false_positives': sorted(introduced), 'lost_true_positives': sorted(lost),
                        'fixed_extra': products((old - new) - gold), 'recovered': products((new - old) & gold),
                        'parsed': fields, 'effective': effective,
                    })
    finally:
        context.close()
    if previous:
        if previous_changes or set(groups) != set(previous['models']):
            raise ValueError('The compared record keys differ from the baseline replay')
        for model, counts in groups.items():
            for key in ('compared', 'before_exact', 'before_extra_queries', 'before_miss_queries',
                        'before_extra_items', 'before_miss_items'):
                if counts[key] != previous['models'][model][key.replace('before_', 'after_')]:
                    raise ValueError(f'Frozen baseline mismatch for {model} {key}')
    write_json(destination, {'run': manifest['run_id'], 'models': dict(groups),
                             'baseline_replay': baseline_replay.name if previous else None,
                             'titles': titles, 'changes': changes, 'remaining_errors': remaining_errors})


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--verify-baseline', action='store_true')
    p.add_argument('--baseline-replay', type=Path, help='Compare the live search entry point with a first-stage replay')
    args = p.parse_args()
    compare(args.run, args.output, args.verify_baseline, args.baseline_replay)
