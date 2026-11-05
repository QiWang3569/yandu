from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text

from app.config import Settings
from app.email_auth import send_verification_email
from app.main import create_app
from app.models import ChatMessage, EmailChallenge, Item, User, now
from conftest import login


def email_client(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr('app.main.send_verification_email', lambda settings, email, code: sent.append((email, code)))
    settings = Settings(database_url=f'sqlite:///{tmp_path / "email.db"}', data_dir=tmp_path,
                        demo_mode=False, ai_mode='local', auth_secret='s' * 32,
                        smtp_host='mail.example', smtp_from='noreply@example.com')
    return create_app(settings), sent


@pytest.mark.parametrize('smtp_port', [465, 994])
def test_smtp_sender_uses_tls_and_addresses_only_verified_recipient(monkeypatch, smtp_port):
    sent = []
    class FakeSMTP:
        def __init__(self, host, port, timeout, context=None):
            assert host == 'mail.example' and port == smtp_port and timeout == 8 and context is not None
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def login(self, user, password): assert (user, password) == ('sender', 'test-password')
        def send_message(self, message): sent.append(message)
    monkeypatch.setattr('app.email_auth.smtplib.SMTP_SSL', FakeSMTP)
    settings = Settings(smtp_host='mail.example', smtp_port=smtp_port, smtp_user='sender',
                        smtp_password='test-password', smtp_from='notice@example.com')
    send_verification_email(settings, 'student@pku.edu.cn', '12345678')
    assert len(sent) == 1 and sent[0]['To'] == 'student@pku.edu.cn'
    assert '12345678' in sent[0].get_content()


def test_verified_pku_mail_creates_user_and_reuses_account(tmp_path, monkeypatch):
    app, sent = email_client(tmp_path, monkeypatch)
    with TestClient(app) as client:
        for bad in ('student@gmail.com', 'student@notpku.edu.cn', 'student@x.pku.edu.cn', 'student@stu.pku.edu.cn.evil'):
            assert client.post('/api/v1/auth/email/request-code', json={'email': bad}).status_code == 422
        assert client.post('/api/v1/auth/email/request-code', json={'email': ' Student@STU.PKU.EDU.CN '}).status_code == 200
        assert sent[0][0] == 'student@stu.pku.edu.cn'
        assert client.post('/api/v1/auth/email/verify', json={'email': sent[0][0], 'code': '00000000', 'nickname': '北大同学'}).status_code == 400
        result = client.post('/api/v1/auth/email/verify', json={'email': sent[0][0], 'code': sent[0][1],
                            'nickname': '北大同学', 'campus': '燕园校本部', 'intent': 'register',
                            'password': 'CampusLife9'})
        assert result.status_code == 200, result.text
        user = result.json()['user']
        assert user['role'] == 'student' and user['email'] == sent[0][0]
        assert client.get('/api/v1/auth/me').json()['user']['id'] == user['id']
        assert user['email_notifications'] is True
        assert client.post('/api/v1/auth/email/verify', json={'email': sent[0][0], 'code': sent[0][1]}).status_code == 400
        assert client.post('/api/v1/auth/logout').status_code == 200
        with app.state.session_factory() as db:
            challenge = db.get(EmailChallenge, sent[0][0])
            assert challenge is None
        assert client.post('/api/v1/auth/email/request-code', json={'email': sent[0][0]}).status_code == 200
        repeat = client.post('/api/v1/auth/email/verify', json={'email': sent[-1][0], 'code': sent[-1][1],
                              'intent': 'login'})
        assert repeat.status_code == 200 and repeat.json()['user']['id'] == user['id']
        client.post('/api/v1/auth/logout')
        assert client.post('/api/v1/auth/email/request-code', json={'email': 'someone@pku.edu.cn'}).status_code == 200
        existing = client.post('/api/v1/auth/email/verify', json={'email': sent[-1][0], 'code': sent[-1][1],
                               'nickname': '另一位同学', 'password': 'NewCampus9', 'intent': 'register'})
        assert existing.status_code == 200 and existing.json()['user']['id'] != user['id']
        with app.state.session_factory() as db:
            assert db.scalar(select(User).where(User.email == 'student@stu.pku.edu.cn')).role == 'student'


def test_email_code_limits_and_unconfigured_service(tmp_path, monkeypatch):
    app, sent = email_client(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/email/request-code', json={'email': 'a@pku.edu.cn'}).status_code == 200
        assert client.post('/api/v1/auth/email/request-code', json={'email': 'a@pku.edu.cn'}).status_code == 429
        for _ in range(5):
            assert client.post('/api/v1/auth/email/verify', json={'email': 'a@pku.edu.cn', 'code': '99999999'}).status_code == 400
        assert client.post('/api/v1/auth/email/verify', json={'email': 'a@pku.edu.cn', 'code': sent[0][1], 'nickname': '北大同学'}).status_code == 400
        with app.state.session_factory() as db:
            challenge = db.get(EmailChallenge, 'a@pku.edu.cn')
            challenge.sent_at = now() - timedelta(minutes=2)
            db.commit()
        assert client.post('/api/v1/auth/email/request-code', json={'email': 'a@pku.edu.cn'}).status_code == 200
    no_mail = create_app(Settings(database_url=f'sqlite:///{tmp_path / "no-mail.db"}', data_dir=tmp_path,
                                  demo_mode=False, ai_mode='local'))
    with TestClient(no_mail) as client:
        assert client.post('/api/v1/auth/email/request-code', json={'email': 'a@pku.edu.cn'}).status_code == 503
        assert client.post('/api/v1/auth/demo', json={'profile': 'admin'}).status_code == 503


def test_chat_is_private_persistent_and_tracks_read_state(client, app):
    assert client.get('/api/v1/conversations').status_code == 401
    login(client, 'seller')
    assert client.post('/api/v1/items/sample-1/conversations', json={'body': '我的商品'}).status_code == 403
    login(client, 'buyer')
    assert client.post('/api/v1/items/sample-1/conversations', json={'body': '  '}).status_code == 422
    started = client.post('/api/v1/items/sample-1/conversations', json={'body': '请问还在售吗？'})
    assert started.status_code == 201, started.text
    conversation_id = started.json()['conversation']['id']
    assert client.get('/api/v1/conversations').json()[0]['counterpart']['id'] == 'demo-seller'
    assert client.get(f'/api/v1/conversations/{conversation_id}/messages').json()['messages'][0]['body'] == '请问还在售吗？'
    login(client, 'admin')
    assert client.get('/api/v1/conversations').json() == []
    assert client.get(f'/api/v1/conversations/{conversation_id}/messages').status_code == 404
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '窥探'}).status_code == 404
    login(client, 'seller')
    assert client.get('/api/v1/conversations').json()[0]['unread_count'] == 1
    assert client.post(f'/api/v1/conversations/{conversation_id}/read', json={'ids': [started.json()['message']['id']]}).status_code == 200
    assert client.get('/api/v1/conversations').json()[0]['unread_count'] == 0
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '还在，可以当面看。'}).status_code == 201
    login(client, 'buyer')
    assert client.get('/api/v1/conversations').json()[0]['unread_count'] == 1
    assert len(client.get(f'/api/v1/conversations/{conversation_id}/messages').json()['messages']) == 2
    with app.state.session_factory() as db:
        assert db.scalar(select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)) is not None
        db.get(Item, 'sample-1').status = 'SOLD'
        db.commit()
    assert client.post('/api/v1/items/sample-1/conversations', json={'body': '新咨询'}).status_code == 409
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '知道了，谢谢'}).status_code == 201


