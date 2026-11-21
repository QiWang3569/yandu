"""Fixed-catalog evaluation using the production parser and complete search results.

Only an isolated in-memory database is used. Relevance labels are authored outside
the search implementation; the oracle injects gold intent, never gold result IDs.
"""
import copy
from datetime import datetime
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Literal

from pydantic import Field, model_validator

from .common import digest, read_json
from .schema import CandidateItem, Case, Nonempty, ParseExpected, ParseInput, Strict, normalize_term, validate_business_payload


class SearchExpected(Strict):
    parse: ParseExpected
    oracle_intent: dict
    relevant_item_ids: list[Nonempty]
    retrieval_applicable: bool = True
    around_price: bool = False
    min_price: float | None = Field(default=None, ge=0)


def validate_search_case(case):
    ParseInput.model_validate(case['input'])
    target = SearchExpected.model_validate(case['expected'])
    if len(set(target.relevant_item_ids)) != len(target.relevant_item_ids):
        raise ValueError('Duplicate relevant item IDs')
    if not target.retrieval_applicable and target.relevant_item_ids:
        raise ValueError('Non-retrieval cases must have empty relevance labels')
    if set(target.oracle_intent) != {'category', 'max_price', 'campus', 'condition_grade',
                                      'keywords', 'excluded_keywords', 'preferences', 'clarification'}:
        raise ValueError('Oracle intent must explicitly specify all eight fields')
    validate_business_payload('intent_parse', target.oracle_intent)
    # Reuse all existing parse-label validation, including synonyms and negations.
    Case.model_validate({**case, 'task': 'intent_parse', 'expected': case['expected']['parse']})


class CatalogItem(CandidateItem):
    created_at: Nonempty
    status: Literal['ACTIVE', 'RESERVED', 'SOLD'] = 'ACTIVE'

    @model_validator(mode='after')
    def timestamp(self):
        stamp = datetime.fromisoformat(self.created_at)
        if stamp.tzinfo is not None:
            raise ValueError('Catalog timestamps use fixed naive UTC values')
        if self.category is None:
            raise ValueError('Catalog items require a category')
        return self


class Catalog(Strict):
    version: Nonempty
    description: Nonempty
    label_status: Literal['draft', 'reviewed']
    items: list[CatalogItem] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def unique(self):
        if len({x.id for x in self.items}) != len(self.items):
            raise ValueError('Duplicate catalog item IDs')
        if len({x.created_at for x in self.items}) != len(self.items):
            raise ValueError('Use distinct fixed timestamps to make sorting ties reproducible')
        return self


class Relation(Strict):
    id: Nonempty
    base: Nonempty
    mutated: Nonempty
    relation: Literal['invariant', 'subset']
    rationale: Nonempty
    max_price_cents: int | None = Field(default=None, ge=0)
    forbidden_item_ids: list[Nonempty] = Field(default_factory=list)

    @model_validator(mode='after')
    def constraints(self):
        if self.base == self.mutated:
            raise ValueError('A relation needs distinct cases')
        if self.relation == 'subset' and self.max_price_cents is None and not self.forbidden_item_ids:
            raise ValueError('Subset relation requires a budget or explicit forbidden IDs')
        if self.relation == 'invariant' and (self.max_price_cents is not None or self.forbidden_item_ids):
            raise ValueError('Invariant relations cannot add constraints')
        return self


def load_search_assets(cases, catalog_path, relations_path=None):
    search_cases = {c['id']: c for c in cases if c['task'] == 'smart_search'}
    if not search_cases:
        if relations_path:
            raise ValueError('Relations require smart_search cases')
        return None, []
    if not catalog_path:
        raise ValueError('smart_search requires --catalog')
    catalog = Catalog.model_validate(read_json(catalog_path)).model_dump(mode='json')
    ids = {i['id'] for i in catalog['items']}
    from .scoring import score_case
    for case in search_cases.values():
        if set(case['expected']['relevant_item_ids']) - ids:
            raise ValueError(f'{case["id"]}: relevant item missing from catalog')
        parse_case = {**case, 'task': 'intent_parse', 'expected': case['expected']['parse']}
        if not score_case(parse_case, case['expected']['oracle_intent'])['passed']:
            raise ValueError(f'{case["id"]}: oracle intent contradicts parse annotations')
    relations = []
    if relations_path:
        source = read_json(relations_path)
        if not isinstance(source, dict) or set(source) != {'version', 'relations'} or source['version'] != 1:
            raise ValueError('Relations require version=1 and relations')
        relations = [Relation.model_validate(row).model_dump(mode='json') for row in source['relations']]
        if len({r['id'] for r in relations}) != len(relations):
            raise ValueError('Duplicate relation IDs')
        for relation in relations:
            if {relation['base'], relation['mutated']} - set(search_cases):
                raise ValueError('Relation references missing search cases')
            a, b = (search_cases[relation[k]] for k in ('base', 'mutated'))
            if (a['split'], a['family']) != (b['split'], b['family']):
                raise ValueError('Related cases must share split and family')
            if set(relation['forbidden_item_ids']) - ids:
                raise ValueError('Relation references unknown forbidden items')
    return catalog, relations


