"""Strict, versionable evaluation cases; one JSON object per file."""
from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.schemas import (
    CAMPUSES, CATEGORIES, CONDITIONS, ItemParseRequest, ParsedIntent,
    ParsedItem, ParsedWanted, QueryIn, WantedParseRequest,
)


Task = Literal['intent_parse', 'item_parse', 'wanted_parse', 'candidate_review']
Verdict = Literal['MATCH', 'NO_MATCH', 'UNCERTAIN']
Nonempty = Annotated[str, Field(min_length=1)]
PARSING_MODELS = {'intent_parse': ParsedIntent, 'item_parse': ParsedItem, 'wanted_parse': ParsedWanted}
SCALAR_FIELDS = {
    'intent_parse': {'category', 'max_price', 'campus', 'condition_grade'},
    'item_parse': {'category', 'price', 'campus', 'condition_grade'},
    'wanted_parse': {'category', 'budget', 'campus'},
}
SET_FIELDS = {'intent_parse': {'keywords', 'excluded_keywords', 'preferences'},
              'item_parse': {'tags'}, 'wanted_parse': set()}
MONEY_FIELDS = {'max_price', 'price', 'budget'}


def normalize_term(value: str) -> str:
    """Only collapse whitespace and case; never infer synonyms or substrings."""
    return ' '.join(value.split()).casefold()


def ensure_finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('non-finite numbers are forbidden')
    if isinstance(value, Decimal) and not value.is_finite():
        raise ValueError('non-finite numbers are forbidden')
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError('object keys must be strings')
        for child in value.values():
            ensure_finite(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            ensure_finite(child)


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, str_strip_whitespace=True,
                              allow_inf_nan=False)


def validate_business_payload(task: str, value: dict, *, output: bool = False) -> Any:
    """Use production enums/constraints, without bool/str-to-number case coercion.

    Production Decimal output schemas explicitly permit numeric strings. Model
    output and JSON-serialized final results retain that compatibility; gold
    case data must use JSON numbers.
    """
    if not isinstance(value, dict):
        raise ValueError('parsed payload must be an object')
    ensure_finite(value)
    schema = PARSING_MODELS[task]
    if set(value) - set(schema.model_fields):
        raise ValueError('unknown parsed fields: ' + ', '.join(sorted(set(value) - set(schema.model_fields))))
    for name, item in value.items():
        if name in MONEY_FIELDS:
            accepted = (int, float, Decimal, str) if output else (int, float)
            if item is not None and (type(item) not in accepted):
                raise ValueError(f'{name} must be a number or null')
        elif name in {'keywords', 'excluded_keywords', 'preferences', 'tags'}:
            if type(item) is not list or any(type(term) is not str for term in item):
                raise ValueError(f'{name} must be a string list')
            normalized = [normalize_term(term) for term in item]
            if len(set(normalized)) != len(normalized):
                raise ValueError(f'{name} contains duplicate terms')
        elif item is not None and type(item) is not str:
            raise ValueError(f'{name} must be a string or null')
    result = schema.model_validate(value)
    # Production validators normalize empty condition strings to None. Cases
    # and evaluated outputs must actually contain a documented enum value.
    if 'condition_grade' in value and value['condition_grade'] not in {*CONDITIONS, None}:
        raise ValueError('invalid condition_grade')
    return result


class ParseInput(Strict):
    text: Nonempty


class ParseExpected(Strict):
    fields: dict[str, Any] = Field(default_factory=dict)
    sets: dict[str, list[list[str]]] = Field(default_factory=dict)
    clarification: bool | None = None

    @model_validator(mode='after')
    def valid_targets(self):
        if not self.fields and not self.sets and self.clarification is None:
            raise ValueError('expected must contain at least one evaluation target')
        for field, groups in self.sets.items():
            seen: set[str] = set()
            for group in groups:
                if not group:
                    raise ValueError(f'{field}: synonym groups cannot be empty')
                terms = [normalize_term(term) for term in group]
                if any(not term or len(term) > 30 for term in terms):
                    raise ValueError(f'{field}: terms must contain 1–30 characters')
                if len(set(terms)) != len(terms) or seen.intersection(terms):
                    raise ValueError(f'{field}: synonym groups must be disjoint and unique')
                seen.update(terms)
        return self


