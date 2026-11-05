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
        db.add(User(id='u1', nickname='同学', campus='燕园校本部', email='user@stu.pku.edu.cn'))
        db.commit()

    assert set_admin_role(url, 'user@stu.pku.edu.cn', 'admin') is True
    assert set_admin_role(url, 'user@stu.pku.edu.cn', 'admin') is False
    assert set_admin_role(url, 'user@stu.pku.edu.cn', 'student') is True

    with pytest.raises(ValueError):
        set_admin_role(url, 'user@stu.pku.edu.cn', 'bogus')
    with pytest.raises(ValueError):
        set_admin_role(url, 'someone@example.com', 'admin')
    with pytest.raises(ValueError):
        set_admin_role(url, 'ghost@stu.pku.edu.cn', 'admin')
    engine.dispose()
