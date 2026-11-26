from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.config import Settings
from app.admin_cli import set_admin_role
from app.main import create_app
from app.models import Base, ChatMessage, ChatReport, Conversation, Item, User, now
from app.retention import prune_chat
from conftest import intent, login


def start(client):
    login(client, 'buyer')
    result = client.post('/api/v1/items/sample-1/conversations', json={'body': '你好，还在售吗？'})
    assert result.status_code == 201, result.text
    return result.json()['conversation']['id'], result.json()['message']['id']


def test_chat_report_review_and_blocking(client):
    conversation_id, first_message = start(client)
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages/{first_message}/reports',
                       json={'reason': '自己发的消息'}).status_code == 404
    login(client, 'seller')
    reply = client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '请先给我转账'}).json()['id']
    login(client, 'buyer')
    path = f'/api/v1/conversations/{conversation_id}/messages/{reply}/reports'
    report = client.post(path, json={'reason': '要求提前转账，疑似诈骗'})
    assert report.status_code == 201
    assert client.post(path, json={'reason': '重复举报同一条消息'}).status_code == 409
    assert client.post(f'/api/v1/conversations/{conversation_id}/block').status_code == 200
    assert client.get('/api/v1/conversations').json()[0]['blocked_by_me']
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '新消息'}).status_code == 403
    login(client, 'seller')
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '新消息'}).status_code == 403
    assert client.get(f'/api/v1/conversations/{conversation_id}/messages').status_code == 200
    login(client, 'admin')
    assert client.get(f'/api/v1/conversations/{conversation_id}/messages').status_code == 404
    reports = client.get('/api/v1/admin/chat-reports').json()
    assert reports[0]['id'] == report.json()['id'] and reports[0]['message_body'] == '请先给我转账'
    review_path = f"/api/v1/admin/chat-reports/{report.json()['id']}/review"
    assert client.post(review_path, json={'action': 'hide', 'note': '核实为索要提前转账', 'confirmed': False}).status_code == 422
    assert client.post(review_path, json={'action': 'hide', 'note': '核实为索要提前转账', 'confirmed': True}).status_code == 200
    assert client.post(review_path, json={'action': 'hide', 'note': '再次处理同一消息', 'confirmed': True}).status_code == 409
    login(client, 'buyer')
    messages = client.get(f'/api/v1/conversations/{conversation_id}/messages').json()['messages']
    reviewed = next(message for message in messages if message['id'] == reply)
    assert reviewed['hidden'] and '转账' not in reviewed['body']
    assert client.delete(f'/api/v1/conversations/{conversation_id}/block').status_code == 200
    assert client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '我会当面核实'}).status_code == 201


def test_deal_confirmation_and_stale_match_notice(client, app):
    login(client, 'buyer')
    task = intent(client).json()['intent']['id']
    notice = client.get('/api/v1/notifications/').json()[0]
    conversation_id, _ = start(client)
    path = f'/api/v1/conversations/{conversation_id}/deal'
    assert client.post(path, json={'action': 'reserve'}).status_code == 403
    assert client.post(path, json={'action': 'request'}).json()['deal_status'] == 'REQUESTED'
    login(client, 'seller')
    assert client.post(path, json={'action': 'reserve'}).json()['item_status'] == 'RESERVED'
    login(client, 'buyer')
    assert not client.get('/api/v1/notifications/').json()[0]['available']
    assert client.post(path, json={'action': 'cancel'}).json()['item_status'] == 'ACTIVE'
    assert client.get('/api/v1/notifications/').json()[0]['available']
    assert client.post(path, json={'action': 'request'}).status_code == 200
    login(client, 'seller')
    assert client.post(path, json={'action': 'reserve'}).status_code == 200
    assert client.post(path, json={'action': 'sold'}).json()['item_status'] == 'SOLD'
    login(client, 'buyer')
    assert client.post(path, json={'action': 'confirm'}).json()['deal_status'] == 'CONFIRMED'
    assert not client.get('/api/v1/notifications/').json()[0]['available']
    assert client.post(path, json={'action': 'request'}).status_code == 409
    completed = client.post(f'/api/v1/intents/{task}/complete', json={'item_id': notice['item']['id']})
    assert completed.status_code == 200 and completed.json()['completed_item_id'] == notice['item']['id']
    assert client.post(f'/api/v1/intents/{task}/complete', json={}).status_code == 409
    with app.state.session_factory() as db:
        assert db.get(Item, 'sample-1').status == 'SOLD'
        assert db.get(Conversation, conversation_id).deal_status == 'CONFIRMED'
        # Later chat activity must not affect the confirmed transaction duration.
        from datetime import timedelta
        from sqlalchemy import select
        from app.models import ActionLog

        item = db.get(Item, 'sample-1')
        confirmation = db.scalar(select(ActionLog).where(
            ActionLog.action == 'deal.confirm', ActionLog.target_id == conversation_id))
        item.created_at = confirmation.created_at - timedelta(days=3)
        db.get(Conversation, conversation_id).last_message_at = confirmation.created_at + timedelta(days=6)
        db.commit()
    login(client, 'admin')
    stats = client.get('/api/v1/admin/analytics/business-overview')
    assert stats.status_code == 200
    assert stats.json()['liquidity']['avg_days_to_sell'] == 3.0


