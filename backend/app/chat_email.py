"""Durable, user-controlled reminders for unread chat messages.

Polling only sees committed messages, so mail never runs in a chat transaction.
Atomic leases prevent simultaneous workers claiming a conversation/recipient;
per-message receipts survive restarts without relying on timestamp ordering.
SMTP cannot provide exactly-once delivery: a crash after SMTP acceptance and
before committing receipts can cause a retry. Stable Message-IDs help providers
deduplicate that case, but cannot guarantee it.
"""
import hashlib
import logging
import smtplib
import ssl
import threading
from datetime import datetime, timedelta
from email.message import EmailMessage

import certifi
from sqlalchemy import DateTime, ForeignKey, Integer, String, and_, case, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from .email_auth import normalize_pku_email
from .item_lifecycle import PUBLIC_ITEM_STATES
from .models import Base, ChatAttachment, ChatMessage, Conversation, Item, User, UserBlock, now, uid


logger = logging.getLogger(__name__)
LEASE_SECONDS = 600


class ChatEmailQueue(Base):
    __tablename__ = 'chat_email_queue'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), primary_key=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatEmailReceipt(Base):
    __tablename__ = 'chat_email_receipts'
    message_id: Mapped[str] = mapped_column(ForeignKey('chat_messages.id', ondelete='CASCADE'), primary_key=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime)


def _blocked(first, second):
    return exists(select(UserBlock.blocker_id).where(or_(
        and_(UserBlock.blocker_id == first, UserBlock.blocked_id == second),
        and_(UserBlock.blocker_id == second, UserBlock.blocked_id == first),
    )))


def _not_delivered(recipient):
    return ~exists(select(ChatEmailReceipt.message_id).where(
        ChatEmailReceipt.message_id == ChatMessage.id,
        ChatEmailReceipt.recipient_id == recipient,
    ))


def _discover(factory, settings, at, limit):
    recipient = case((ChatMessage.sender_id == Conversation.buyer_id, Conversation.seller_id),
                     else_=Conversation.buyer_id)
    with factory() as db:
        candidates = db.execute(select(Conversation.id, User.id, func.min(ChatMessage.created_at))
            .select_from(ChatMessage)
            .join(Conversation, Conversation.id == ChatMessage.conversation_id)
            .join(User, User.id == recipient)
            .outerjoin(ChatEmailQueue, and_(ChatEmailQueue.conversation_id == Conversation.id,
                                           ChatEmailQueue.recipient_id == User.id))
            .where(ChatMessage.sender_id.in_([Conversation.buyer_id, Conversation.seller_id]),
                   ChatMessage.read_at.is_(None), ChatMessage.hidden_at.is_(None),
                   ChatMessage.created_at <= at - timedelta(seconds=settings.chat_email_delay_seconds),
                   User.email_notifications.is_(True), User.email.is_not(None),
                   ~User.id.like('demo-%'), ~ChatMessage.sender_id.like('demo-%'),
                   ~_blocked(User.id, ChatMessage.sender_id), _not_delivered(User.id),
                   or_(ChatEmailQueue.conversation_id.is_(None), and_(
                       ChatEmailQueue.next_attempt_at <= at,
                       or_(ChatEmailQueue.lease_until.is_(None), ChatEmailQueue.lease_until <= at),
                       or_(ChatEmailQueue.last_sent_at.is_(None),
                           ChatEmailQueue.last_sent_at <= at - timedelta(seconds=settings.chat_email_cooldown_seconds)),
                   )))
            .group_by(Conversation.id, User.id)
            .order_by(func.min(ChatMessage.created_at), Conversation.id, User.id)
            .limit(limit)).all()
    for conversation_id, recipient_id, oldest in candidates:
        # Savepoints make concurrent discovery harmless on SQLite and PostgreSQL.
        with factory.begin() as db:
            if db.get(ChatEmailQueue, (conversation_id, recipient_id)) is None:
                try:
                    with db.begin_nested():
                        db.add(ChatEmailQueue(conversation_id=conversation_id, recipient_id=recipient_id,
                                             next_attempt_at=oldest + timedelta(seconds=settings.chat_email_delay_seconds)))
                        db.flush()
                except IntegrityError:
                    pass
    return [(conversation_id, recipient_id) for conversation_id, recipient_id, _ in candidates]


def _claim(factory, key, settings, at):
    token = uid()
    with factory.begin() as db:
        claimed = db.execute(update(ChatEmailQueue).where(
            ChatEmailQueue.conversation_id == key[0], ChatEmailQueue.recipient_id == key[1],
            ChatEmailQueue.next_attempt_at <= at,
            or_(ChatEmailQueue.lease_until.is_(None), ChatEmailQueue.lease_until <= at),
            or_(ChatEmailQueue.last_sent_at.is_(None),
                ChatEmailQueue.last_sent_at <= at - timedelta(seconds=settings.chat_email_cooldown_seconds)),
        ).values(lease_token=token, lease_until=at + timedelta(seconds=LEASE_SECONDS))).rowcount
    return token if claimed else None


def _line(value, limit):
    return ' '.join(value.split())[:limit]


