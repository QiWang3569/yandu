"""Deterministic field and verdict scoring, with explicit evidence limits."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import Field

from .schema import Strict, Verdict, normalize_term, validate_business_payload


class EvidenceOutput(Strict):
    criterion: str = Field(min_length=1, max_length=30)
    quote: str = Field(min_length=1, max_length=160)


class ReviewOutput(Strict):
    item_id: str = Field(min_length=1, max_length=36)
    verdict: Verdict
    evidence: list[EvidenceOutput] = Field(max_length=12)
    questions: list[str] = Field(max_length=6)

    @classmethod
    def checked(cls, value):
        result = cls.model_validate(value)
        if any(not q.strip() or len(q) > 160 for q in result.questions):
            raise ValueError('invalid clarification question')
        return result


def _plain(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump(mode='json')
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _review_values(output):
    output = _plain(output)
    if isinstance(output, dict):
        if set(output) != {'assessments'}:
            raise ValueError('review output must contain only assessments')
        output = output['assessments']
    if type(output) is not list:
        raise ValueError('review output must be a list or assessments object')
    return [_plain(item) for item in output]


def _review_metrics(case, output):
    expected = case['expected']['verdicts']
    actual = {}
    try:
        rows = _review_values(output)
        duplicates = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get('item_id'), str):
                continue
            key = row['item_id']
            if key in actual:
                duplicates.add(key)
            actual[key] = row.get('verdict') if row.get('verdict') in ('MATCH', 'NO_MATCH', 'UNCERTAIN') else None
        for key in duplicates:
            actual[key] = None
    except (TypeError, ValueError):
        pass
    pairs = [{'item_id': key, 'expected': gold, 'actual': actual.get(key)} for key, gold in expected.items()]
    return {'verdict_pairs': pairs,
            'false_match_count': sum(p['expected'] != 'MATCH' and p['actual'] == 'MATCH' for p in pairs),
            'non_match_count': sum(gold != 'MATCH' for gold in expected.values()),
            'evidence_valid': False, 'evidence_valid_count': 0, 'evidence_count': 0,
            'grounded_evidence_rate': None, 'requires_human_review': True}


def score_case(case: dict, output: Any, error=None) -> dict:
    """Score one valid case. Bad provider results are failures, never exceptions.

    Set scoring counts one check per required concept and per surplus output
    term. Matching uses only declared alternatives, case and whitespace.
    Evidence grounding checks verbatim provenance, not semantic entailment.
    """
    checks = []
    metrics = {'schema_valid': False, 'check_count': 0, 'passed_checks': 0}
    if case['task'] == 'candidate_review':
        metrics.update(_review_metrics(case, None if error is not None else output))

    def add(field, passed, expected, actual):
        checks.append({'field': field, 'passed': bool(passed), 'expected': expected, 'actual': actual})

    def finish(force_zero=False):
        metrics['check_count'] = len(checks)
        metrics['passed_checks'] = sum(check['passed'] for check in checks)
        score = metrics['passed_checks'] / len(checks) if checks else 0.0
        return {'passed': bool(checks) and all(c['passed'] for c in checks) and not force_zero,
                'score': 0.0 if force_zero else score, 'checks': checks, 'metrics': metrics}

    if error is not None:
        add('execution', False, 'successful model response', str(error))
        return finish(force_zero=True)
    try:
        if case['task'] != 'candidate_review':
            output = _plain(output)
            validate_business_payload(case['task'], output, output=True)
            metrics['schema_valid'] = True
            target = case['expected']
            for field, expected in target.get('fields', {}).items():
                actual = output.get(field)
                present = field in output
                if field in {'price', 'max_price', 'budget'} and actual is not None and expected is not None:
                    passed = Decimal(str(actual)) == Decimal(str(expected))
                else:
                    passed = actual == expected
                add(field, present and passed, expected, actual if present else {'missing': True})
            precisions, recalls = {}, {}
            for field, groups in target.get('sets', {}).items():
                actual = output.get(field)
                if field not in output:
                    add(field, False, groups, {'missing': True})
                    precisions[field], recalls[field] = 0.0, 0.0
                    continue
                normalized = [normalize_term(term) for term in actual]
                used = set()
                for index, group in enumerate(groups):
                    accepted = {normalize_term(term) for term in group}
                    matched = next((i for i, term in enumerate(normalized) if i not in used and term in accepted), None)
                    if matched is not None:
                        used.add(matched)
                    add(f'{field}.concept[{index}]', matched is not None, group,
                        actual[matched] if matched is not None else {'missing': True})
                for index, term in enumerate(actual):
                    if index not in used:
                        add(f'{field}.extra[{index}]', False, 'no extra term', term)
                if not groups and not actual:
                    add(field, True, [], [])
                precisions[field] = len(used) / len(actual) if actual else (1.0 if not groups else 0.0)
                recalls[field] = len(used) / len(groups) if groups else 1.0
            metrics.update(set_precision=precisions, set_recall=recalls)
            if 'clarification' in target:
                actual = bool(output.get('clarification') and output['clarification'].strip())
                add('clarification', 'clarification' in output and actual == target['clarification'],
                    target['clarification'], actual)
        else:
            rows = _review_values(output)
            assessments = [ReviewOutput.checked(row) for row in rows]
            ids = [row.item_id for row in assessments]
            expected = case['expected']['verdicts']
            if len(set(ids)) != len(ids) or set(ids) != set(expected):
                raise ValueError('review IDs must be unique and exactly match candidates')
            metrics['schema_valid'] = True
            by_id = {row.item_id: row for row in assessments}
            items = {item['id']: item for item in case['input']['items']}
            intent = case['input']['intent']
            hard = set(intent['keywords']) | set(intent['excluded_keywords'])
            criteria = hard | set(intent['preferences']) | {'商品'}
            evidence_checks = []
            for item_id, verdict in expected.items():
                row, item = by_id[item_id], items[item_id]
                add(f'{item_id}.verdict', row.verdict == verdict, verdict, row.verdict)
                sources = [item['title'], item['description'], *item['tags']]
                for index, evidence in enumerate(row.evidence):
                    grounded = evidence.criterion in criteria and any(evidence.quote in source for source in sources)
                    evidence_checks.append(grounded)
                    add(f'{item_id}.evidence[{index}]', grounded,
                        'known criterion and verbatim quote from one source field', evidence.model_dump())
                if row.verdict in {'MATCH', 'NO_MATCH'}:
                    add(f'{item_id}.evidence_required', bool(row.evidence), 'at least one evidence quote', len(row.evidence))
                if row.verdict == 'MATCH':
                    covered = {e.criterion for e in row.evidence}
                    add(f'{item_id}.hard_evidence', hard <= covered, sorted(hard), sorted(covered))
                elif row.verdict == 'NO_MATCH':
                    add(f'{item_id}.hard_rejection', any(e.criterion in hard for e in row.evidence),
                        'rejection cites a hard criterion, not only a preference', [e.criterion for e in row.evidence])
                else:
                    add(f'{item_id}.question_required', bool(row.questions), 'at least one question', row.questions)
            metrics['evidence_count'] = len(evidence_checks)
            metrics['evidence_valid_count'] = sum(evidence_checks)
            metrics['grounded_evidence_rate'] = sum(evidence_checks) / len(evidence_checks) if evidence_checks else None
            metrics['evidence_valid'] = all(c['passed'] for c in checks if not c['field'].endswith('.verdict'))
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as invalid:
        metrics['schema_valid'] = False
        add('output_schema', False, 'valid task output', str(invalid))
        return finish(force_zero=True)
    return finish()
