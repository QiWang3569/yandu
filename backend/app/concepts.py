"""Database-backed product-concept catalog.

Concept families, aliases and item links are written by the concept-learning
worker from model judgments. This module only reads a snapshot of those tables
for runtime lookup; catalog content never lives in code and no model call
happens per query.
"""
import re
import threading
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import Concept, ConceptAlias, Item, ItemConcept


def _key(value):
    return (value or '').strip().lower()


@dataclass(frozen=True)
class Catalog:
    concepts: dict
    aliases: dict
    children: dict
    parent: dict
    pattern: re.Pattern | None

    @classmethod
    def load(cls, db: Session):
        concepts = {row.id: {'name': row.name, 'definition': row.definition or '',
                             'parent': row.parent_id, 'category': row.category}
                    for row in db.scalars(select(Concept))}
        aliases = {row.alias: row.concept_id for row in db.scalars(select(ConceptAlias))}
        return cls.build(concepts, aliases)

    @classmethod
    def build(cls, concepts, aliases):
        concepts = {cid: {'name': row['name'], 'definition': row.get('definition', ''),
                          'parent': row.get('parent'), 'category': row.get('category')}
                    for cid, row in concepts.items() if row.get('parent') in (None, *concepts)}
        aliases = {_key(alias): cid for alias, cid in aliases.items() if cid in concepts and _key(alias)}
        children, parent = {}, {}
        for cid, row in concepts.items():
            parent[cid] = row['parent']
            if row['parent']:
                children.setdefault(row['parent'], []).append(cid)
        for cid, row in concepts.items():
            alias = _key(row['name'])
            if alias and alias not in aliases:
                aliases[alias] = cid
        pattern = re.compile('|'.join(re.escape(alias) for alias in
                                      sorted(aliases, key=len, reverse=True)), re.IGNORECASE) if aliases else None
        return cls(concepts=concepts, aliases=aliases, children=children, parent=parent, pattern=pattern)

    @classmethod
    def empty(cls):
        return cls(concepts={}, aliases={}, children={}, parent={}, pattern=None)

    def ancestors(self, concept_id):
        chain, cursor, seen = [], self.parent.get(concept_id), set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            chain.append(cursor)
            cursor = self.parent.get(cursor)
        return chain

    def descendants(self, concept_id):
        result, stack = [], list(self.children.get(concept_id, []))
        while stack:
            child = stack.pop()
            if child in result:
                continue
            result.append(child)
            stack.extend(self.children.get(child, []))
        return result

    def matches(self, text):
        if self.pattern is None:
            return []
        return [self.aliases[match.group(0).lower()] for match in self.pattern.finditer(text or '')]


_STATE = threading.Lock()
_CATALOG = Catalog.empty()
_LEGACY = True


def configure(catalog, legacy):
    global _CATALOG, _LEGACY
    with _STATE:
        _CATALOG, _LEGACY = catalog, bool(legacy)


def refresh(db: Session):
    configure(Catalog.load(db), legacy_enabled())


def reset():
    configure(Catalog.empty(), legacy=True)


def current():
    with _STATE:
        return _CATALOG


def legacy_enabled():
    with _STATE:
        return _LEGACY


def concepts_in_text(text):
    """Concept ids in order of appearance, using longest-alias matching."""
    return current().matches(text)


def concept_names(text):
    catalog = current()
    return list(dict.fromkeys(catalog.concepts[cid]['name'] for cid in catalog.matches(text)))


def concept_category(concept_id):
    return current().concepts.get(concept_id, {}).get('category')


def ancestors(concept_id):
    return current().ancestors(concept_id)


def expand_concept_ids(concept_ids):
    catalog = current()
    result = []
    for concept_id in concept_ids:
        for item in [concept_id, *catalog.descendants(concept_id)]:
            if item in catalog.concepts and item not in result:
                result.append(item)
    return result


def expand_term(term):
    """Concept ids and every alias surface for a query term."""
    catalog = current()
    concept_ids = expand_concept_ids(catalog.matches(term))
    aliases = []
    for concept_id in concept_ids:
        for alias, mapped in catalog.aliases.items():
            if mapped == concept_id and alias not in aliases:
                aliases.append(alias)
        name = catalog.concepts[concept_id]['name']
        if name not in aliases:
            aliases.append(name)
    return concept_ids, aliases


def canonicalize(text):
    """Replace a learned alias with its canonical name plus ancestors.

    Spaces keep whole-token checks from treating '鼠标' as present in '鼠标垫'.
    """
    catalog = current()
    if catalog.pattern is None:
        return (text or '').lower()

    def replace(match):
        concept_id = catalog.aliases[match.group(0).lower()]
        names = [catalog.concepts[concept_id]['name'],
                 *(catalog.concepts[a]['name'] for a in catalog.ancestors(concept_id))]
        return ' ' + ' '.join(dict.fromkeys(names)) + ' '
    return catalog.pattern.sub(replace, (text or '').lower())


def link_item(db: Session, item):
    """Apply the currently known aliases to one item; no model call."""
    catalog = current()
    concept_ids = list(dict.fromkeys(catalog.matches(' '.join(
        [item.title or '', item.description or '', *(item.tags or [])]))))
    db.execute(delete(ItemConcept).where(ItemConcept.item_id == item.id, ItemConcept.source == 'model'))
    for concept_id in concept_ids:
        db.add(ItemConcept(item_id=item.id, concept_id=concept_id, source='model'))
    db.flush()


def relink_items(db: Session):
    """Re-apply the catalog to every item after a learning update."""
    if not current().concepts:
        return
    items = db.scalars(select(Item)).all()
    db.execute(delete(ItemConcept).where(ItemConcept.source == 'model'))
    catalog = current()
    for item in items:
        for concept_id in dict.fromkeys(catalog.matches(' '.join(
                [item.title or '', item.description or '', *(item.tags or [])]))):
            db.add(ItemConcept(item_id=item.id, concept_id=concept_id, source='model'))
    db.flush()


