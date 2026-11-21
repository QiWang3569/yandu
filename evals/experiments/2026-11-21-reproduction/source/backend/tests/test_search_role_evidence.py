from types import SimpleNamespace

import pytest

from app import services
from app.search_intent import ModelSearchIntent
from conftest import login, publish


def test_remote_roles_round_trip_through_search_and_sort(client, monkeypatch):
    login(client, 'seller')
    def add(color, price):
        row = publish(client, title=color + '鼠标', description='鼠标按键正常，适合办公。', price=price, tags=[])
        assert row.status_code == 201
        return row.json()['id']
    black, white = add('黑色', 80), add('白色', 30)
    monkeypatch.setattr('app.main.parse_search_intent', lambda q, _: services.parse_search_intent(q, SimpleNamespace(ai_mode='remote')))
    query = '想买鼠标，黑色会更合我心意'
    roles = [{'role': 'required', 'term': '鼠标', 'quote': '想买鼠标'},
             {'role': 'preferred', 'term': '黑色', 'quote': '黑色会更合我心意'}]
    def model(system, payload, settings):
        assert '整句话' in system and 'quote' in system
        assert payload == {'query': query}
        return {'conditions': roles}
    monkeypatch.setattr(services, 'chat_json', model)

    def search(sort):
        response = client.post('/api/v1/items/smart-search', json={'query': query, 'sort': sort, 'size': 50})
        assert response.status_code == 200
        return response.json()
    result = search('recommended')
    parsed = result['parsed']
    assert parsed['role_source'] == 'model' and parsed['conditions'] == roles
    assert parsed['keywords'] == ['鼠标'] and parsed['preferences'] == ['黑色']
    ids = [item['id'] for item in result['items']]
    assert ids.index(black) < ids.index(white)
    cheaper = [item['id'] for item in search('price_asc')['items']]
    assert cheaper.index(white) < cheaper.index(black)

    roles[1]['quote'] = '我非黑色不可'
    bad = client.post('/api/v1/items/smart-search', json={'query': query})
    assert bad.status_code == 502 and '引用' in bad.json()['detail']


@pytest.mark.parametrize('wire', [
    {'conditions': [{'role':'preferred', 'term':'黑色'}]},
    {'conditions': [{'role':'preferred', 'term':'黑色', 'quote':'想买鼠标'}]},
    {'conditions': [{'role':r, 'term':'黑色', 'quote':'我喜欢黑色'} for r in ('preferred','required')]},
    {'conditions': [], 'budget_quote':'300以内'},
])
def test_missing_misattributed_or_conflicting_evidence_is_invalid(wire):
    with pytest.raises(ValueError):
        ModelSearchIntent.model_validate(wire).verified('想买鼠标，我喜欢黑色')


def test_soft_structured_attributes_never_become_hard_filters():
    query = '想买鼠标，全新的会更称心，万柳取货会更方便'
    roles = [{'role':'required','term':'鼠标','quote':'想买鼠标'},
             {'role':'preferred','term':'全新','quote':'全新的会更称心'},
             {'role':'preferred','term':'万柳','quote':'万柳取货会更方便'}]
    intent = ModelSearchIntent(conditions=roles).verified(query)
    assert intent.condition_grade is None and intent.campus == '不限校区'
    assert intent.preferences == ['全新','万柳']