class SearchContext:
    def __init__(self, catalog):
        # Use the same module namespace as the serving parser imported by adapters.
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from app.models import Item
        self.catalog = catalog
        self.engine = create_engine('sqlite+pysqlite:///:memory:')
        Item.__table__.create(self.engine)
        self.session = Session(self.engine)
        for data in catalog['items']:
            values = {**data, 'created_at': datetime.fromisoformat(data['created_at']), 'seller_id': 'eval-seller'}
            self.session.add(Item(**values))
        self.session.commit()

    def close(self):
        self.session.close()
        self.engine.dispose()


def evaluate_search(case, profile, key, context, *, client, sleep):
    from .adapters import evaluate
    from fastapi import HTTPException
    from app.schemas import ParsedIntent
    from app.search_intent import SearchFilters
    from app.services import InvalidSearchInterpretation
    from app.search import execute_smart_search
    if context is None:
        raise ValueError('Missing preflighted catalog')
    started = perf_counter()
    if profile['mode'] == 'oracle':
        parsed_value = copy.deepcopy(case['expected']['oracle_intent'])
        result = dict(status='ok', error=None, output=parsed_value, raw_output=None, raw_score_output=None,
                      raw_content=None, fallback_used=False, attempts=[], usage=None, cost_cny=0.0,
                      prompt_hash=digest({'oracle': 'inject-annotated-intent-v1'}), latency_ms=0.0)
    else:
        parse_case = {**case, 'task': 'intent_parse', 'expected': case['expected']['parse']}
        result = evaluate(parse_case, profile, key, client=client, sleep=sleep, search_intent=True)
    result['parse_latency_ms'] = result['latency_ms']
    parsed_value = result['output']

    def observed_parser(*_):
        if result['error'] == 'invalid_search_evidence':
            raise InvalidSearchInterpretation()
        if result['error']:
            raise HTTPException(502, 'evaluation parser failure')
        schema = ParsedIntent if profile['mode'] == 'oracle' else SearchFilters
        return schema.model_validate(parsed_value)

    retrieval_started = perf_counter()
    result['fallback_attempted'] = result['error'] not in (None, 'invalid_search_evidence')
    try:
        parsed, items, total = execute_smart_search(context.session, case['input']['text'],
            SimpleNamespace(ai_mode='local' if profile['mode'] == 'oracle' else profile['mode'], demo_mode=True),
            parser=observed_parser, page=1, size=len(context.catalog['items']))
    except (HTTPException, ValueError, TypeError):
        # The serving fallback can itself violate the parse schema on conflicting input.
        # Keep this failed case in the run, with no fabricated retrieval result.
        result.update(status='error', error=result['error'] or 'search_validation_error', output=None,
                      raw_score_output=None, fallback_used=False)
        result['search_latency_ms'] = (perf_counter() - retrieval_started) * 1000
        result['latency_ms'] = round((perf_counter() - started) * 1000, 3)
        return result
    ids = [item.id for item, _coverage in items]
    result['search_latency_ms'] = (perf_counter() - retrieval_started) * 1000
    result['output'] = {'parsed': parsed, 'ranked_item_ids': ids, 'total': total}
    raw = result['raw_score_output']
    budget_fields = {k: parsed[k] for k in ('around_price', 'min_price') if k in parsed}
    result['raw_score_output'] = {'parsed': {**raw, **budget_fields},
        'ranked_item_ids': ids, 'total': total} if raw is not None else None
    result['fallback_used'] = result['error'] is not None
    result['latency_ms'] = round((perf_counter() - started) * 1000, 3)
    return result


