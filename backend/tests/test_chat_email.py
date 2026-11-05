from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import create_engine, delete, event, func, select
from sqlalchemy.orm import sessionmaker

from app import chat_email
from app.chat_email import ChatEmailQueue, ChatEmailReceipt, process_chat_email_batch, send_chat_email as smtp_send_chat_email
from app.config import Settings
from app.models import Base, ChatAttachment, ChatMessage, Conversation, Item, Upload, User, UserBlock


AT = datetime(2026, 10, 13, 12, 0)


@pytest.fixture
def maildb(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path / "mail.db"}', connect_args={'check_same_thread': False, 'timeout': 10})
    @event.listens_for(engine, 'connect')
    def sqlite_config(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA journal_mode=WAL')
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(chat_email_enabled=True, public_app_url='https://yandu.example',
                        smtp_host='smtp.example', smtp_from='yandu@example.org',
                        smtp_user='mail-user', smtp_password='test-password')
    with factory.begin() as db:
        db.add_all([
            User(id='buyer', nickname='买家', campus='燕园校本部', email='buyer@pku.edu.cn', email_notifications=False),
            User(id='seller', nickname='卖家', campus='燕园校本部', email='seller@stu.pku.edu.cn', email_notifications=True),
        ])
        db.flush()
        db.add(Item(id='item', seller_id='seller', title='鼠标', category='数码与影音', price_cents=1000,
                    campus='燕园校本部'))
        db.flush()
        db.add(Conversation(id='conversation', item_id='item', buyer_id='buyer', seller_id='seller'))
    sent = []
    def capture(_, message):
        assert engine.pool.checkedout() == 0, 'SMTP must not hold a database connection'
        sent.append(message)
    monkeypatch.setattr(chat_email, 'send_chat_email', capture)
    yield factory, settings, sent
    engine.dispose()


def add_message(factory, identity='message-1', *, created=AT - timedelta(minutes=6), sender='buyer',
                body='请问明天方便交易吗？', **fields):
    with factory.begin() as db:
        db.add(ChatMessage(id=identity, conversation_id='conversation', sender_id=sender,
                           body=body, created_at=created, **fields))


def test_delay_merge_delivery_and_persistent_receipts(maildb):
    factory, settings, sent = maildb
    add_message(factory, created=AT - timedelta(minutes=4))
    assert process_chat_email_batch(factory, settings, at=AT) == 0
    add_message(factory, 'message-2', created=AT - timedelta(minutes=1))
    add_message(factory, 'message-3', created=AT, body='<script>alert("test")</script>')
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(minutes=1)) == 1
    assert len(sent) == 1
    assert sent[0]['To'] == 'seller@stu.pku.edu.cn'
    assert sent[0]['From'] == 'yandu@example.org'
    assert sent[0]['Subject'] == '燕渡：买家 发来 3 条未读消息'
    assert sent[0].get_content_type() == 'text/plain'
    body = sent[0].get_content()
    assert '鼠标' in body and '<script>' in body
    assert 'https://yandu.example/#messages/conversation' in body
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatEmailReceipt)) == 3
    # A fresh session factory represents a restarted worker, with no memory cursor.
    restarted = sessionmaker(factory.kw['bind'], expire_on_commit=False)
    assert process_chat_email_batch(restarted, settings, at=AT + timedelta(days=1)) == 0


@pytest.mark.parametrize('body', ['', '这是商品细节'])
def test_image_mail_preview_keeps_attachments_private(maildb, body):
    factory, settings, sent = maildb
    add_message(factory, body=body)
    path = '/api/v1/chat-images/private-image.jpg'
    with factory.begin() as db:
        db.add(Upload(path=path, user_id='buyer'))
        db.flush()
        db.add(ChatAttachment(path=path, message_id='message-1', position=0))
    assert process_chat_email_batch(factory, settings, at=AT) == 1
    content = sent[0].get_content()
    assert '最新消息：[图片]' in content and body in content
    assert path not in content and not sent[0].is_multipart()
    assert 'https://yandu.example/#messages/conversation' in content


