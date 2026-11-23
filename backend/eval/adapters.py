"""Node adapters. Each adapter calls the production implementation; no prompt is copied."""
import asyncio
import dataclasses
import io
from types import SimpleNamespace

from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import buyer_agent, concept_learning, models, services
from app.schemas import CATEGORIES
from app.vision import SYSTEM_PROMPT, VisionDraft, VisionService

from .datasets import DATASET_DIR


def text_settings(settings, model, url, key):
    return dataclasses.replace(settings, ai_mode='remote', deepseek_model=model,
                               deepseek_url=url, deepseek_key=key, embedding_mode='local')


def vision_settings(settings, model, url, key):
    return dataclasses.replace(settings, vision_model=model, vision_url=url, vision_key=key)


def embedding_settings(settings, model, url, key):
    return dataclasses.replace(settings, ai_mode='remote', embedding_mode='remote',
                               embedding_model=model, embedding_url=url, embedding_key=key)


def run_item(raw, settings, sink):
    parsed = services.parse_item(raw, settings, observer=sink.append)
    return {
        'title': parsed.title,
        'category': parsed.category,
        'price': float(parsed.price) if parsed.price is not None else None,
        'campus': parsed.campus,
        'condition_grade': parsed.condition_grade,
        'tags': list(parsed.tags),
        'clarification': parsed.clarification,
    }


def run_intent(query, settings, sink):
    parsed, quotes = services.parse_intent_with_quotes(query, settings, observer=sink.append)
    return {
        'category': parsed.category,
        'max_price': float(parsed.max_price) if parsed.max_price is not None else None,
        'campus': parsed.campus,
        'keywords': list(parsed.keywords),
        'excluded_keywords': list(parsed.excluded_keywords),
        'preferences': list(parsed.preferences),
        'condition_grade': parsed.condition_grade,
        'clarification': parsed.clarification,
        'quotes': quotes,
    }


def run_review(intent, item, settings, sink):
    assessments = buyer_agent.review_candidates(intent, [item], settings, observer=sink.append)
    if len(assessments) != 1:
        raise ValueError('expected exactly one assessment')
    result = assessments[0]
    return {
        'item_id': result.item_id,
        'verdict': result.verdict,
        'evidence': [evidence.model_dump() for evidence in result.evidence],
        'questions': list(result.questions),
    }


def concept_catalog(rows):
    """Turn name-based dataset rows into the id/parent form production prompts use."""
    ids = {row['name']: concept_learning._slug(row['name']) for row in rows}
    catalog = []
    for row in rows:
        parent = (row.get('parent') or '').strip()
        catalog.append({
            'id': ids[row['name']],
            'name': row['name'],
            'definition': row.get('definition', ''),
            'parent': ids.get(parent),
            'category': row.get('category'),
            'aliases': list(row.get('aliases', [])),
        })
    return catalog


def _concept_db(catalog):
    """Fresh in-memory catalog per sample so rows cannot leak into each other."""
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False},
                           poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for row in catalog:
        db.add(models.Concept(id=row['id'], name=row['name'], definition=row['definition'],
                              parent_id=row['parent'], category=row['category'], source='fixture'))
        for alias in row.get('aliases', []):
            db.add(models.ConceptAlias(alias=alias.lower(), concept_id=row['id'], source='fixture'))
    db.flush()
    return db


def _family_names(plan, catalog):
    by_id = {row['id']: row for row in catalog}
    names = {concept_id: row['name'] for concept_id, row in by_id.items()}
    names.update({concept_id: row['name'] for concept_id, row in plan.new.items()})
    parents = {concept_id: row['parent'] for concept_id, row in by_id.items()}
    parents.update({concept_id: row['parent'] for concept_id, row in plan.new.items()})
    return [{'name': names.get(concept_id, concept_id),
             'parent': names.get(parents.get(concept_id)) if parents.get(concept_id) else None,
             'aliases': list(plan.aliases.get(concept_id, []))}
            for concept_id in plan.links]


def _evidence_grounded(payload, item):
    text = ' '.join(filter(None, [item.title, item.description, *(item.tags or [])])).lower()
    if not isinstance(payload, dict):
        return False
    assignments = payload.get('assignments')
    if not isinstance(assignments, list) or not assignments:
        return True
    return all(isinstance(entry, dict) and str(entry.get('evidence') or '').strip()
               and str(entry['evidence']).strip().lower() in text for entry in assignments)


def run_concept(input, settings, sink):
    """Propose + validate against a throwaway catalog; never writes or refreshes."""
    item = SimpleNamespace(title=input['item'].get('title', ''),
                           description=input['item'].get('description', ''),
                           tags=list(input['item'].get('tags') or []),
                           category=input['item'].get('category'))
    catalog = concept_catalog(input.get('catalog', []))
    db = _concept_db(catalog)
    payload = concept_learning.propose(item, catalog, settings, observer=sink.append)
    try:
        concept_learning.Proposal.model_validate(payload)
        schema_valid = True
    except (ValueError, TypeError):
        schema_valid = False
    grounded = _evidence_grounded(payload, item)
    try:
        plan = concept_learning.validate(db, item, payload)
    except concept_learning.Rejected as error:
        return {'decision': 'reject', 'reason': error.reason, 'families': [], 'aliases': [],
                'evidence_grounded': grounded, 'schema_valid': schema_valid}
    except (ValueError, TypeError):
        return {'decision': 'reject', 'reason': 'invalid_schema', 'families': [], 'aliases': [],
                'evidence_grounded': grounded, 'schema_valid': schema_valid}
    families = _family_names(plan, catalog)
    return {'decision': 'apply', 'reason': 'learned' if plan.links else 'no_family',
            'families': families,
            'aliases': [alias for family in families for alias in family['aliases']],
            'evidence_grounded': grounded, 'schema_valid': schema_valid}