class CandidateItem(Strict):
    id: str = Field(min_length=1, max_length=36)
    title: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=5, max_length=3000)
    tags: list[str] = Field(max_length=8)
    price_cents: int = Field(ge=0, le=99999900)
    campus: str
    condition_grade: str
    category: str | None = None

    @model_validator(mode='after')
    def business_values(self):
        if self.campus not in CAMPUSES or self.condition_grade not in CONDITIONS:
            raise ValueError('invalid campus or condition_grade')
        if self.category is not None and self.category not in CATEGORIES:
            raise ValueError('invalid category')
        validate_business_payload('item_parse', {'tags': self.tags})
        return self


class ReviewInput(Strict):
    intent: dict[str, Any]
    items: list[CandidateItem] = Field(min_length=1, max_length=10)

    @model_validator(mode='after')
    def intent_and_ids(self):
        if not {'keywords', 'excluded_keywords', 'preferences'} <= self.intent.keys():
            raise ValueError('review intent requires keywords, excluded_keywords and preferences')
        validate_business_payload('intent_parse', self.intent)
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError('candidate item IDs must be unique')
        return self


class ReviewExpected(Strict):
    verdicts: dict[Nonempty, Verdict] = Field(min_length=1)


class Case(Strict):
    id: str = Field(min_length=1, max_length=120, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')
    task: Task
    enabled: bool
    split: Literal['dev', 'holdout']
    family: Nonempty
    tags: list[Nonempty]
    source: Nonempty
    rationale: Nonempty
    label_status: Literal['draft', 'reviewed']
    input: dict[str, Any]
    expected: dict[str, Any]

    @model_validator(mode='after')
    def task_contract(self):
        ensure_finite(self.input)
        ensure_finite(self.expected)
        if len(self.tags) != len(set(self.tags)):
            raise ValueError('case tags must be unique')
        if self.task == 'candidate_review':
            given = ReviewInput.model_validate(self.input)
            target = ReviewExpected.model_validate(self.expected)
            if set(target.verdicts) != {item.id for item in given.items}:
                raise ValueError('expected verdict IDs must exactly match input item IDs')
        else:
            given = ParseInput.model_validate(self.input)
            if self.task == 'intent_parse':
                QueryIn(raw_query=given.text)
            elif self.task == 'item_parse':
                ItemParseRequest(raw=given.text)
            else:
                WantedParseRequest(raw=given.text)
            target = ParseExpected.model_validate(self.expected)
            if 'clarification' in self.expected and self.expected['clarification'] is None:
                raise ValueError('expected clarification must be a boolean when provided')
            if set(target.fields) - SCALAR_FIELDS[self.task]:
                raise ValueError('unsupported scalar evaluation field')
            if set(target.sets) - SET_FIELDS[self.task]:
                raise ValueError('unsupported set evaluation field')
            representatives = {key: [group[0] for group in groups] for key, groups in target.sets.items()}
            validate_business_payload(self.task, {**target.fields, **representatives})
            # Every accepted synonym must satisfy the business field contract.
            for field, groups in target.sets.items():
                for group in groups:
                    for term in group:
                        validate_business_payload(self.task, {field: [term]})
            if self.task == 'intent_parse':
                positive = {normalize_term(t) for field in ('keywords', 'preferences')
                            for group in target.sets.get(field, []) for t in group}
                negative = {normalize_term(t) for group in target.sets.get('excluded_keywords', []) for t in group}
                if positive & negative:
                    raise ValueError('accepted required/preferred and excluded terms overlap')
        return self


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def validate_cases(path: str | Path) -> list[dict]:
    """Load a file or recursive directory, rejecting ID and split leakage."""
    path = Path(path)
    files = sorted(path.rglob('*.json')) if path.is_dir() else [path]
    if not files:
        raise ValueError(f'no JSON cases found at {path}')
    cases = []
    ids: set[str] = set()
    families: dict[str, str] = {}
    for filename in files:
        try:
            raw = json.loads(filename.read_text(encoding='utf-8-sig'), object_pairs_hook=_unique_object,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'invalid JSON number: {value}')))
            case = Case.model_validate(raw).model_dump(mode='json')
            if case['id'] in ids:
                raise ValueError(f'duplicate case id: {case["id"]}')
            if case['family'] in families and families[case['family']] != case['split']:
                raise ValueError(f'family leakage across dev/holdout: {case["family"]}')
            ids.add(case['id'])
            families[case['family']] = case['split']
            cases.append(case)
        except (OSError, ValueError, TypeError) as error:
            raise ValueError(f'{filename}: {error}') from error
    return cases