@pytest.mark.parametrize('reason', ['opt_out', 'no_email', 'invalid_email', 'demo_recipient', 'demo_sender',
                                    'read', 'hidden', 'blocked_by_recipient', 'blocked_by_sender'])
def test_ineligible_messages_never_send(maildb, reason):
    factory, settings, sent = maildb
    add_message(factory)
    with factory.begin() as db:
        recipient = db.get(User, 'seller')
        message = db.get(ChatMessage, 'message-1')
        if reason == 'opt_out':
            recipient.email_notifications = False
        elif reason == 'no_email':
            recipient.email = None
        elif reason == 'invalid_email':
            recipient.email = 'outsider@example.org'
        elif reason == 'read':
            message.read_at = AT
        elif reason == 'hidden':
            message.hidden_at = AT
        elif reason.startswith('blocked'):
            first, second = ('seller', 'buyer') if reason == 'blocked_by_recipient' else ('buyer', 'seller')
            db.add(UserBlock(blocker_id=first, blocked_id=second))
        elif reason == 'demo_recipient':
            db.add(User(id='demo-recipient', nickname='演示', campus='燕园校本部',
                        email='demo@pku.edu.cn', email_notifications=True))
            db.flush()
            db.get(Conversation, 'conversation').seller_id = 'demo-recipient'
        elif reason == 'demo_sender':
            db.add(User(id='demo-sender', nickname='演示', campus='燕园校本部'))
            db.flush()
            db.get(Conversation, 'conversation').buyer_id = 'demo-sender'
            message.sender_id = 'demo-sender'
    assert process_chat_email_batch(factory, settings, at=AT) == 0
    assert sent == []


@pytest.mark.parametrize('change', ['read', 'hide', 'opt_out', 'block'])
def test_state_is_rechecked_after_claim_before_smtp(maildb, monkeypatch, change):
    factory, settings, sent = maildb
    add_message(factory)
    claim = chat_email._claim
    def claim_then_change(*args):
        token = claim(*args)
        with factory.begin() as db:
            if change == 'read':
                db.get(ChatMessage, 'message-1').read_at = AT
            elif change == 'hide':
                db.get(ChatMessage, 'message-1').hidden_at = AT
            elif change == 'opt_out':
                db.get(User, 'seller').email_notifications = False
            else:
                db.add(UserBlock(blocker_id='seller', blocked_id='buyer'))
        return token
    monkeypatch.setattr(chat_email, '_claim', claim_then_change)
    assert process_chat_email_batch(factory, settings, at=AT) == 0
    assert sent == []
    with factory() as db:
        queue = db.get(ChatEmailQueue, ('conversation', 'seller'))
        assert queue.lease_token is None and queue.attempts == 0


def test_cooldown_and_each_recipient_has_independent_cursor(maildb):
    factory, settings, sent = maildb
    add_message(factory)
    assert process_chat_email_batch(factory, settings, at=AT) == 1
    add_message(factory, 'message-2', created=AT + timedelta(minutes=1))
    with factory.begin() as db:
        db.get(User, 'buyer').email_notifications = True
    add_message(factory, 'reply', created=AT, sender='seller')
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(minutes=6)) == 1
    assert sent[-1]['To'] == 'buyer@pku.edu.cn'
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(minutes=29)) == 0
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(minutes=30)) == 1
    assert sent[-1]['To'] == 'seller@stu.pku.edu.cn'
    assert '1 条未读消息' in sent[-1]['Subject']


