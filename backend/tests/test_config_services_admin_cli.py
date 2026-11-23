"""Unit tests for settings validation, remote parsing/embedding, and the admin CLI."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.admin_cli import set_admin_role
from app.config import Settings
from app.models import Base, User


@pytest.mark.parametrize(
    'kwargs',
    [
        dict(app_env='staging'),
        dict(ai_mode='remote'),
        dict(embedding_mode='remote'),
        dict(model_thinking='bogus'),
        dict(model_timeout=0),
        dict(match_attempts=6),
        dict(threshold=1.5),
        dict(chat_retention_days=29),
        dict(chat_email_delay_seconds=59),
        dict(chat_email_cooldown_seconds=299),
        dict(chat_email_enabled=True),
        dict(public_app_url='https://example.com/path'),
        dict(public_app_url='https://user@example.com'),
    ],
)
def test_settings_reject_invalid_values(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_local_loopback_http_public_url_is_allowed():
    settings = Settings(public_app_url='http://127.0.0.1:8000', app_env='local')
    assert settings.public_app_url == 'http://127.0.0.1:8000'


def test_parse_item_remote_success_and_local_fallback(monkeypatch):
    from app import services
    from app.buyer_agent import ModelUnavailable

    settings = Settings(ai_mode='remote', deepseek_key='test-key', embedding_mode='local')
    monkeypatch.setattr(
        services,
        'chat_json',
        lambda *a, **k: {
            'title': '二手平板',
            'description': '九成新平板，功能正常',
            'category': '数码与影音',
            'price': '100',
            'campus': '燕园校本部',
            'condition_grade': '9成新',
            'tags': ['平板'],
            'clarification': None,
        },
    )
    parsed = services.parse_item('九成新平板', settings)
    assert parsed.category == '数码与影音'
    assert float(parsed.price) == 100.0

    def provider_down(*a, **k):
        raise ModelUnavailable('provider down')

    monkeypatch.setattr(services, 'chat_json', provider_down)
    fallback = services.parse_item('卖 300 元静音鼠标', settings)
    assert float(fallback.price) == 300.0


def test_parse_item_local_extracts_every_field(monkeypatch):
    from app import concepts, services

    monkeypatch.setattr(concepts, 'concepts_in_text', lambda text: [])
    monkeypatch.setattr(concepts, 'legacy_enabled', lambda: True)
    parsed = services.parse_item_local('静音无线鼠标，¥280，万柳学区，九五新')
    assert parsed.title == '静音无线鼠标'
    assert parsed.category == '数码与影音'
    assert float(parsed.price) == 280.0
    assert parsed.campus == '万柳学区'
    assert parsed.condition_grade == '95新'
    assert parsed.tags == ['鼠标', '静音', '无线']


def test_parse_item_invalid_remote_fields_fall_back_to_local(monkeypatch):
    from app import services

    settings = Settings(ai_mode='remote', deepseek_key='test-key', embedding_mode='local')
    monkeypatch.setattr(services, 'chat_json', lambda *a, **k: {
        'title': '不存在的商品', 'category': '不存在的分类', 'price': '-50',
        'campus': '火星', 'condition_grade': '十成新', 'tags': []})
    parsed = services.parse_item('卖 300 元静音鼠标', settings)
    assert float(parsed.price) == 300.0
    assert parsed.campus == '燕园校本部'


def test_parse_item_blank_or_punctuation_input_does_not_crash(monkeypatch):
    from app import concepts, services

    monkeypatch.setattr(concepts, 'concepts_in_text', lambda text: [])
    monkeypatch.setattr(concepts, 'legacy_enabled', lambda: True)
    parsed = services.parse_item('，。！？ ', Settings(ai_mode='local', embedding_mode='local'))
    assert parsed.title is None
    assert parsed.price is None
    assert parsed.tags == []


def test_parse_item_local_reads_chinese_price_condition_and_campus(monkeypatch):
    from app import concepts, services

    monkeypatch.setattr(concepts, 'concepts_in_text', lambda text: [])
    monkeypatch.setattr(concepts, 'legacy_enabled', lambda: True)
    parsed = services.parse_item_local('台灯，售价120元，昌平新校区，八成新')
    assert float(parsed.price) == 120.0
    assert parsed.campus == '昌平新校区'
    assert parsed.condition_grade == '8成新'


def test_parse_item_remote_accepts_numeric_price_and_eight_tags(monkeypatch):
    from app import services

    settings = Settings(ai_mode='remote', deepseek_key='test-key', embedding_mode='local')
    tags = ['教材', '高数', '同济', '第七版', '笔记', '考研', '数学', '二手']
    monkeypatch.setattr(services, 'chat_json', lambda *a, **k: {
        'title': '高数教材', 'description': '同济第七版，少量笔记', 'category': '课程资料与书籍',
        'price': 35, 'campus': '医学部', 'condition_grade': '9成新',
        'tags': tags, 'clarification': None})
    parsed = services.parse_item('高数教材 35 元', settings)
    assert float(parsed.price) == 35.0
    assert parsed.campus == '医学部'
    assert parsed.condition_grade == '9成新'
    assert parsed.tags == tags


def test_parse_item_remote_keeps_a_full_length_description(monkeypatch):
    from app import services

    settings = Settings(ai_mode='remote', deepseek_key='test-key', embedding_mode='local')
    description = '九成新。' * 750
    monkeypatch.setattr(services, 'chat_json', lambda *a, **k: {
        'title': '静音鼠标', 'description': description, 'category': '数码与影音',
        'price': '199.99', 'campus': '万柳学区', 'condition_grade': '9成新',
        'tags': ['鼠标'], 'clarification': None})
    parsed = services.parse_item('静音鼠标，¥199.99', settings)
    assert len(parsed.description) == 3000
    assert float(parsed.price) == 199.99


def test_parse_item_remote_non_object_payload_falls_back(monkeypatch):
    from app import services

    settings = Settings(ai_mode='remote', deepseek_key='test-key', embedding_mode='local')
    monkeypatch.setattr(services, 'chat_json', lambda *a, **k: ['not', 'an', 'object'])
    parsed = services.parse_item('卖 300 元静音鼠标', settings)
    assert float(parsed.price) == 300.0


def test_parse_item_remote_out_of_range_price_falls_back(monkeypatch):
    from app import services

    settings = Settings(ai_mode='remote', deepseek_key='test-key', embedding_mode='local')
    monkeypatch.setattr(services, 'chat_json', lambda *a, **k: {
        'title': '鼠标', 'description': '静音鼠标', 'category': '数码与影音',
        'price': 1000000, 'campus': '燕园校本部', 'condition_grade': '95新',
        'tags': ['鼠标'], 'clarification': None})
    parsed = services.parse_item('卖 250 元静音鼠标', settings)
    assert float(parsed.price) == 250.0


def test_parse_item_remote_unknown_field_falls_back(monkeypatch):
    from app import services

    settings = Settings(ai_mode='remote', deepseek_key='test-key', embedding_mode='local')
    monkeypatch.setattr(services, 'chat_json', lambda *a, **k: {
        'title': '台灯', 'description': '护眼台灯', 'category': '宿舍生活与家电',
        'price': '280', 'campus': '燕园校本部', 'condition_grade': '95新',
        'tags': ['台灯'], 'clarification': None, 'seller_phone': '12345678901'})
    parsed = services.parse_item('卖 280 元台灯', settings)
    assert float(parsed.price) == 280.0


def test_embed_remote_returns_vector_and_sanitizes_bad_payload(monkeypatch):
    from app import services

    settings = Settings(
        ai_mode='remote', deepseek_key='test-key', embedding_mode='remote', embedding_key='test-key'
    )

    class Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class FakeClient:
        def __init__(self, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, *args, **kwargs):
            return Resp({'data': [{'embedding': [1.0] * 1536}]})

    monkeypatch.setattr(services.httpx, 'Client', FakeClient)
    assert services.embed('任意文本', settings) == [1.0] * 1536

    class BadClient(FakeClient):
        def post(self, *args, **kwargs):
            return Resp({'data': [{'embedding': [1.0]}]})

    monkeypatch.setattr(services.httpx, 'Client', BadClient)
    with pytest.raises(HTTPException):
        services.embed('任意文本', settings)


def test_set_admin_role_noop_and_validation(tmp_path):
    url = f'sqlite:///{tmp_path / "cli.db"}'
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id='u1', nickname='同学', campus='燕园校本部', email='user@example.com'))
        db.commit()

    assert set_admin_role(url, 'user@example.com', 'admin') is True
    assert set_admin_role(url, 'user@example.com', 'admin') is False
    assert set_admin_role(url, 'user@example.com', 'student') is True

    with pytest.raises(ValueError):
        set_admin_role(url, 'user@example.com', 'bogus')
    with pytest.raises(ValueError):
        set_admin_role(url, 'someone@example.com', 'admin')
    with pytest.raises(ValueError):
        set_admin_role(url, 'ghost@stu.pku.edu.cn', 'admin')
    engine.dispose()
