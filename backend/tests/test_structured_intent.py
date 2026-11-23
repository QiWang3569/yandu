import json

from fastapi.testclient import TestClient

from app import services
from app.config import Settings
from app.main import create_app
from app.schemas import ParsedIntent
from conftest import login


def remote_settings():
    return Settings(ai_mode='remote', embedding_mode='local', deepseek_key='test-credential')


def structured(**changes):
    payload = {'category': '数码与影音', 'max_price': 300, 'budget_quote': '300', 'campus': '万柳学区',
               'campus_quote': '万柳', 'condition_grade': None, 'condition_quote': '',
               'conditions': [{'role': 'required', 'term': '鼠标', 'quote': '鼠标'},
                              {'role': 'required', 'term': '无线', 'quote': '无线'},
                              {'role': 'excluded', 'term': '游戏鼠标', 'quote': '游戏鼠标'},
                              {'role': 'preferred', 'term': '静音', 'quote': '静音'}],
               'clarification': None}
    payload.update(changes)
    return payload


def use_reply(monkeypatch, reply):
    monkeypatch.setattr(services, 'chat_json', lambda *args, **kwargs: reply)


def test_structured_roles_flatten_to_public_intent(monkeypatch):
    use_reply(monkeypatch, structured())
    parsed, quotes = services.parse_intent_with_quotes(
        '蹲一个万柳附近 300 元以内的静音无线鼠标，不要游戏鼠标', remote_settings())
    assert parsed == ParsedIntent(category='数码与影音', max_price=300, campus='万柳学区',
                                  keywords=['鼠标', '无线'], excluded_keywords=['游戏鼠标'],
                                  preferences=['静音'])
    assert quotes == ['300', '万柳', '鼠标', '无线', '游戏鼠标', '静音']


def test_non_verbatim_quotes_are_dropped(monkeypatch):
    use_reply(monkeypatch, structured(budget_quote='三百元',
                                      conditions=[{'role': 'required', 'term': '鼠标', 'quote': '无线鼠标'}]))
    parsed, quotes = services.parse_intent_with_quotes('万柳 300 元以内无线鼠标', remote_settings())
    assert parsed.max_price == 300
    assert quotes == ['万柳', '无线鼠标']


def test_condition_phrases_are_normalized(monkeypatch):
    use_reply(monkeypatch, structured(condition_grade='九成新以上', condition_quote='九成新',
                                      conditions=[]))
    parsed, quotes = services.parse_intent_with_quotes('收一本教材，九成新以上', remote_settings())
    assert parsed.condition_grade == '9成新'
    assert quotes == ['九成新']

    reply = structured(condition_grade='全新或九五新都行', condition_quote='九五新', conditions=[])
    use_reply(monkeypatch, reply)
    parsed, _ = services.parse_intent_with_quotes('收台灯，全新或九五新都行', remote_settings())
    assert parsed.condition_grade == '95新'


def test_invalid_enums_and_negative_price_are_sanitized(monkeypatch):
    use_reply(monkeypatch, structured(category='不存在的分类', campus='火星', max_price=-50,
                                      budget_quote='-50', conditions=[]))
    parsed, _ = services.parse_intent_with_quotes('收显示器，预算 -50 元', remote_settings())
    assert parsed.category is None and parsed.campus == '不限校区' and parsed.max_price is None


def test_duplicate_terms_never_break_public_validation(monkeypatch):
    use_reply(monkeypatch, structured(conditions=[
        {'role': 'required', 'term': '鼠标', 'quote': '鼠标'},
        {'role': 'excluded', 'term': '鼠标', 'quote': '鼠标'},
        {'role': 'preferred', 'term': '鼠标', 'quote': '鼠标'}]))
    parsed, _ = services.parse_intent_with_quotes('鼠标', remote_settings())
    assert parsed.keywords == ['鼠标'] and parsed.excluded_keywords == [] and parsed.preferences == []


def test_clarification_quotes_keep_conflicting_spans_verbatim(monkeypatch):
    use_reply(monkeypatch, structured(max_price=None, budget_quote='', campus='不限校区',
                                      campus_quote='', clarification='您既要全新又要用过，请确认哪一项重要',
                                      clarification_quotes=['全新', '用过', '并未出现的短语'],
                                      conditions=[{'role': 'required', 'term': '耳机', 'quote': '耳机'}]))
    parsed, quotes = services.parse_intent_with_quotes('要全新但用过的耳机', remote_settings())
    assert parsed.clarification
    assert parsed.keywords == ['耳机']
    assert quotes == ['耳机', '全新', '用过']


def test_parse_api_shape_is_unchanged(tmp_path, monkeypatch):
    use_reply(monkeypatch, structured())
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path / "api.db"}', data_dir=tmp_path,
                              ai_mode='remote', embedding_mode='local', deepseek_key='test-credential'))
    with TestClient(app) as client:
        login(client)
        response = client.post('/api/v1/intents/parse',
                               json={'raw_query': '蹲一个万柳附近 300 元以内的静音无线鼠标，不要游戏鼠标'})
        assert response.status_code == 200, response.text
        parsed = response.json()['parsed']
        assert set(parsed) == set(ParsedIntent.model_fields)
        assert parsed['keywords'] == ['鼠标', '无线'] and parsed['preferences'] == ['静音']


def test_invalid_provider_shape_is_sanitized_502(tmp_path, monkeypatch):
    use_reply(monkeypatch, {'conditions': 'not-a-list'})
    app = create_app(Settings(database_url=f'sqlite:///{tmp_path / "bad.db"}', data_dir=tmp_path,
                              ai_mode='remote', embedding_mode='local', deepseek_key='test-credential'))
    with TestClient(app) as client:
        login(client)
        response = client.post('/api/v1/intents/parse', json={'raw_query': '想要鼠标'})
        assert response.status_code == 502
        assert 'test-credential' not in response.text


def test_local_mode_returns_no_quotes():
    parsed, quotes = services.parse_intent_with_quotes('万柳 300 以内无线鼠标',
                                                       Settings(ai_mode='local', embedding_mode='local'))
    assert quotes == [] and parsed.keywords == ['鼠标', '无线']
