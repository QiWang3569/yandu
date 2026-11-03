from datetime import datetime, timezone
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, func, true
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def uid():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    nickname: Mapped[str] = mapped_column(String(50))
    campus: Mapped[str] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(20), default='student')
    contact: Mapped[str] = mapped_column(String(100), default='')
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    email_notifications: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bio: Mapped[str] = mapped_column(String(160), default='')
    avatar_color: Mapped[str] = mapped_column(String(20), default='sage')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, server_default=func.now())


class EmailChallenge(Base):
    __tablename__ = 'email_challenges'
    email: Mapped[str] = mapped_column(String(254), primary_key=True)
    challenge_id: Mapped[str] = mapped_column(String(36), default=uid)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    sent_at: Mapped[datetime] = mapped_column(DateTime)
    window_started_at: Mapped[datetime] = mapped_column(DateTime)
    sends_in_window: Mapped[int] = mapped_column(Integer, default=1)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class PasswordAttempt(Base):
    __tablename__ = 'password_attempts'
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime] = mapped_column(DateTime)


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    item_id: Mapped[str] = mapped_column(ForeignKey('items.id'))
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_message_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    deal_status: Mapped[str] = mapped_column(String(20), default='NONE')
    # Per-participant "delete from my list" markers. A new message restores the chat.
    buyer_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    seller_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint('item_id', 'buyer_id'), Index('idx_conversation_buyer', 'buyer_id', 'last_message_at'), Index('idx_conversation_seller', 'seller_id', 'last_message_at'))


class ChatMessage(Base):
    __tablename__ = 'chat_messages'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'))
    sender_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (Index('idx_chat_messages_conversation', 'conversation_id', 'created_at'),)


class ChatAttachment(Base):
    __tablename__ = 'chat_attachments'
    path: Mapped[str] = mapped_column(ForeignKey('uploads.path', ondelete='CASCADE'), primary_key=True)
    message_id: Mapped[str] = mapped_column(ForeignKey('chat_messages.id', ondelete='CASCADE'), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)


class UserBlock(Base):
    __tablename__ = 'user_blocks'
    blocker_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    blocked_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ChatReport(Base):
    __tablename__ = 'chat_reports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    reporter_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    message_id: Mapped[str] = mapped_column(ForeignKey('chat_messages.id'))
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint('reporter_id', 'message_id'),
                      Index('idx_chat_reports_status', 'status', 'created_at'))


class Item(Base):
    __tablename__ = 'items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default='')
    category: Mapped[str] = mapped_column(String(30))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    price_cents: Mapped[int] = mapped_column(Integer)
    campus: Mapped[str] = mapped_column(String(30))
    condition_grade: Mapped[str] = mapped_column(String(20), default='95新')
    images: Mapped[list] = mapped_column(JSON, default=list)
    art: Mapped[str] = mapped_column(String(30), default='box')
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE')
    embedding: Mapped[list | None] = mapped_column(JSON().with_variant(Vector(1536), 'postgresql'), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(100), default='local-keyword')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index('idx_items_filter', 'status', 'category', 'campus', 'price_cents'),)


class ItemDraft(Base):
    __tablename__ = 'item_drafts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    seller_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    raw: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campus: Mapped[str] = mapped_column(String(30), default='燕园校本部')
    condition_grade: Mapped[str] = mapped_column(String(20), default='95新')
    tags: Mapped[list] = mapped_column(JSON, default=list)
    images: Mapped[list] = mapped_column(JSON, default=list)
    clarification: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index('idx_item_drafts_seller', 'seller_id', 'created_at'),)


class Intent(Base):
    __tablename__ = 'buyer_intents'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    raw_query: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    max_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campus: Mapped[str] = mapped_column(String(30), default='不限校区')
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    excluded_keywords: Mapped[list] = mapped_column(JSON, default=list)
    preferences: Mapped[list] = mapped_column(JSON, default=list)
    condition_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE')
    completed_item_id: Mapped[str | None] = mapped_column(ForeignKey('items.id'), nullable=True)
    embedding: Mapped[list | None] = mapped_column(JSON().with_variant(Vector(1536), 'postgresql'), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(100), default='local-keyword')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index('idx_intents_active', 'status'),)