def test_buyer_sale_feedback_needs_seller_confirmation(client):
    login(client, 'buyer')
    assert client.post('/api/v1/items/sample-1/sale-feedback').status_code == 201
    assert client.post('/api/v1/items/sample-1/sale-feedback').status_code == 409
    assert client.get('/api/v1/items/sample-1').json()['status'] == 'ACTIVE'
    login(client, 'seller')
    item = client.get('/api/v1/items/sample-1').json()
    assert item['sale_feedback_count'] == 1
    feedback = client.get('/api/v1/items/sample-1/sale-feedback').json()[0]
    result = client.post(f"/api/v1/items/sample-1/sale-feedback/{feedback['id']}/review", json={'action': 'sold'})
    assert result.status_code == 200 and result.json()['status'] == 'SOLD'
    assert client.get('/api/v1/items/sample-1/sale-feedback').json() == []


def test_manual_seller_status_cannot_silently_accept_a_pending_buyer(client):
    conversation_id, _ = start(client)
    path = f'/api/v1/conversations/{conversation_id}/deal'
    assert client.post(path, json={'action': 'request'}).status_code == 200
    login(client, 'seller')
    assert client.patch('/api/v1/items/sample-1/status', json={'status': 'RESERVED'}).status_code == 409
    assert client.patch('/api/v1/items/sample-1/status', json={'status': 'SOLD'}).status_code == 200
    assert client.get('/api/v1/conversations').json()[0]['deal_status'] == 'DECLINED'


def test_chat_retention_preserves_open_reports(client, app):
    conversation_id, first_message = start(client)
    login(client, 'seller')
    reply = client.post(f'/api/v1/conversations/{conversation_id}/messages', json={'body': '不合适的消息'}).json()['id']
    login(client, 'buyer')
    report = client.post(f'/api/v1/conversations/{conversation_id}/messages/{reply}/reports',
                         json={'reason': '这条消息需要管理员核实'})
    assert report.status_code == 201
    with app.state.session_factory() as db:
        db.get(ChatMessage, first_message).created_at = now() - timedelta(days=200)
        db.get(ChatMessage, reply).created_at = now() - timedelta(days=200)
        db.commit()
    prune_chat(app.state.session_factory, app.state.mutation_lock, 180)
    with app.state.session_factory() as db:
        assert db.get(ChatMessage, first_message) is None
        assert db.get(ChatMessage, reply) is not None
        db.get(ChatReport, report.json()['id']).status = 'DISMISSED'
        db.get(ChatReport, report.json()['id']).reviewed_at = now() - timedelta(days=400)
        db.commit()
    prune_chat(app.state.session_factory, app.state.mutation_lock, 180)
    with app.state.session_factory() as db:
        assert db.get(ChatMessage, reply) is None
        assert db.get(ChatReport, report.json()['id']) is None


def test_existing_database_receives_additive_chat_and_deal_columns(tmp_path):
    url = f'sqlite:///{tmp_path / "old-chat.db"}'
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE conversations DROP COLUMN deal_status'))
        connection.execute(text('ALTER TABLE chat_messages DROP COLUMN hidden_at'))
    engine.dispose()
    settings = Settings(database_url=url, data_dir=tmp_path, demo_mode=True, ai_mode='local')
    with TestClient(create_app(settings)) as client:
        login(client, 'buyer')
        conversation_id, _ = start(client)
        assert client.get('/api/v1/conversations').json()[0]['deal_status'] == 'NONE'
        assert client.post(f'/api/v1/conversations/{conversation_id}/deal', json={'action': 'request'}).status_code == 200


def test_verified_user_can_be_granted_and_revoked_admin_role(client, app):
    with app.state.session_factory() as db:
        db.get(User, 'demo-buyer').email = 'moderator@pku.edu.cn'
        db.commit()
    url = str(app.state.engine.url)
    assert set_admin_role(url, 'moderator@pku.edu.cn', 'admin')
    assert not set_admin_role(url, 'moderator@pku.edu.cn', 'admin')
    login(client, 'buyer')
    assert client.get('/api/v1/admin/chat-reports').status_code == 200
    assert set_admin_role(url, 'moderator@pku.edu.cn', 'student')
    assert client.get('/api/v1/admin/chat-reports').status_code == 401
    login(client, 'buyer')
    assert client.get('/api/v1/admin/chat-reports').status_code == 403
    try:
        set_admin_role(url, 'missing@pku.edu.cn', 'admin')
    except ValueError:
        pass
    else:
        raise AssertionError('未验证邮箱不能被授予管理员权限')
