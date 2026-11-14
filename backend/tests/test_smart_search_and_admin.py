"""Regression tests for natural-language smart search and admin-only endpoints."""

from fastapi import HTTPException

from conftest import login


def test_smart_search_parses_budget_category_and_returns_matching_item(client):
    res = client.post('/api/v1/items/smart-search', json={'query': '300以内静音鼠标'})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body['parsed']['category'] == '数码与影音'
    assert body['parsed']['max_price'] == 300
    assert body['parsed']['around_price'] is False
    assert body['total'] >= 1
    assert any('罗技' in item['title'] for item in body['items'])


def test_smart_search_detects_around_price(client):
    res = client.post('/api/v1/items/smart-search', json={'query': '200左右平板'})
    assert res.status_code == 200, res.text
    assert res.json()['parsed']['around_price'] is True


def test_smart_search_validates_input_and_supports_all_sorts(client):
    assert client.post('/api/v1/items/smart-search', json={'query': 'x'}).status_code == 422
    assert client.post(
        '/api/v1/items/smart-search', json={'query': '静音鼠标', 'sort': 'bogus'}
    ).status_code == 422
    for sort in ('recommended', 'newest', 'price_asc', 'price_desc'):
        res = client.post(
            '/api/v1/items/smart-search', json={'query': '鼠标', 'sort': sort, 'size': 50}
        )
        assert res.status_code == 200, res.text


def test_smart_search_falls_back_to_local_parser_when_remote_unavailable(client, monkeypatch):
    from app import main

    def parser_down(*args, **kwargs):
        raise HTTPException(502, '需求解析服务暂时不可用')

    monkeypatch.setattr(main, 'parse_intent', parser_down)
    res = client.post('/api/v1/items/smart-search', json={'query': '300以内静音鼠标'})
    assert res.status_code == 200, res.text
    assert res.json()['parsed']['category'] == '数码与影音'


def test_smart_search_negated_exclusion_is_not_falsely_filtered(client):
    from conftest import publish

    login(client, 'seller')
    gaming = publish(client, title='游戏鼠标', description='电竞游戏鼠标，功能正常，附接收器。', tags=['鼠标']).json()
    office = publish(client, title='非游戏鼠标', description='这是一只非游戏鼠标，适合办公，功能正常。', tags=['鼠标']).json()
    res = client.post('/api/v1/items/smart-search', json={'query': '万柳300以内鼠标，不要游戏鼠标', 'size': 50})
    assert res.status_code == 200, res.text
    ids = {item['id'] for item in res.json()['items']}
    assert gaming['id'] not in ids
    assert office['id'] in ids


def test_unified_parse_natural_language_dispatcher():
    from app.config import Settings
    from app.services import parse_natural_language

    settings = Settings(ai_mode='local')
    intent_res = parse_natural_language('万柳300以内静音鼠标', settings, kind='intent')
    wanted_res = parse_natural_language('万柳300以内静音鼠标', settings, kind='wanted')
    item_res = parse_natural_language('出九成新无线鼠标 120元 万柳自取', settings, kind='item')
    assert intent_res.category == '数码与影音' and intent_res.max_price == 300
    assert wanted_res.category == '数码与影音' and wanted_res.budget == 300
    assert item_res.category == '数码与影音' and float(item_res.price) == 120.0


def test_admin_can_create_update_and_deactivate_announcement(client):
    login(client, 'admin')
    created = client.post(
        '/api/v1/admin/announcements',
        json={'title': '测试公告', 'body': '这是一条测试公告正文', 'kind': '公告'},
    )
    assert created.status_code == 201, created.text
    announcement_id = created.json()['id']

    public = client.get('/api/v1/announcements').json()
    assert any(a['id'] == announcement_id for a in public)

    assert client.patch(
        f'/api/v1/admin/announcements/{announcement_id}', json={'active': False}
    ).status_code == 200
    public = client.get('/api/v1/announcements').json()
    assert not any(a['id'] == announcement_id for a in public)

    assert client.patch(
        '/api/v1/admin/announcements/missing', json={'active': False}
    ).status_code == 404


def test_announcement_management_requires_admin(client):
    login(client, 'buyer')
    assert client.get('/api/v1/admin/announcements').status_code == 403
    assert client.post(
        '/api/v1/admin/announcements', json={'title': '越权公告', 'body': '不应创建成功'}
    ).status_code == 403


def test_admin_can_list_reports_chat_reports_and_logs(client):
    login(client, 'admin')
    assert client.get('/api/v1/admin/reports').status_code == 200
    assert client.get('/api/v1/admin/chat-reports').status_code == 200
    assert client.get('/api/v1/admin/logs').status_code == 200


def test_wanted_watch_renew_and_reopen_lifecycle(client):
    login(client, 'buyer')
    created = client.post(
        '/api/v1/wanted/',
        json={'title': '求购一本教材', 'description': '课程需要，版本不限', 'category': '课程资料与书籍', 'campus': '燕园校本部'},
    )
    assert created.status_code == 201, created.text
    wanted_id = created.json()['id']

    assert client.post(f'/api/v1/wanted/{wanted_id}/watch').status_code == 200
    assert client.post(f'/api/v1/wanted/{wanted_id}/renew').status_code == 409

    assert client.delete(f'/api/v1/wanted/{wanted_id}').status_code == 200
    reopened = client.post(f'/api/v1/wanted/{wanted_id}/renew')
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()['status'] == 'ACTIVE'
