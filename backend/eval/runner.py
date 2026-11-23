"""Run a dataset split through one node and compute pre-registered metrics."""
import time
from datetime import datetime, timezone

from . import adapters, datasets, metrics


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def call_with_retry(call, attempts=3, backoff=0.5, sleep=time.sleep):
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            return call(), None, attempt
        except Exception as exc:  # provider or validation failure; sanitized downstream
            errors.append(type(exc).__name__)
            if attempt < attempts:
                sleep(backoff * 2 ** (attempt - 1))
    return None, errors[-1], attempts


def dispatch(node, row, settings, sink):
    if node == '1.1':
        return adapters.run_item(row['input']['raw'], settings, sink)
    if node == '1.2':
        return adapters.run_vision(row['input']['images'], row['input'].get('note', ''), settings, sink)
    if node == '2.1':
        return adapters.run_intent(row['input']['query'], settings, sink)
    if node == '2.3':
        return adapters.run_recall(row, datasets.load_pool(), sink)
    if node == '2.4':
        return adapters.run_review(row['input']['intent'], row['input']['item'], settings, sink)
    raise KeyError(node)


def fixture_output(node, row):
    gold = row['gold']
    if node == '1.1':
        return {'title': gold.get('title'), 'category': gold.get('category'),
                'price': gold.get('price'), 'campus': gold.get('campus'),
                'condition_grade': gold.get('condition_grade'), 'tags': gold.get('tags', []),
                'clarification': 'fixture clarification' if gold.get('clarification_required') else None}
    if node == '1.2':
        return {'status': gold['status'], 'title': gold.get('title'), 'category': gold.get('category'),
                'description': 'fixture draft', 'tags': gold.get('tags', []),
                'uncertainties': gold.get('uncertainties', [])}
    if node == '2.1':
        return {key: gold.get(key) for key in ('category', 'max_price', 'campus', 'keywords',
                                               'excluded_keywords', 'preferences', 'condition_grade')} | {
            'clarification': 'fixture clarification' if gold.get('clarification_required') else None,
            'quotes': gold.get('gold_quotes', []),
        }
    if node == '2.3':
        return adapters.run_recall(row, datasets.load_pool(), [])
    if node == '2.4':
        item = row['input']['item']
        verdict = gold['verdict']
        evidence = []
        if verdict != 'UNCERTAIN':
            term = (row['input']['intent'].get('keywords') or ['商品'])[0]
            source = item['title'] if term in item['title'] else item['description']
            evidence = [{'criterion': term, 'quote': source[:160]}]
        return {'item_id': item['id'], 'verdict': verdict, 'evidence': evidence,
                'questions': [] if verdict != 'UNCERTAIN' else ['请确认商品是否满足要求？']}
    raise KeyError(node)


def run_node(node, split, settings, candidate, fixture=False, attempts=3, sleep=time.sleep):
    rows = datasets.load_rows(node, split)
    if not rows:
        raise ValueError(f'{node} has no rows for split {split}')
    problems = datasets.validate_rows(node, rows)
    if problems:
        raise ValueError('; '.join(problems))
    results = []
    for row in rows:
        sink = []
        started = time.monotonic()
        if fixture:
            try:
                output, error, used = fixture_output(node, row), None, 1
            except Exception as exc:
                output, error, used = None, type(exc).__name__, 1
        else:
            output, error, used = call_with_retry(
                lambda row=row, sink=sink: dispatch(node, row, settings, sink), attempts, 0.5, sleep)
        results.append({
            'id': row['id'],
            'split': row['split'],
            'stratum': row.get('stratum'),
            'ok': output is not None,
            'output': output,
            'error': error,
            'attempts': used,
            'latency_ms': (time.monotonic() - started) * 1000,
            'events': sink,
        })
    return {
        'node': node,
        'split': split,
        'candidate': candidate['id'] if candidate else 'fixture',
        'model': candidate.get('model') if candidate else 'fixture',
        'fixture': fixture,
        'started_at': now_iso(),
        'samples': results,
        'usage': aggregate_usage(results),
        'metrics': summarize(node, rows, results),
    }


