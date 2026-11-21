from decimal import Decimal

import pytest

from app.schemas import ParsedIntent
from app.search import price_cap_cents
from app.search_intent import ground_intent
from conftest import login, publish


@pytest.mark.parametrize('query,expected,around', [
    ('两百多买鼠标', 300, False),
    ('想找一副两百来块的耳机', 200, True),
    ('两千出头的电脑', 2000, True),
    ('约180元的键盘', 180, True),
    ('万柳附近的键盘，200元以内', 200, False),
    ('大约200，最多210元', 210, False),
    ('买键盘，预算不要超过200', 200, False),
    ('预算1.5k改成1,200元', 1200, False),
    ('200多页的教材', None, False),
    ('预算200到300元的键盘', 300, False),
    ('买G20扫地机器人，要求95新', None, False),
    ('99.95元以内买鼠标', Decimal('99.95'), False),
])
def test_budget_uses_expressed_amount(query, expected, around):
    effective, fuzzy = ground_intent(query, ParsedIntent(max_price=299))
    assert effective.max_price == expected
    assert fuzzy is around


def test_exact_cent_at_approximate_ceiling():
    assert price_cap_cents(20000, around=True) == 23000
    assert price_cap_cents(100, around=True) == 115
    assert price_cap_cents(9999, around=True) == 11498


@pytest.mark.parametrize('text,minimum,maximum', [
    ('要一个200多元的键盘', 200, 300),
    ('预算200到300元买键盘', 200, 300),
    ('买键盘，200–300元', 200, 300),
    ('200到300的键盘', 200, 300),
    ('两百多买键盘，最多260', 200, 260),
    ('预算两百多改成150元', None, 150),
    ('要一本两百多页的教材', None, None),
])
def test_budget_range(text, minimum, maximum):
    actual, around = ground_intent(text, ParsedIntent())
    assert (actual.min_price, actual.max_price, around) == (minimum, maximum, False)


def test_invented_filters_and_preference_are_grounded():
    proposed = ParsedIntent(keywords=['键盘接收器', '无线接收器', '红色'], max_price=60,
                            campus='医学部', condition_grade='全新', excluded_keywords=['二手'])
    actual, _ = ground_intent('买个键盘接收器，红色优先', proposed)
    assert actual.keywords == ['键盘接收器']
    assert actual.preferences == ['红色']
    assert actual.excluded_keywords == []
    assert (actual.max_price, actual.campus, actual.condition_grade) == (None, '不限校区', None)


def test_soft_modifier_keeps_subject_and_explicit_requirement():
    proposed = ParsedIntent(keywords=['静音', '无线', '鼠标'])
    actual, _ = ground_intent('最好静音的无线鼠标', proposed)
    assert set(actual.keywords) == {'无线', '鼠标'}
    assert actual.preferences == ['静音']
    actual, _ = ground_intent('必须静音的无线鼠标，最好黑色', proposed)
    assert set(actual.keywords) == {'静音', '无线', '鼠标'}
    assert actual.preferences == ['黑色']


def test_postpositive_preference_and_unknown_product():
    result, _ = ground_intent('找降噪优先的耳机', ParsedIntent(keywords=['降噪耳机']))
    assert result.keywords == ['耳机']
    assert result.preferences == ['降噪']
    result, _ = ground_intent('买个保温杯', ParsedIntent(keywords=[]))
    assert result.keywords == ['保温杯']


def test_browsing_filters_do_not_become_product_names():
    suggested = ParsedIntent(keywords=['附近'], category='数码与影音')
    actual, around = ground_intent('万柳附近，只看数码类，预算200以内', suggested)
    assert actual.keywords == [] and actual.category == '数码与影音'
    assert actual.max_price == 200 and actual.campus == '万柳学区' and not around


def test_conflicting_request_returns_clarification_through_local_api(client):
    response = client.post('/api/v1/items/smart-search', json={'query': '静音鼠标，不要静音'})
    assert response.status_code == 200
    parsed = response.json()['parsed']
    assert parsed['clarification'] and parsed['keywords'] == ['鼠标']
    assert parsed['excluded_keywords'] == []


def test_search_api_keeps_budget_and_other_filters_on_category_retry(client, monkeypatch):
    login(client, 'seller')
    def add(price, campus, tag):
        response = publish(client, title='无线键盘' + tag, price=price, campus=campus,
                           description='无线键盘，功能正常。', tags=[])
        assert response.status_code == 201
        return response.json()['id']

    below = add(199.99, '万柳学区', '黑色')
    bottom = add(200, '万柳学区', '黑色')
    within = add(259, '万柳学区', '黑色')
    top = add(300, '万柳学区', '白色')
    over = add(300.01, '万柳学区', '白色')
    elsewhere = add(219, '医学部', '蓝色')
    from app.search_intent import ModelSearchIntent
    def proposed(query, _):
        preferred = [{'role':'preferred', 'term':'白色', 'quote':'最好白色'}] if '最好白色' in query else []
        return ModelSearchIntent(category='宿舍生活与家电', budget_quote='两百多',
            campus_quote='万柳' if '万柳' in query else None,
            conditions=[{'role':'required', 'term':'无线键盘', 'quote':'无线键盘'}, *preferred]).verified(query)
    monkeypatch.setattr('app.main.parse_search_intent', proposed)
    def search(query):
        response = client.post('/api/v1/items/smart-search', json={'query': query, 'size': 50})
        assert response.status_code == 200
        return response.json()

    result = search('万柳，两百多买无线键盘，最好白色')
    ids = {i['id'] for i in result['items']}
    assert {bottom, within, top} <= ids and not {below, over, elsewhere} & ids
    assert result['parsed']['category'] is None
    assert (result['parsed']['min_price'], result['parsed']['max_price']) == (200, 300)
    assert result['parsed']['preferences'] == ['白色']
    assert search('只看宿舍生活与家电，两百多买无线键盘')['total'] == 0