class SaleFeedback(Base):
    __tablename__ = 'sale_feedback'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    reporter_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    item_id: Mapped[str] = mapped_column(ForeignKey('items.id'))
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (UniqueConstraint('reporter_id', 'item_id'),)


class TradeReview(Base):
    """One review per participant after a confirmed deal."""
    __tablename__ = 'trade_reviews'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'))
    item_id: Mapped[str] = mapped_column(ForeignKey('items.id'))
    reviewer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    reviewee_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    rating: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text, default='')
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (UniqueConstraint('conversation_id', 'reviewer_id'),
                      Index('idx_trade_reviews_reviewee', 'reviewee_id', 'created_at'))


class Notification(Base):
    __tablename__ = 'match_notifications'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    intent_id: Mapped[str] = mapped_column(ForeignKey('buyer_intents.id'))
    item_id: Mapped[str] = mapped_column(ForeignKey('items.id'))
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(String(20), default='MATCH')
    questions: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    review_mode: Mapped[str] = mapped_column(String(20), default='local')
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (UniqueConstraint('intent_id', 'item_id'),)


class Announcement(Base):
    __tablename__ = 'announcements'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default='公告')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index('idx_announcements_active', 'active', 'created_at'),)


class AnnouncementRead(Base):
    __tablename__ = 'announcement_reads'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    announcement_id: Mapped[str] = mapped_column(ForeignKey('announcements.id'), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class MatchJob(Base):
    __tablename__ = 'match_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(20))
    target_id: Mapped[str] = mapped_column(String(36))
    item_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    error_code: Mapped[str] = mapped_column(String(40), default='')
    __table_args__ = (Index('idx_match_jobs_pending', 'status', 'available_at'),)


class Favorite(Base):
    __tablename__ = 'favorites'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey('items.id'), primary_key=True)


class Wanted(Base):
    __tablename__ = 'wanted_posts'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    buyer_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(30), nullable=True)
    budget_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campus: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default='ACTIVE')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    intent_id: Mapped[str | None] = mapped_column(ForeignKey('buyer_intents.id'), nullable=True)
    __table_args__ = (Index('uq_wanted_intent', 'intent_id', unique=True),)


class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    reporter_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    item_id: Mapped[str] = mapped_column(ForeignKey('items.id'))
    reason: Mapped[str] = mapped_column(Text)
    risk: Mapped[str] = mapped_column(String(20))
    evidence: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class ActionLog(Base):
    __tablename__ = 'action_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(80))
    target_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Upload(Base):
    __tablename__ = 'uploads'
    path: Mapped[str] = mapped_column(String(200), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))


class Feedback(Base):
    __tablename__ = 'feedbacks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    category: Mapped[str] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(Text)
    page_path: Mapped[str] = mapped_column(String(500), default='')
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index('idx_feedback_user', 'user_id', 'updated_at'),
                      Index('idx_feedback_status', 'status', 'updated_at'))


class FeedbackReply(Base):
    __tablename__ = 'feedback_replies'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedbacks.id'), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class FeedbackAttachment(Base):
    __tablename__ = 'feedback_attachments'
    path: Mapped[str] = mapped_column(ForeignKey('uploads.path'), primary_key=True)
    feedback_id: Mapped[str | None] = mapped_column(ForeignKey('feedbacks.id'), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class FeedbackNotice(Base):
    __tablename__ = 'feedback_notices'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    feedback_id: Mapped[str] = mapped_column(ForeignKey('feedbacks.id'), index=True)
    body: Mapped[str] = mapped_column(String(200))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (Index('idx_feedback_notice_user', 'user_id', 'is_read', 'created_at'),)

class VisitorEvent(Base):
    __tablename__ = 'visitor_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    vid: Mapped[str] = mapped_column(String(32), index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, server_default=func.now())
    __table_args__ = (Index('idx_visitor_event', 'event_type', 'created_at'),)


class PageDwellLog(Base):
    __tablename__ = 'page_dwell_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    vid: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    page: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[str | None] = mapped_column(ForeignKey('items.id', ondelete='CASCADE'), nullable=True, index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, server_default=func.now())
    __table_args__ = (Index('idx_dwell_page_created', 'page', 'created_at'),)