def _num(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize(node, rows, results):
    if node == '1.1':
        return summarize_item(rows, results)
    if node == '2.1':
        return summarize_intent(rows, results)
    if node == '2.4':
        return summarize_review(rows, results)
    if node == '2.3':
        return summarize_recall(rows, results)
    if node == '1.2':
        return summarize_vision(rows, results)
    return {}


def _latency(results):
    return metrics.percentile([result['latency_ms'] for result in results], 95)


def summarize_item(rows, results):
    category, price, campus, condition, tags, clarification, valid = [], [], [], [], [], [], []
    for row, result in zip(rows, results):
        gold = row['gold']
        out = result['output'] or {}
        valid.append(result['ok'])
        category.append((gold.get('category'), out.get('category')))
        price.append((_num(gold.get('price')), _num(out.get('price'))))
        campus.append((gold.get('campus'), out.get('campus')))
        condition.append((gold.get('condition_grade'), out.get('condition_grade')))
        tags.append((set(gold.get('tags', [])), set(out.get('tags') or [])))
        clarification.append((bool(gold.get('clarification_required')), bool(out.get('clarification'))))
    summary = {
        'valid_rate': metrics.rate(valid),
        'category_accuracy': metrics.exact_rate(category),
        'price_accuracy': metrics.exact_rate(price),
        'campus_accuracy': metrics.exact_rate(campus),
        'condition_accuracy': metrics.exact_rate(condition),
        'tags_macro_f1': metrics.macro_f1(tags),
        'clarification_accuracy': metrics.exact_rate(clarification),
        'p95_latency_ms': _latency(results),
    }
    summary['field_macro_f1'] = metrics.mean([summary['category_accuracy'], summary['price_accuracy'],
                                              summary['campus_accuracy'], summary['condition_accuracy'],
                                              summary['tags_macro_f1']])
    return summary


def summarize_intent(rows, results):
    category, price, campus, condition = [], [], [], []
    keywords, exclusions, preferences, valid, injection = [], [], [], [], []
    quotes = []
    for row, result in zip(rows, results):
        gold = row['gold']
        out = result['output'] or {}
        valid.append(result['ok'])
        category.append((gold.get('category'), out.get('category')))
        price.append((_num(gold.get('max_price')), _num(out.get('max_price'))))
        campus.append((gold.get('campus'), out.get('campus')))
        condition.append((gold.get('condition_grade'), out.get('condition_grade')))
        keywords.append((set(gold.get('keywords', [])), set(out.get('keywords') or [])))
        exclusions.append((set(gold.get('excluded_keywords', [])), set(out.get('excluded_keywords') or [])))
        preferences.append((set(gold.get('preferences', [])), set(out.get('preferences') or [])))
        quotes.append(metrics.quote_recall(gold.get('gold_quotes', []), out.get('quotes') or []))
        if row.get('stratum') == 'injection':
            injection.append(
                (gold.get('category'), gold.get('max_price'), gold.get('campus'), gold.get('condition_grade'),
                 tuple(sorted(gold.get('keywords', []))), tuple(sorted(gold.get('excluded_keywords', []))),
                 tuple(sorted(gold.get('preferences', [])))) ==
                (out.get('category'), _num(out.get('max_price')), out.get('campus'), out.get('condition_grade'),
                 tuple(sorted(out.get('keywords') or [])), tuple(sorted(out.get('excluded_keywords') or [])),
                 tuple(sorted(out.get('preferences') or []))))
    summary = {
        'valid_rate': metrics.rate(valid),
        'category_accuracy': metrics.exact_rate(category),
        'price_accuracy': metrics.exact_rate(price),
        'campus_accuracy': metrics.exact_rate(campus),
        'condition_accuracy': metrics.exact_rate(condition),
        'keywords_f1': metrics.macro_f1(keywords),
        'exclusions_f1': metrics.macro_f1(exclusions),
        'preferences_f1': metrics.macro_f1(preferences),
        'quote_recall': metrics.mean(quotes),
        'injection_structure_rate': metrics.rate(injection),
        'p95_latency_ms': _latency(results),
    }
    summary['field_macro_f1'] = metrics.mean([summary['keywords_f1'], summary['exclusions_f1'],
                                              summary['preferences_f1']])
    summary['hard_field_exact'] = metrics.mean([summary['category_accuracy'], summary['price_accuracy'],
                                                summary['campus_accuracy'], summary['condition_accuracy']])
    return summary


def summarize_vision(rows, results):
    status, category, valid, unsupported = [], [], [], []
    for row, result in zip(rows, results):
        gold = row['gold']
        out = result['output'] or {}
        valid.append(result['ok'])
        status.append((gold['status'], out.get('status')))
        if gold['status'] == 'ready':
            category.append((gold.get('category'), out.get('category')))
            forbidden = gold.get('forbidden_terms', [])
            text = ' '.join(filter(None, [out.get('title'), out.get('description'), *(out.get('tags') or [])]))
            unsupported.append(any(term.lower() in text.lower() for term in forbidden))
    summary = {
        'valid_rate': metrics.rate(valid),
        'status_accuracy': metrics.exact_rate(status),
        'category_accuracy': metrics.exact_rate(category),
        'unsupported_attribute_rate': metrics.rate(unsupported),
        'p95_latency_ms': _latency(results),
    }
    return summary


def summarize_review(rows, results):
    verdicts, match_cases, valid, grounding, exclusion_accepts, preference_rejects = [], [], [], [], 0, 0
    for row, result in zip(rows, results):
        gold = row['gold']['verdict']
        out = result['output'] or {}
        predicted = out.get('verdict')
        valid.append(result['ok'])
        verdicts.append((gold, predicted))
        if gold == 'MATCH':
            match_cases.append(gold == predicted)
            if predicted == 'NO_MATCH' and row['gold'].get('preference_missing'):
                preference_rejects += 1
        if gold == 'NO_MATCH' and predicted == 'MATCH':
            exclusion_accepts += 1
        quotes = [evidence.get('quote', '') for evidence in out.get('evidence') or []]
        sources = [row['input']['item']['title'], row['input']['item']['description'],
                   *row['input']['item'].get('tags', [])]
        grounding.append(metrics.grounding_rate(quotes, sources))
    return {
        'valid_rate': metrics.rate(valid),
        'verdict_accuracy': metrics.exact_rate(verdicts),
        'match_recall': metrics.rate(match_cases),
        'grounding_rate': metrics.mean(grounding),
        'exclusion_false_accept': exclusion_accepts,
        'preference_only_reject': preference_rejects,
        'p95_latency_ms': _latency(results),
    }


def summarize_recall(rows, results):
    recalls, valid = [], []
    for row, result in zip(rows, results):
        valid.append(result['ok'])
        ranked = (result['output'] or {}).get('ranked', [])
        recalls.append(metrics.recall_at_k(row['gold']['relevant'], ranked, 10))
    return {
        'valid_rate': metrics.rate(valid),
        'recall_at_10': metrics.mean(recalls),
        'p95_latency_ms': _latency(results),
    }


def aggregate_usage(results):
    totals = {'calls': 0, 'input_tokens': 0, 'output_tokens': 0, 'failures': 0}
    for result in results:
        if not result['ok']:
            totals['failures'] += 1
        for event in result['events']:
            if event.get('node') not in ('chat', 'vision', 'embedding'):
                continue
            totals['calls'] += 1
            usage = event.get('usage') or {}
            totals['input_tokens'] += int(usage.get('prompt_tokens') or usage.get('input_tokens') or 0)
            totals['output_tokens'] += int(usage.get('completion_tokens') or usage.get('output_tokens') or 0)
    return totals


def evaluate_checks(metrics_by_node, thresholds):
    checks = {}
    for node, node_metrics in metrics_by_node.items():
        rules = {**thresholds.get('global', {}), **thresholds.get(node, {})}
        checks[node] = {}
        for name, rule in rules.items():
            value = node_metrics.get(name)
            checks[node][name] = {'value': value, 'rule': rule, 'pass': metrics.passes(value, rule)}
    return checks