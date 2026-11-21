from types import SimpleNamespace

import pytest

from app.smart_terms import Listing, phrase_matches
from app.services import parse_local
from conftest import login, publish


@pytest.mark.parametrize('title,description,query,match', [
    ('键盘膜', '适用于机械键盘', '键盘', False),
    ('无线鼠标不带接收器', '正常使用', '鼠标', True),
    ('鼠标，附接收器', '可连接笔记本电脑', '鼠标', True),
    ('适用于笔记本的支架', '铝合金，兼容电脑', '笔记本电脑', False),
    ('定制腕托', '可搭配键盘使用', '键盘', False),
    ('适用于鼠标的定制腕托', '适合日常办公', '鼠标', False),
    ('键盘接收器', '无线连接', '键盘接收器', True),
    ('无线办公鼠标', '蓝牙款，按键不支持静音', '无线鼠标', True),
    ('无线办公鼠标', '蓝牙款，按键不支持静音', '静音鼠标', False),
    ('普通通勤自行车', '非山地自行车，不带车锁', '山地车', False),
    ('黑色跑步鞋', '仅适合日常慢跑', '鞋子', True),
])
def test_subject_and_evidence(title, description, query, match):
    item = SimpleNamespace(title=title, description=description, tags=[], price_cents=5000, condition_grade='95新')
    assert phrase_matches(Listing.from_item(item), query) == match


def test_preferences_promote_without_filtering_or_overriding_price(client):
    login(client, 'seller')
    def add(title, desc, price):
        response = publish(client, title=title, description=desc, price=price, tags=[])
        assert response.status_code in (200, 201)
        return response.json()['id']
    quiet = add('无线办公鼠标', '静音按键，正常使用。', 98)
    noisy = add('无线游戏鼠标', '不支持静音，正常使用。', 25)
    router = add('无线路由器', '带网线，正常使用。', 10)
    def ids(query, sort='recommended'):
        response = client.post('/api/v1/items/smart-search', json={'query':query,'sort':sort,'size':50})
        assert response.status_code == 200
        return [i['id'] for i in response.json()['items']]
    base = ids('万柳100以内无线鼠标')
    ranked = ids('万柳100以内无线鼠标，最好静音')
    assert set(base) == set(ranked)
    assert router not in ranked and ranked.index(quiet) < ranked.index(noisy)
    prices = ids('万柳100以内无线鼠标，最好静音', 'price_asc')
    assert prices.index(noisy) < prices.index(quiet)
    strict = ids('万柳100以内静音无线鼠标')
    assert quiet in strict and noisy not in strict
    excluded = ids('万柳100以内无线鼠标，不要静音')
    assert quiet not in excluded and noisy in excluded
    assert set(ids('万柳100以内无线鼠标，最好全新')) == set(base)


@pytest.mark.parametrize('query,required,excluded,preferred', [
    ('想买蓝牙降噪耳机，不要白色，最好全新', {'耳机', '蓝牙', '降噪'}, ['白色'], ['全新']),
    ('100以内白色鞋子', {'鞋', '白色'}, [], []),
    ('收非游戏鼠标', {'鼠标'}, ['游戏鼠标'], []),
    ('找一个MacBook充电器', {'macbook充电器'}, [], []),
])
def test_local_required_terms(query, required, excluded, preferred):
    parsed = parse_local(query)
    assert set(parsed.keywords) == required
    assert parsed.excluded_keywords == excluded
    assert parsed.preferences == preferred
    assert parsed.condition_grade is None
