"""A public wanted post and its private matching task represent the same need."""
from dataclasses import replace

from sqlalchemy import select

from .models import Intent, Wanted
from .services import model_name, understand_intent


def wanted_query(wanted):
    if wanted.description.startswith(wanted.title):
        return wanted.description
    return wanted.title + ('\n' + wanted.description if wanted.description else '')


def apply_wanted(wanted, intent, settings, preserve_conditions=False, *, allow_remote=False):
    intent.raw_query = wanted_query(wanted)
    if not preserve_conditions:
        qu_settings = settings if allow_remote else replace(settings, ai_mode='local')
        parsed = understand_intent(intent.raw_query, qu_settings, fallback=True)
        intent.keywords = parsed.keywords or [wanted.title[:30]]
        intent.excluded_keywords = parsed.excluded_keywords
        intent.preferences = parsed.preferences
        intent.condition_grade = parsed.condition_grade
        intent.embedding = None
        intent.embedding_model = model_name(settings)
    intent.category = wanted.category
    intent.max_price_cents = wanted.budget_cents
    intent.campus = wanted.campus


def sync_wanted(db, intent, details=False):
    wanted = db.scalar(select(Wanted).where(Wanted.intent_id == intent.id).with_for_update())
    if wanted:
        wanted.status = intent.status
        if details:
            title, separator, description = intent.raw_query.partition('\n')
            wanted.title = title[:120]
            wanted.description = description if separator and len(title) <= 120 else intent.raw_query
            wanted.category = intent.category
            wanted.budget_cents = intent.max_price_cents
            wanted.campus = intent.campus
    return wanted


def backfill_wanted(factory, matching, settings):
    """Link existing real posts once, without provider calls during startup."""
    with factory.begin() as db:
        posts = db.scalars(select(Wanted).where(Wanted.intent_id.is_(None), Wanted.id.not_like('sample-%')))
        for wanted in posts:
            intent = Intent(buyer_id=wanted.buyer_id, status=wanted.status if wanted.status in {'ACTIVE', 'PAUSED'} else 'COMPLETED')
            apply_wanted(wanted, intent, settings)
            db.add(intent)
            db.flush()
            wanted.intent_id = intent.id
            if intent.status == 'ACTIVE':
                matching.enqueue(db, 'intent', intent.id)
