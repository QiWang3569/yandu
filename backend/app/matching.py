"""Persisted event jobs. Provider calls run with no DB session or mutation lock held.

The MVP runs one worker per process; use one server process until a distributed
queue and multi-process migration coordination are introduced.
"""
import threading
import re
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .buyer_agent import Assessment, Evidence, ModelUnavailable, review_candidates
from .models import Intent, Item, MatchJob, Notification, now
from .search import item_snapshot, matches_hard_constraints, recall_candidates_for_intent
from .services import EXCLUSION_NEGATION_PREFIX, NEGATION_PREFIX, embed, model_name, normalize, term_matches


def item_data(item):
    return item_snapshot(item)


def intent_data(intent):
    return {'keywords': intent.keywords, 'excluded_keywords': intent.excluded_keywords,
            'preferences': intent.preferences, 'category': intent.category,
            'max_price_cents': intent.max_price_cents, 'campus': intent.campus,
            'condition_grade': intent.condition_grade}


def eligible(item, intent):
    return matches_hard_constraints(item, intent)


def local_review(intent, item):
    source = [item['title'], item['description'], *item['tags']]
    text = normalize(' '.join(source))
    evidence, questions = [], []
    verdict = 'MATCH'
    for term in intent['excluded_keywords']:
        normalized = normalize(term)
        # A negated exclusion is not positive evidence that the item has it.
        if term_matches(term, text, ignore_negated=True, negation_prefix=EXCLUSION_NEGATION_PREFIX):
            quote = next((s[:160] for s in source if term in s), None)
            # Pick an exact slice even when the term occurs late in a long description.
            if quote is None:
                quote = source[0][:160]
            return Assessment(item_id=item['id'], verdict='NO_MATCH', evidence=[Evidence(criterion=term, quote=quote)], questions=[])
        if normalized not in text:
            verdict = 'UNCERTAIN'
            questions.append(f'请确认商品是否具有“{term}”这一不接受的特征？')
    for term in intent['keywords']:
        if re.search(NEGATION_PREFIX + re.escape(normalize(term)), text):
            quote = next(s for s in source if normalize(term) in normalize(s))
            return Assessment(item_id=item['id'], verdict='NO_MATCH', evidence=[Evidence(criterion=term, quote=quote[:160])], questions=[])
        if term_matches(term, text):
            quote = next((s for s in source if normalize(term) in normalize(s)), '')
            evidence.append(Evidence(criterion=term, quote=quote[:160]))
    for term in intent['preferences']:
        if not term_matches(term, text) or re.search(NEGATION_PREFIX + re.escape(normalize(term)), text):
            questions.append(f'请问商品是否满足“{term}”这一偏好？')
    return Assessment(item_id=item['id'], verdict=verdict, evidence=evidence[:12], questions=questions[:6])