def render_image(spec):
    """Load a frozen photo when named; otherwise draw a deterministic synthetic one."""
    if spec.get('file'):
        return (DATASET_DIR / spec['file']).read_bytes()
    image = Image.new('RGB', (480, 360), tuple(spec.get('background', [255, 255, 255])))
    draw = ImageDraw.Draw(image)
    color = tuple(spec.get('color', [180, 190, 200]))
    shape = spec.get('shape', 'blank')
    if shape == 'book':
        draw.rectangle([110, 50, 370, 300], fill=color, outline='black', width=4)
        draw.line([110, 118, 370, 118], fill='black', width=2)
    elif shape == 'mouse':
        draw.ellipse([170, 110, 310, 250], fill=color, outline='black', width=4)
        draw.line([240, 132, 240, 172], fill='black', width=3)
    elif shape == 'bike':
        draw.ellipse([110, 200, 200, 290], outline='black', width=4)
        draw.ellipse([280, 200, 370, 290], outline='black', width=4)
        draw.line([155, 245, 310, 245], fill='black', width=4)
        draw.line([230, 245, 200, 160], fill=black_color(), width=4)
    elif shape == 'lamp':
        draw.polygon([(180, 60), (300, 60), (330, 130), (150, 130)], fill=color, outline='black')
        draw.rectangle([228, 130, 252, 300], fill=black_color())
    elif shape == 'monitor':
        draw.rectangle([90, 60, 390, 250], fill=color, outline='black', width=4)
        draw.rectangle([228, 250, 252, 300], fill=black_color())
        draw.rectangle([170, 300, 310, 315], fill=black_color())
    elif shape == 'headphones':
        draw.arc([140, 80, 340, 300], start=180, end=360, fill=black_color(), width=6)
        draw.ellipse([130, 200, 190, 290], fill=color, outline='black')
        draw.ellipse([290, 200, 350, 290], fill=color, outline='black')
    elif shape == 'multiple':
        draw.rectangle([70, 70, 190, 250], fill=color, outline='black', width=3)
        draw.rectangle([280, 90, 410, 270], fill=tuple(spec.get('color2', [210, 170, 150])), outline='black', width=3)
    elif shape == 'occluded':
        draw.rectangle([150, 90, 340, 280], fill=color, outline='black', width=3)
        draw.rectangle([150, 180, 340, 280], fill=tuple(spec.get('occluder', [90, 90, 90])))
    if spec.get('label'):
        draw.text((20, 328), spec['label'], fill=black_color())
    stream = io.BytesIO()
    image.save(stream, 'JPEG', quality=85)
    return stream.getvalue()


def black_color():
    return (0, 0, 0)


def run_vision(specs, note, settings, sink):
    images = [render_image(spec) for spec in specs]
    service = VisionService(settings, observer=sink.append)
    result = asyncio.run(service._complete(images, note, SYSTEM_PROMPT, VisionDraft, 1200))
    return result.model_dump(mode='json')


def _normalized(text):
    return services.normalize(text)


def lexical_rank(parsed, excluded, pool, k=10):
    """Retrieval-stage ranking with the same alias table as production."""
    keywords = [_normalized(word) for word in parsed.get('keywords', []) if word.strip()]
    excluded = [_normalized(word) for word in excluded if word.strip()]
    ranked = []
    for item in pool:
        text = _normalized(' '.join([item['title'], item['description'], *item.get('tags', [])]))
        if any(term and services.tokens_contain(text, term) for term in excluded):
            continue
        if parsed.get('category') and item['category'] != parsed['category']:
            continue
        if parsed.get('max_price') is not None and item['price'] > parsed['max_price']:
            continue
        if parsed.get('campus') not in (None, '不限校区') and item['campus'] not in (parsed['campus'], '不限校区'):
            continue
        if parsed.get('condition_grade'):
            order = ['全新', '95新', '9成新', '8成新', '基本可用']
            if order.index(item['condition_grade']) > order.index(parsed['condition_grade']):
                continue
        score = sum(services.tokens_contain(text, term) for term in keywords) / len(keywords) if keywords else 0.0
        if score > 0:
            ranked.append((item['id'], score, item['price']))
    ranked.sort(key=lambda row: (-row[1], row[2], row[0]))
    return [row[0] for row in ranked[:k]]


def run_recall(row, pool, sink):
    parsed = row['parsed']
    ranked = lexical_rank(parsed, parsed.get('excluded_keywords', []), pool)
    sink.append({'node': 'recall', 'model': 'lexical-alias', 'ranked': len(ranked)})
    return {'ranked': ranked}


def pool_categories(pool):
    return {item['id']: item['category'] for item in pool if item.get('category') in CATEGORIES}