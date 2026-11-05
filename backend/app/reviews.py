"""Two-sided trade reviews collected after both sides confirm a deal.

A review belongs to one confirmed conversation. Each participant may review
the other exactly once; reading a review never republishes a withdrawn or
hidden item. Public aggregates are available without login so buyers can
judge a seller before contacting.
"""
from fastapi import Depends, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import func, select

from .item_lifecycle import PUBLIC_ITEM_STATES
from .models import Conversation, Item, TradeReview, User, now
from .schemas import StrictModel
from .services import log

REVIEW_TAGS = ['描述相符', '沟通顺畅', '准时守约', '包装仔细', '态度友好']


class TradeReviewCreate(StrictModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(default='', max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=5)

    @field_validator('tags')
    @classmethod
    def known_tags(cls, value):
        cleaned = [tag.strip() for tag in value]
        if any(tag not in REVIEW_TAGS for tag in cleaned):
            raise ValueError('请选择有效的评价标签')
        return list(dict.fromkeys(cleaned))


def register_reviews(app, get_db, require_user, mutation_lock):
    def iso(value):
        return value.isoformat() + 'Z'

    def review_out(db, review):
        reviewer = db.get(User, review.reviewer_id)
        item = db.get(Item, review.item_id)
        title = item.title if item and item.status in PUBLIC_ITEM_STATES else '已结束的交易'
        return {
            'id': review.id,
            'conversation_id': review.conversation_id,
            'item_id': review.item_id,
            'item_title': title,
            'reviewer_id': review.reviewer_id,
            'reviewee_id': review.reviewee_id,
            'reviewer': {'id': reviewer.id, 'nickname': reviewer.nickname,
                         'campus': reviewer.campus, 'role': reviewer.role} if reviewer else None,
            'rating': review.rating,
            'body': review.body,
            'tags': review.tags,
            'created_at': iso(review.created_at),
        }

    def summarize(db, user_id):
        rows = db.execute(
            select(TradeReview.rating, func.count(TradeReview.id))
            .where(TradeReview.reviewee_id == user_id)
            .group_by(TradeReview.rating)
        ).all()
        counts = {rating: count for rating, count in rows}
        total = sum(counts.values())
        average = round(sum(rating * count for rating, count in counts.items()) / total, 1) if total else None
        return {
            'average': average,
            'count': total,
            'distribution': [{'rating': rating, 'count': counts.get(rating, 0)} for rating in range(5, 0, -1)],
        }

    @app.get('/api/v1/users/{user_id}/reviews')
    def user_reviews(user_id: str, limit: int = Query(20, ge=1, le=50),
                     offset: int = Query(0, ge=0), db=Depends(get_db)):
        target = db.get(User, user_id)
        if not target:
            raise HTTPException(404, '用户不存在')
        rows = db.scalars(
            select(TradeReview).where(TradeReview.reviewee_id == user_id)
            .order_by(TradeReview.created_at.desc(), TradeReview.id.desc())
            .offset(offset).limit(limit)
        ).all()
        return {
            'user': {'id': target.id, 'nickname': target.nickname,
                     'campus': target.campus, 'role': target.role},
            'summary': summarize(db, user_id),
            'reviews': [review_out(db, review) for review in rows],
        }

    @app.get('/api/v1/conversations/{conversation_id}/reviews')
    def conversation_reviews(conversation_id: str, db=Depends(get_db), user=Depends(require_user)):
        conversation = db.get(Conversation, conversation_id)
        if not conversation or user.id not in {conversation.buyer_id, conversation.seller_id}:
            raise HTTPException(404, '会话不存在')
        rows = db.scalars(
            select(TradeReview).where(TradeReview.conversation_id == conversation_id)
            .order_by(TradeReview.created_at)
        ).all()
        mine = any(review.reviewer_id == user.id for review in rows)
        return {
            'deal_status': conversation.deal_status,
            'can_review': conversation.deal_status == 'CONFIRMED' and not mine,
            'reviews': [review_out(db, review) for review in rows],
        }

    @app.post('/api/v1/conversations/{conversation_id}/reviews', status_code=201)
    def create_review(conversation_id: str, data: TradeReviewCreate,
                      db=Depends(get_db), user=Depends(require_user)):
        with mutation_lock:
            conversation = db.scalar(
                select(Conversation).where(Conversation.id == conversation_id).with_for_update()
            )
            if not conversation or user.id not in {conversation.buyer_id, conversation.seller_id}:
                raise HTTPException(404, '会话不存在')
            if conversation.deal_status != 'CONFIRMED':
                raise HTTPException(409, '双方确认成交后才能评价')
            if db.scalar(select(TradeReview.id).where(
                    TradeReview.conversation_id == conversation_id,
                    TradeReview.reviewer_id == user.id)):
                raise HTTPException(409, '你已评价过本次交易')
            reviewee_id = conversation.seller_id if user.id == conversation.buyer_id else conversation.buyer_id
            review = TradeReview(
                conversation_id=conversation.id,
                item_id=conversation.item_id,
                reviewer_id=user.id,
                reviewee_id=reviewee_id,
                rating=data.rating,
                body=data.body.strip(),
                tags=data.tags,
                created_at=now(),
            )
            db.add(review)
            db.flush()
            log(db, user, 'trade.review', review.id, f'rating={data.rating}')
            db.commit()
            return review_out(db, review)