def test_chat_survives_restart(tmp_path):
    settings = Settings(database_url=f'sqlite:///{tmp_path / "chat.db"}', data_dir=tmp_path, demo_mode=True, ai_mode='local')
    with TestClient(create_app(settings)) as client:
        login(client)
        created = client.post('/api/v1/items/sample-1/conversations', json={'body': '我想看看商品'})
        conversation_id = created.json()['conversation']['id']
    with TestClient(create_app(settings)) as client:
        login(client)
        assert client.get('/api/v1/conversations').json()[0]['id'] == conversation_id
        assert client.get(f'/api/v1/conversations/{conversation_id}/messages').json()['messages'][0]['body'] == '我想看看商品'


def test_pre_email_user_table_gets_additive_upgrade(tmp_path):
    url = f'sqlite:///{tmp_path / "old-users.db"}'
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, nickname VARCHAR(50) NOT NULL, campus VARCHAR(30) NOT NULL, role VARCHAR(20) NOT NULL, contact VARCHAR(100) NOT NULL)'))
    engine.dispose()
    settings = Settings(database_url=url, data_dir=tmp_path, demo_mode=True, ai_mode='local')
    with TestClient(create_app(settings)) as client:
        login(client)
        assert client.get('/api/v1/auth/me').json()['user']['email'] is None
        assert client.get('/api/v1/auth/me').json()['user']['bio'] == ''
        assert client.get('/api/v1/auth/me').json()['user']['avatar_color'] == 'sage'
        assert client.get('/api/v1/auth/me').json()['user']['has_password'] is False
        with client.app.state.session_factory() as db:
            assert db.get(User, 'demo-buyer').password_hash is None
        assert client.get('/api/v1/conversations').json() == []