def _prepare(factory, key, token, settings, at):
    """Recheck privacy and unread state in a fresh session just before SMTP."""
    with factory() as db:
        queue = db.get(ChatEmailQueue, key)
        if not queue or queue.lease_token != token:
            return None
        conversation = db.get(Conversation, key[0])
        recipient = db.get(User, key[1])
        if not conversation or not recipient or not recipient.email_notifications or recipient.id.startswith('demo-'):
            return None
        if recipient.id not in {conversation.buyer_id, conversation.seller_id}:
            return None
        address = normalize_pku_email(recipient.email or '')
        sender_id = conversation.seller_id if recipient.id == conversation.buyer_id else conversation.buyer_id
        if not address or sender_id.startswith('demo-') or db.scalar(select(_blocked(recipient.id, sender_id))):
            return None
        messages = db.scalars(select(ChatMessage).where(
            ChatMessage.conversation_id == conversation.id, ChatMessage.sender_id == sender_id,
            ChatMessage.read_at.is_(None), ChatMessage.hidden_at.is_(None), _not_delivered(recipient.id),
        ).order_by(ChatMessage.created_at, ChatMessage.id).limit(100)).all()
        if not messages or messages[0].created_at > at - timedelta(seconds=settings.chat_email_delay_seconds):
            return None
        sender = db.get(User, sender_id)
        item = db.get(Item, conversation.item_id)
        title = item.title if item and item.status in PUBLIC_ITEM_STATES else '已停止展示的商品'
        nickname = _line(sender.nickname if sender else '对方', 50)
        title = _line(title, 120)
        message_ids = [message.id for message in messages]
        message = EmailMessage()
        message['Subject'] = f'燕渡：{nickname} 发来 {len(messages)} 条未读消息'
        message['From'] = settings.smtp_from
        message['To'] = address
        identity = hashlib.sha256((recipient.id + ':' + ':'.join(sorted(message_ids))).encode()).hexdigest()
        message['Message-ID'] = f'<chat-{identity}@yandu.local>'
        preview = _line(messages[-1].body, 160)
        if db.scalar(select(exists().where(ChatAttachment.message_id == messages[-1].id))):
            preview = ('[图片] ' + preview).strip()
        url = settings.public_app_url.rstrip('/') + '/#messages/' + conversation.id
        message.set_content(f'{nickname} 在“{title}”的会话中发来 {len(messages)} 条未读消息。\n\n'
                            f'最新消息：{preview}\n\n查看并回复：{url}\n\n'
                            '请在燕渡网站内回复，此邮箱不接收聊天回复。\n'
                            '你可以在燕渡的个人主页关闭未读站内信邮件提醒。')
        return message, message_ids


def send_chat_email(settings, message):
    """Use the same verified TLS transport as registration mail."""
    context = ssl.create_default_context(cafile=certifi.where())
    implicit_tls = settings.smtp_port in {465, 994}
    client = (smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=8, context=context)
              if implicit_tls else smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=8))
    with client:
        if not implicit_tls:
            client.starttls(context=context)
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(message)


def _finish(factory, key, token, settings, at, *, message_ids=None, failed=False):
    with factory.begin() as db:
        # A token-conditioned write obtains the row lock before recording receipts.
        if not db.execute(update(ChatEmailQueue).where(
            ChatEmailQueue.conversation_id == key[0], ChatEmailQueue.recipient_id == key[1],
            ChatEmailQueue.lease_token == token,
        ).values(lease_until=None)).rowcount:
            return
        queue = db.get(ChatEmailQueue, key)
        queue.lease_token = None
        if message_ids:
            # Retention can remove messages while SMTP is in flight.
            retained_ids = db.scalars(select(ChatMessage.id).where(ChatMessage.id.in_(message_ids))).all()
            for message_id in retained_ids:
                if db.get(ChatEmailReceipt, (message_id, key[1])) is None:
                    db.add(ChatEmailReceipt(message_id=message_id, recipient_id=key[1], sent_at=at))
            queue.last_sent_at = at
            queue.attempts = 0
            queue.next_attempt_at = at + timedelta(seconds=settings.chat_email_cooldown_seconds)
        elif failed:
            queue.attempts += 1
            queue.next_attempt_at = at + timedelta(seconds=min(3600, 30 * 2 ** min(queue.attempts - 1, 7)))
        else:
            queue.attempts = 0
            queue.next_attempt_at = at + timedelta(seconds=30)


def process_chat_email_batch(factory, settings, *, at=None, batch_size=20, stop_event=None):
    """Send at most batch_size reminders. Returns the number accepted by SMTP.

    No SMTP call runs while a database transaction or the app mutation lock is
    held. Unconfigured/disabled delivery leaves existing queue rows untouched.
    """
    if not settings.chat_email_ready:
        return 0
    instant = at or now()
    sent = 0
    # A larger discovery window lets temporarily leased or retrying rows yield.
    candidates = _discover(factory, settings, instant, max(batch_size * 10, 100))
    claimed = 0
    for key in candidates:
        if claimed >= batch_size or (stop_event and stop_event.is_set()):
            break
        token = _claim(factory, key, settings, instant)
        if token is None:
            continue
        claimed += 1
        try:
            prepared = _prepare(factory, key, token, settings, instant)
            if not prepared or not settings.chat_email_ready:
                _finish(factory, key, token, settings, at or now())
                continue
            message, message_ids = prepared
            send_chat_email(settings, message)
        except Exception:
            # SMTP exceptions may contain addresses, credentials, or message text.
            logger.warning('Chat reminder delivery deferred; a retry is scheduled')
            _finish(factory, key, token, settings, at or now(), failed=True)
        else:
            _finish(factory, key, token, settings, at or now(), message_ids=message_ids)
            sent += 1
    return sent


class ChatEmailRunner:
    def __init__(self, factory, settings):
        self.factory, self.settings = factory, settings
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if not self.settings.chat_email_enabled or self.thread:
            return
        self.thread = threading.Thread(target=self._work, name='yandu-chat-email', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=50)

    def _work(self):
        while not self.stop_event.is_set():
            try:
                process_chat_email_batch(self.factory, self.settings, stop_event=self.stop_event)
            except Exception:
                logger.warning('Chat reminder worker will retry after an internal failure')
            self.stop_event.wait(30)