class MatchingRunner:
    def __init__(self, factory, settings, mutation_lock):
        self.factory, self.settings, self.lock = factory, settings, mutation_lock
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.thread = None

    def start(self):
        with self.factory() as db:
            db.execute(update(MatchJob).where(MatchJob.status == 'RUNNING').values(status='PENDING', available_at=now()))
            db.commit()
        self.thread = threading.Thread(target=self._work, name='yandu-matching', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake_event.set()
        if self.thread:
            self.thread.join(timeout=self.settings.model_timeout + 2)

    def enqueue(self, db, kind, target_id, item_id=None):
        job = MatchJob(kind=kind, target_id=target_id, item_id=item_id)
        db.add(job)
        db.flush()
        return job.id

    def enqueue_item(self, db, item):
        return [self.enqueue(db, 'intent', intent.id, item.id)
                for intent in db.scalars(select(Intent).where(Intent.status == 'ACTIVE'))
                if eligible(item, intent)]

    def run_or_wake(self, job_id):
        if self.settings.ai_mode == 'local':
            self.process(job_id)
        else:
            self.wake_event.set()

    def _work(self):
        while not self.stop_event.is_set():
            self.wake_event.wait(timeout=1)
            self.wake_event.clear()
            with self.factory() as db:
                ids = list(db.scalars(select(MatchJob.id).where(MatchJob.status == 'PENDING', MatchJob.available_at <= now()).order_by(MatchJob.created_at).limit(20)))
            for job_id in ids:
                if self.stop_event.is_set():
                    break
                self.process(job_id)

    def process(self, job_id):
        with self.lock, self.factory() as db:
            claimed = db.execute(update(MatchJob).where(MatchJob.id == job_id, MatchJob.status == 'PENDING', MatchJob.available_at <= now())
                                 .values(status='RUNNING', attempts=MatchJob.attempts + 1))
            if not claimed.rowcount:
                return []
            job = db.get(MatchJob, job_id)
            kind, target_id, item_id = job.kind, job.target_id, job.item_id
            db.commit()
        try:
            with self.factory() as db:
                if kind == 'intent':
                    ids = [target_id]
                else:
                    ids = list(db.scalars(select(Intent.id).where(Intent.status == 'ACTIVE')))
            matched = []
            for intent_id in ids:
                if self.stop_event.is_set():
                    raise ModelUnavailable('interrupted')
                matched.extend(self._match(intent_id, target_id if kind == 'item' else item_id))
            with self.lock, self.factory() as db:
                job = db.get(MatchJob, job_id)
                job.status, job.error_code = 'DONE', ''
                db.commit()
            return matched
        except Exception as error:
            # Do not persist HTTP response bodies, request data, secrets, or exception reprs.
            with self.lock, self.factory() as db:
                job = db.get(MatchJob, job_id)
                job.error_code = 'model_unavailable' if isinstance(error, ModelUnavailable) else 'matching_error'
                job.status = 'FAILED' if job.attempts >= self.settings.match_attempts else 'PENDING'
                job.available_at = now() + timedelta(seconds=min(60, 2 ** job.attempts))
                db.commit()
            return []

    def _match(self, intent_id, item_id=None):
        # Migrated and edited wanted posts acquire vectors in a retryable job.
        with self.factory() as db:
            intent = db.get(Intent, intent_id)
            if not intent or intent.status != 'ACTIVE':
                return []
            missing_vector = self.settings.embedding_mode == 'remote' and intent.embedding is None
            spec = intent_data(intent)
        if missing_vector:
            vector = embed(' '.join(spec['keywords']), self.settings)
            with self.lock, self.factory() as db:
                intent = db.scalar(select(Intent).where(Intent.id == intent_id).with_for_update())
                if not intent or intent.status != 'ACTIVE' or intent_data(intent) != spec:
                    return []
                intent.embedding, intent.embedding_model = vector, model_name(self.settings)
                db.commit()
        with self.factory() as db:
            intent = db.get(Intent, intent_id)
            if not intent or intent.status != 'ACTIVE':
                return []
            spec = intent_data(intent)
            existing = set(db.scalars(select(Notification.item_id).where(Notification.intent_id == intent_id)))
            # Exclude already assessed pairs before spending any model tokens.
            candidates = recall_candidates_for_intent(
                db, intent, self.settings, item_id=item_id, exclude_item_ids=existing, limit=10
            )
        # All provider work happens after the read session has closed.
        if self.settings.ai_mode == 'remote':
            reviews = review_candidates(spec, [i for i, _ in candidates], self.settings)
        else:
            reviews = [local_review(spec, i) for i, _ in candidates]
        snapshots = {i['id']: i for i, _ in candidates}
        scores = {i['id']: score for i, score in candidates}
        result = []
        with self.lock, self.factory() as db:
            intent = db.scalar(select(Intent).where(Intent.id == intent_id).with_for_update())
            if not intent or intent_data(intent) != spec:
                return []
            for review in reviews:
                if review.verdict == 'NO_MATCH':
                    continue
                item = db.scalar(select(Item).where(Item.id == review.item_id).with_for_update())
                if not item or not eligible(item, intent) or item_data(item) != snapshots[item.id]:
                    continue
                reasons = [f'售价 ¥{item.price_cents / 100:g}', item.campus, item.condition_grade]
                if intent.max_price_cents is not None:
                    reasons[0] += f'，在 ¥{intent.max_price_cents / 100:g} 预算内'
                if self.settings.ai_mode == 'local':
                    reasons.append('关键词命中：' + '、'.join(e.criterion for e in review.evidence))
                else:
                    reasons.append('模型判断：' + ('硬条件符合商品描述' if review.verdict == 'MATCH' else '部分条件尚待确认'))
                if intent.preferences:
                    reasons.append('偏好仅供参考，不作为硬性门槛')
                try:
                    with db.begin_nested():
                        db.add(Notification(buyer_id=intent.buyer_id, intent_id=intent.id, item_id=item.id,
                                            score=round(scores[item.id], 4), reason=' · '.join(reasons),
                                            verdict=review.verdict, questions=review.questions,
                                            evidence=[e.model_dump() for e in review.evidence], review_mode=self.settings.ai_mode))
                        db.flush()
                except IntegrityError:
                    pass
                result.append(item.id)
            db.commit()
        return result