def test_failure_retries_persist_and_do_not_log_exception_secrets(maildb, monkeypatch, caplog):
    factory, settings, sent = maildb
    add_message(factory)
    good_sender = chat_email.send_chat_email
    def fail(*_):
        raise RuntimeError('sensitive recipient and test-password')
    monkeypatch.setattr(chat_email, 'send_chat_email', fail)
    assert process_chat_email_batch(factory, settings, at=AT) == 0
    with factory() as db:
        queue = db.get(ChatEmailQueue, ('conversation', 'seller'))
        assert queue.attempts == 1
        assert queue.next_attempt_at == AT + timedelta(seconds=30)
        assert queue.lease_token is None
        assert db.scalar(select(func.count()).select_from(ChatEmailReceipt)) == 0
    assert 'test-password' not in caplog.text
    monkeypatch.setattr(chat_email, 'send_chat_email', good_sender)
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(seconds=29)) == 0
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(seconds=30)) == 1
    with factory() as db:
        assert db.get(ChatEmailQueue, ('conversation', 'seller')).attempts == 0


def test_retry_backoff_is_bounded(maildb, monkeypatch):
    factory, settings, _ = maildb
    add_message(factory)
    monkeypatch.setattr(chat_email, 'send_chat_email', lambda *_: (_ for _ in ()).throw(RuntimeError('failure')))
    current = AT
    for attempt in range(1, 11):
        assert process_chat_email_batch(factory, settings, at=current) == 0
        with factory() as db:
            queue = db.get(ChatEmailQueue, ('conversation', 'seller'))
            assert queue.attempts == attempt
            delay = (queue.next_attempt_at - current).total_seconds()
            assert delay == min(3600, 30 * 2 ** min(attempt - 1, 7))
            current = queue.next_attempt_at


def test_atomic_claim_and_expired_lease_recovery(maildb):
    factory, settings, sent = maildb
    add_message(factory)
    key = chat_email._discover(factory, settings, AT, 10)[0]
    barrier = Barrier(2)
    def claim():
        barrier.wait(timeout=5)
        return chat_email._claim(factory, key, settings, AT)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim(), range(2)))
    assert sum(token is not None for token in results) == 1
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(minutes=9)) == 0
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(minutes=10)) == 1
    assert len(sent) == 1


def test_message_timestamp_ties_do_not_skip_later_messages(maildb):
    factory, settings, sent = maildb
    add_message(factory, 'zzz')
    assert process_chat_email_batch(factory, settings, at=AT) == 1
    add_message(factory, 'aaa')  # Inserted later, but sorts before the old UUID.
    assert process_chat_email_batch(factory, settings, at=AT + timedelta(minutes=30)) == 1
    assert len(sent) == 2


def test_cooldown_backoff_and_leases_cannot_starve_later_conversation(maildb):
    factory, settings, sent = maildb
    # These older unread messages would fill the complete discovery window.
    with factory.begin() as db:
        for index in range(100):
            item_id, conversation_id = f'item-{index}', f'conversation-{index}'
            db.add(Item(id=item_id, seller_id='seller', title='旧商品', category='数码与影音',
                        price_cents=1000, campus='燕园校本部'))
            db.flush()
            db.add(Conversation(id=conversation_id, item_id=item_id, buyer_id='buyer', seller_id='seller'))
            db.flush()
            db.add(ChatMessage(id=f'old-{index}', conversation_id=conversation_id, sender_id='buyer',
                               body='旧消息', created_at=AT - timedelta(days=1)))
            fields = ({'next_attempt_at': AT - timedelta(minutes=1), 'last_sent_at': AT}
                      if index % 3 == 0 else
                      {'next_attempt_at': AT + timedelta(minutes=1)} if index % 3 == 1 else
                      {'next_attempt_at': AT - timedelta(minutes=1), 'lease_token': 'other-worker',
                       'lease_until': AT + timedelta(minutes=1)})
            db.add(ChatEmailQueue(conversation_id=conversation_id, recipient_id='seller', **fields))
    add_message(factory)
    assert process_chat_email_batch(factory, settings, at=AT, batch_size=1) == 1
    assert '/#messages/conversation\n' in sent[0].get_content()


