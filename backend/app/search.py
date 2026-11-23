"""Literal, case-insensitive keyword matching shared by items and wanted posts."""
from sqlalchemy import and_, func, or_, select

from . import concepts
from .models import ItemConcept
from .services import ATTRIBUTE_ALIASES


def attribute_aliases(word):
    for canonical, synonyms in ATTRIBUTE_ALIASES.items():
        if word == canonical or word in synonyms:
            return synonyms
    return []


def keyword_filters(query, *columns, item_model=None):
    # Every whitespace-separated term must match; aliases of one term are alternatives.
    for word in dict.fromkeys(query.lower().split()):
        concept_ids, aliases = concepts.expand_term(word)
        surfaces = {word, *aliases, *attribute_aliases(word)} - {''}
        text = or_(*(func.lower(column).contains(alias.lower(), autoescape=True)
                     for column in columns for alias in surfaces))
        if concept_ids and item_model is not None:
            # Items with concept links use the table; legacy unlinked rows fall back to text.
            linked = select(ItemConcept.item_id)
            yield or_(
                item_model.id.in_(select(ItemConcept.item_id).where(
                    ItemConcept.concept_id.in_(concept_ids))),
                and_(item_model.id.not_in(linked), text),
            )
        else:
            yield text