def score_search(case, output, error, score_parse):
    target = case['expected']
    valid = (isinstance(output, dict) and set(output) == {'parsed', 'ranked_item_ids', 'total'}
             and isinstance(output['parsed'], dict) and isinstance(output['ranked_item_ids'], list)
             and all(type(x) is str for x in output['ranked_item_ids'])
             and len(set(output['ranked_item_ids'])) == len(output['ranked_item_ids'])
             and type(output['total']) is int and output['total'] == len(output['ranked_item_ids']))
    annotations = {'around_price', 'min_price', 'conditions', 'filter_quotes', 'role_source'}
    parsed = {k: v for k, v in output['parsed'].items() if k not in annotations} if valid else None
    parse_case = {**case, 'task': 'intent_parse', 'expected': target['parse']}
    result = score_parse(parse_case, parsed, error=error or (None if valid else 'search_schema_error'))
    metrics = result['metrics']
    if 'min_price' in target or (valid and 'min_price' in output['parsed']):
        lower = output['parsed'].get('min_price') if valid else None
        result['checks'].append({'field': 'min_price', 'expected': target.get('min_price'),
                                 'actual': lower, 'passed': valid and lower == target.get('min_price')})
    result['checks'].append({'field': 'around_price', 'expected': target.get('around_price', False),
        'actual': output['parsed'].get('around_price') if valid else None,
        'passed': bool(valid and error is None and output['parsed'].get('around_price') is target.get('around_price', False))})
    ids = output['ranked_item_ids'] if valid and error is None and metrics['schema_valid'] else []
    gold = set(target['relevant_item_ids'])
    applicable = target.get('retrieval_applicable', True)
    eligible = applicable and bool(gold)
    hits = [i + 1 for i, key in enumerate(ids) if key in gold]
    metrics.update(retrieval_eligible=eligible, relevant_count=len(gold), retrieval_applicable=applicable,
        mrr=1 / hits[0] if hits else (0.0 if eligible else None),
        ap_at_5=sum(sum(x <= rank for x in hits) / rank for rank in hits if rank <= 5) / min(5, len(gold)) if eligible else None,
        recall_at_10=sum(rank <= 10 for rank in hits) / len(gold) if eligible else None,
        zero_result_error=(len(ids) == 0) if eligible and valid and error is None and metrics['schema_valid'] else None)
    if applicable:
        result['checks'].append({'field': 'retrieval_exact', 'passed': valid and error is None and set(ids) == gold,
                                 'expected': sorted(gold), 'actual': ids})
    metrics['check_count'] = len(result['checks'])
    metrics['passed_checks'] = sum(c['passed'] for c in result['checks'])
    result['passed'] = all(c['passed'] for c in result['checks']) and error is None and valid
    result['score'] = metrics['passed_checks'] / metrics['check_count'] if valid and not error and metrics['schema_valid'] else 0.0
    return result


def semantic_intent(parsed, expected=None):
    value = copy.deepcopy(parsed)
    for key in ('conditions', 'filter_quotes', 'role_source'):
        value.pop(key, None)
    for field in ('keywords', 'excluded_keywords', 'preferences'):
        groups = (expected or {}).get('sets', {}).get(field, [])
        aliases = {normalize_term(term): normalize_term(group[0]) for group in groups for term in group}
        value[field] = sorted(aliases.get(normalize_term(term), normalize_term(term)) for term in value.get(field, []))
    value['clarification'] = bool(value.get('clarification') and value['clarification'].strip())
    return value


def evaluate_relations(records, manifest):
    index = {(r['case_id'], r['model'], r['repeat']): r for r in records}
    targets = {c['id']: c.get('parse_expected', {}) for c in manifest.get('cases', [])}
    prices = {i['id']: i['price_cents'] for i in (manifest.get('catalog') or {}).get('items', [])}
    results = []
    for relation in manifest.get('relations', []):
        for profile in manifest['models']:
            if 'smart_search' not in profile.get('tasks', []):
                continue
            for repeat in range(1, manifest['repeats'] + 1):
                a, b = (index.get((relation[k], profile['id'], repeat)) for k in ('base', 'mutated'))
                valid = all(r and r['status'] == 'ok' and (r.get('score') or {}).get('metrics', {}).get('schema_valid') for r in (a, b))
                checks = {'successful_pair': bool(valid)}
                if valid:
                    first, second = (r['output'] for r in (a, b))
                    before, after = set(first['ranked_item_ids']), set(second['ranked_item_ids'])
                    if relation['relation'] == 'invariant':
                        checks['intent_invariant'] = (semantic_intent(first['parsed'], targets.get(relation['base']))
                            == semantic_intent(second['parsed'], targets.get(relation['mutated'])))
                        checks['result_set_invariant'] = before == after
                    else:
                        checks['full_set_subset'] = after <= before
                        if relation.get('max_price_cents') is not None:
                            checks['price_cap'] = all(i in prices and prices[i] <= relation['max_price_cents'] for i in after)
                        checks['excluded_items_absent'] = not after.intersection(relation.get('forbidden_item_ids', []))
                results.append({'id': relation['id'], 'model': profile['id'], 'repeat': repeat,
                    'relation': relation['relation'], 'checks': checks, 'passed': all(checks.values()),
                    'base_nonempty': bool(a and a.get('output') and a['output']['ranked_item_ids'])})
    return results