def test_expired_claim_cannot_overwrite_a_new_worker_claim(maildb):
    factory, settings, _ = maildb
    add_message(factory)
    key = chat_email._discover(factory, settings, AT, 10)[0]
    old_token = chat_email._claim(factory, key, settings, AT)
    new_token = chat_email._claim(factory, key, settings, AT + timedelta(minutes=10))
    assert new_token and old_token != new_token
    chat_email._finish(factory, key, old_token, settings, AT, message_ids=['message-1'])
    with factory() as db:
        queue = db.get(ChatEmailQueue, key)
        assert queue.lease_token == new_token
        assert queue.last_sent_at is None
        assert db.scalar(select(func.count()).select_from(ChatEmailReceipt)) == 0


def test_hidden_item_title_and_header_linebreaks_do_not_leak(maildb):
    factory, settings, sent = maildb
    add_message(factory)
    with factory.begin() as db:
        db.get(Item, 'item').status = 'BANNED'
        db.get(User, 'buyer').nickname = '买家\r\nBcc: nobody@example.org'
    assert process_chat_email_batch(factory, settings, at=AT) == 1
    assert sent[0]['Bcc'] is None
    assert '鼠标' not in sent[0].get_content()
    assert '已停止展示的商品' in sent[0].get_content()


def test_disabled_or_unconfigured_delivery_does_nothing(maildb):
    factory, settings, sent = maildb
    add_message(factory)
    settings.chat_email_enabled = False
    assert process_chat_email_batch(factory, settings, at=AT) == 0
    settings.chat_email_enabled = True
    settings.smtp_host = ''
    assert process_chat_email_batch(factory, settings, at=AT) == 0
    assert sent == []
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatEmailQueue)) == 0


def test_receipts_do_not_prevent_chat_retention(maildb):
    factory, settings, _ = maildb
    add_message(factory)
    assert process_chat_email_batch(factory, settings, at=AT) == 1
    with factory.begin() as db:
        db.execute(delete(ChatMessage))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ChatEmailReceipt)) == 0


def test_retention_during_smtp_does_not_break_acknowledgement(maildb, monkeypatch):
    factory, settings, _ = maildb
    add_message(factory)
    def send_while_pruning(*_):
        with factory.begin() as db:
            db.execute(delete(ChatMessage))
    monkeypatch.setattr(chat_email, 'send_chat_email', send_while_pruning)
    assert process_chat_email_batch(factory, settings, at=AT) == 1
    with factory() as db:
        assert db.get(ChatEmailQueue, ('conversation', 'seller')).last_sent_at == AT


@pytest.mark.parametrize('port', [465, 587])
def test_smtp_transport_uses_tls_and_existing_credentials(maildb, monkeypatch, port):
    factory, settings, sent = maildb
    add_message(factory)
    assert process_chat_email_batch(factory, settings, at=AT) == 1
    calls = []
    class FakeSMTP:
        def __init__(self, host, smtp_port, **kwargs):
            calls.append(('connect', host, smtp_port, kwargs))
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def starttls(self, **kwargs):
            calls.append(('starttls', kwargs))
        def login(self, username, password):
            calls.append(('login', username, password))
        def send_message(self, message):
            calls.append(('send', message['To']))
    monkeypatch.setattr(chat_email.smtplib, 'SMTP', FakeSMTP)
    monkeypatch.setattr(chat_email.smtplib, 'SMTP_SSL', FakeSMTP)
    settings.smtp_port = port
    smtp_send_chat_email(settings, sent[0])
    assert calls[0][1:3] == ('smtp.example', port)
    assert calls[0][3]['timeout'] == 8
    assert ('login', 'mail-user', 'test-password') in calls
    assert ('send', 'seller@stu.pku.edu.cn') in calls
    assert any(call[0] == 'starttls' for call in calls) == (port == 587)
