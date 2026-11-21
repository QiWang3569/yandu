"""Unified search, hard-constraint filtering, and candidate recall shared by items, wanted posts, smart search, and buyer intents."""
from fastapi import HTTPException
from sqlalchemy import func, or_, select

from .smart_terms import Listing, normalized, phrase_matches, required_terms
from .search_intent import SearchFilters, budget_from_text, explicit_category
from .models import Item
from .schemas import CONDITIONS, ParsedIntent
from .services import (
    FEATURES,
    condition_matches,
    normalize,
    InvalidSearchInterpretation,
    local_search_intent,
    parse_search_intent,
    similarity,
)


def keyword_filters(query, *columns):
    # Every whitespace-separated term must match; aliases of one term are alternatives.
    for word in dict.fromkeys(query.lower().split()):
        normalized = normalize(word)
        aliases = {word, normalized, *FEATURES.get(normalized, [])} - {''}
        yield or_(*(func.lower(column).contains(alias.lower(), autoescape=True)
                    for column in columns for alias in aliases))


def _spec_field(spec, name: str, default=None):
    if isinstance(spec, dict):
        return spec.get(name, default)
    return getattr(spec, name, default)


def _spec_max_price_cents(spec) -> int | None:
    cents = _spec_field(spec, 'max_price_cents')
    if cents is not None:
        return int(cents)
    max_price = _spec_field(spec, 'max_price')
    if max_price is not None:
        return int(max_price * 100)
    return None


def price_cap_cents(max_price_cents: int | None, *, around: bool = False) -> int | None:
    if max_price_cents is None:
        return None
    return max_price_cents * 115 // 100 if around else max_price_cents


def matches_hard_constraints(item, spec, *, around: bool = False, buyer_id: str | None = None) -> bool:
    """In-memory hard-attribute check shared by intent eligibility and revalidation."""
    spec_status = _spec_field(spec, 'status', 'ACTIVE')
    effective_buyer_id = buyer_id if buyer_id is not None else _spec_field(spec, 'buyer_id')
    category = _spec_field(spec, 'category')
    campus = _spec_field(spec, 'campus', '不限校区')
    condition_grade = _spec_field(spec, 'condition_grade')
    cap = price_cap_cents(_spec_max_price_cents(spec), around=around)

    return (
        spec_status == 'ACTIVE'
        and item.status == 'ACTIVE'
        and (not effective_buyer_id or item.seller_id != effective_buyer_id)
        and (not category or item.category == category)
        and (cap is None or item.price_cents <= cap)
        and (not campus or campus == '不限校区' or item.campus in {campus, '不限校区'})
        and condition_matches(item.condition_grade, condition_grade)
    )


def apply_intent_filters(
    query,
    spec,
    *,
    around: bool = False,
    demo_mode: bool = True,
    buyer_id: str | None = None,
    item_id: str | None = None,
):
    """Unified SQLAlchemy hard-attribute filter for smart search and buyer-agent recall."""
    effective_buyer_id = buyer_id if buyer_id is not None else _spec_field(spec, 'buyer_id')
    category = _spec_field(spec, 'category')
    campus = _spec_field(spec, 'campus', '不限校区')
    condition_grade = _spec_field(spec, 'condition_grade')
    cap = price_cap_cents(_spec_max_price_cents(spec), around=around)

    if not demo_mode:
        query = query.where(Item.seller_id.not_like('demo-%'))
    query = query.where(Item.status == 'ACTIVE')
    if effective_buyer_id:
        query = query.where(Item.seller_id != effective_buyer_id)
    if item_id:
        query = query.where(Item.id == item_id)
    if category:
        query = query.where(Item.category == category)
    if campus and campus != '不限校区':
        query = query.where(Item.campus.in_([campus, '不限校区']))
    if cap is not None:
        query = query.where(Item.price_cents <= cap)
    if condition_grade:
        allowed = CONDITIONS[:CONDITIONS.index(condition_grade) + 1]
        query = query.where(Item.condition_grade.in_(allowed))
    return query


def search_items_by_intent(
    db,
    parsed: ParsedIntent,
    settings,
    *,
    around: bool = False,
    sort: str = 'recommended',
    page: int = 1,
    size: int = 12,
):
    """Stage 1 (hard filter) + Stage 2 (negation-aware lexical recall & ranking) for smart search."""
    target_cents = _spec_max_price_cents(parsed)
    query = apply_intent_filters(select(Item), parsed, around=around, demo_mode=settings.demo_mode)
    minimum = getattr(parsed, 'min_price', None)
    if minimum is not None:
        query = query.where(Item.price_cents >= int(minimum * 100))

    required = required_terms(parsed.keywords)
    price_terms = {}
    for term in {*parsed.keywords, *parsed.excluded_keywords, *parsed.preferences}:
        budget = budget_from_text(normalized(term))
        if budget.maximum is not None and not budget.product.strip():
            floor = int((budget.minimum or 0) * 100)
            cap = price_cap_cents(int(budget.maximum * 100), around=budget.around)
            price_terms[term] = (floor, cap)

    def matches(listing, term, *, require_subject=False, minimum_condition=False):
        if term in price_terms:
            floor, cap = price_terms[term]
            return floor <= listing.price_cents <= cap
        return phrase_matches(listing, term, require_subject=require_subject, minimum_condition=minimum_condition)

    scored = []
    for item in db.scalars(query):
        listing = Listing.from_item(item)
        if any(matches(listing, term) for term in parsed.excluded_keywords):
            continue
        if not all(matches(listing, term, require_subject=as_subject, minimum_condition=True)
                   for term, as_subject in required):
            continue
        preferred = sum(matches(listing, term) for term in parsed.preferences)
        scored.append((item, preferred))

    def sort_key(entry):
        item, preferred = entry
        newest = -item.created_at.timestamp()
        if sort == 'price_asc':
            return (item.price_cents, newest, item.id)
        if sort == 'price_desc':
            return (-item.price_cents, newest, item.id)
        if sort == 'newest':
            return (newest, item.id)
        closeness = abs(item.price_cents - target_cents) if around and target_cents is not None else 0
        return (-preferred, closeness, newest, item.id)

    scored.sort(key=sort_key)
    page_items = scored[(page - 1) * size:page * size]
    # Each returned item satisfies every required term (including an empty list).
    return [(item, 1.0) for item, _ in page_items], len(scored)


def execute_smart_search(
    db,
    raw_query: str,
    settings,
    *,
    sort: str = 'recommended',
    page: int = 1,
    size: int = 12,
    parser=parse_search_intent,
):
    """Unified end-to-end pipeline: natural-language QU + candidate recall & ranking."""
    try:
        parsed = parser(raw_query, settings)
    except InvalidSearchInterpretation:
        raise  # Invalid evidence must not be replaced by a different interpretation.
    except HTTPException:
        parsed = local_search_intent(raw_query)
    if not isinstance(parsed, SearchFilters):
        # Reference/legacy intents already assign roles. Only resolve price-band semantics.
        budget = budget_from_text(normalized(raw_query)) if parsed.max_price is not None else None
        parsed = SearchFilters(**parsed.model_dump(), around_price=bool(budget and budget.around),
                               min_price=budget.minimum if budget else None, role_source='reference')
    around = parsed.around_price
    page_items, total = search_items_by_intent(
        db, parsed, settings, around=around, sort=sort, page=page, size=size
    )
    # An inferred category can misfile a concrete product. Retry only that filter,
    # and report the filters actually used. An explicit category remains binding.
    if total == 0 and parsed.keywords and parsed.category and not explicit_category(raw_query):
        across_categories = parsed.model_copy(update={'category': None})
        alternatives, count = search_items_by_intent(
            db, across_categories, settings, around=around, sort=sort, page=page, size=size
        )
        if count:
            parsed, page_items, total = across_categories, alternatives, count
    parsed_out = {
        'category': parsed.category,
        'max_price': float(parsed.max_price) if parsed.max_price is not None else None,
        'campus': parsed.campus,
        'keywords': parsed.keywords,
        'excluded_keywords': parsed.excluded_keywords,
        'preferences': parsed.preferences,
        'condition_grade': parsed.condition_grade,
        'clarification': parsed.clarification,
        'around_price': around,
    }
    if parsed.min_price is not None:
        parsed_out['min_price'] = float(parsed.min_price)
    if parsed.conditions is not None:
        parsed_out.update(conditions=[c.model_dump() for c in parsed.conditions],
                          role_source=parsed.role_source, filter_quotes=parsed.filter_quotes)
    return parsed_out, page_items, total


def item_snapshot(item: Item) -> dict:
    return {
        'id': item.id,
        'title': item.title,
        'description': item.description,
        'tags': item.tags,
        'price_cents': item.price_cents,
        'campus': item.campus,
        'condition_grade': item.condition_grade,
    }


def recall_candidates_for_intent(
    db,
    intent,
    settings,
    *,
    item_id: str | None = None,
    exclude_item_ids: set[str] | None = None,
    limit: int = 10,
) -> list[tuple[dict, float]]:
    """Unified Stage 1 + Stage 2 recall for background buyer-agent & wanted matching."""
    query = apply_intent_filters(select(Item), intent, demo_mode=True, item_id=item_id)
    if exclude_item_ids:
        query = query.where(Item.id.not_in(exclude_item_ids))
    if settings.embedding_mode == 'remote':
        query = query.where(Item.embedding_model == intent.embedding_model, Item.embedding.is_not(None))
        if db.bind.dialect.name == 'postgresql' and intent.embedding is not None:
            query = query.order_by(Item.embedding.op('<=>')(intent.embedding)).limit(limit)
    candidates = [(item_snapshot(i), similarity(i, intent, settings)) for i in db.scalars(query)]
    if settings.ai_mode == 'local' or settings.embedding_mode == 'remote':
        candidates = [(i, s) for i, s in candidates if s >= settings.threshold]
    candidates.sort(key=lambda pair: (-pair[1], pair[0]['price_cents'], pair[0]['id']))
    return candidates[:limit]
