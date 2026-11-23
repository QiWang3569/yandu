import json
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app import buyer_agent
from app.buyer_agent import ModelUnavailable, review_candidates
from app.config import Settings
from app.main import create_app
from app.models import Base, Intent, Item, MatchJob, Notification, now
from app.schemas import ParsedIntent
from app.services import parse_local, seed
from conftest import intent, login, publish


def remote_settings(tmp_path, **kwargs):
    return Settings(database_url=f'sqlite:///{tmp_path / "remote.db"}', data_dir=tmp_path,
                    ai_mode='remote', embedding_mode='local', deepseek_key='test-credential', **kwargs)


def fake_provider(monkeypatch, handler):
    real_client = httpx.Client
    monkeypatch.setattr(buyer_agent.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))


def json_reply(content, finish_reason='stop'):
    return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps(content, ensure_ascii=False)}, 'finish_reason': finish_reason}]})


def await_jobs(app, status='DONE'):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        with app.state.session_factory() as db:
            jobs = db.scalars(select(MatchJob)).all()
            if jobs and all(j.status == status for j in jobs):
                return
        time.sleep(0.01)
    with app.state.session_factory() as db:
        states = [(j.status, j.error_code) for j in db.scalars(select(MatchJob))]
    pytest.fail(f'Unexpected job states: {states}')


def sample_review(payload):
    spec = payload['intent']
    return {'assessments': [{'item_id': item['id'], 'verdict': 'MATCH',
                            'evidence': [{'criterion': k, 'quote': item['description']} for k in spec['keywords']],
                            'questions': ['是否仍有原装接收器？']} for item in payload['items']]}


def test_single_chat_key_and_independent_embedding_configuration(tmp_path):
    assert remote_settings(tmp_path).embedding_mode == 'local'
    assert Settings(ai_mode='remote', deepseek_key='test', embedding_key='test', embedding_mode=None).embedding_mode == 'remote'
    assert Settings(ai_mode='local', embedding_mode='remote', embedding_key='test').ai_mode == 'local'
    with pytest.raises(ValueError):
        Settings(ai_mode='remote', deepseek_key='', embedding_mode='local')
    with pytest.raises(ValueError):
        Settings(embedding_mode='remote', embedding_key='')


def test_local_parser_separates_negation_preferences_and_constraints():
    parsed = parse_local('万柳300元以内无线鼠标，不要游戏鼠标，最好静音')
    assert parsed.max_price == 300
    assert set(parsed.keywords) == {'鼠标', '无线'}
    assert parsed.excluded_keywords == ['游戏鼠标']
    assert parsed.preferences == ['静音']
    with pytest.raises(ValueError):
        ParsedIntent(keywords=['鼠标'], excluded_keywords=['鼠标'])


@pytest.mark.parametrize('query,expected', [('燕园二手网球拍', '网球拍'), ('燕园二手羽毛球拍', '羽毛球拍'), ('tennis racket', '网球拍')])
def test_specific_racket_type_is_preserved(query, expected):
    assert parse_local(query).keywords == [expected]


def test_tennis_wish_does_not_match_badminton_and_revoked_match_is_hidden(client, app):
    login(client)
    task = intent(client, '燕园本部二手网球拍').json()['intent']
    assert task['keywords'] == ['网球拍']
    assert client.get('/api/v1/notifications/').json() == []
    with app.state.session_factory() as db:
        db.add(Notification(buyer_id='demo-buyer', intent_id=task['id'], item_id='sample-10', score=1,
                            reason='旧规则误匹配', verdict='NO_MATCH'))
        db.commit()
    assert client.get('/api/v1/notifications/').json() == []
    assert client.get('/api/v1/intents/my').json()[0]['match_count'] == 0


def test_model_thinking_can_be_configured_without_changing_json_protocol(tmp_path, monkeypatch):
    def handler(request):
        payload = json.loads(request.content)
        assert payload['thinking'] == {'type': 'disabled'}
        assert payload['response_format'] == {'type': 'json_object'}
        return json_reply({'item': '网球拍'})
    fake_provider(monkeypatch, handler)
    assert buyer_agent.chat_json('返回 JSON', '网球拍', remote_settings(tmp_path, model_thinking='disabled')) == {'item': '网球拍'}


def test_notifications_are_scoped_to_owned_wish(client):
    login(client)
    mouse = intent(client).json()['intent']
    tennis = intent(client, '燕园本部二手网球拍').json()['intent']
    assert client.get('/api/v1/notifications/').json()
    assert client.get('/api/v1/notifications/', params={'intent_id': tennis['id']}).json() == []
    scoped = client.get('/api/v1/notifications/', params={'intent_id': mouse['id']}).json()
    assert scoped and all(n['intent_id'] == mouse['id'] for n in scoped)
    login(client, 'seller')
    assert client.get('/api/v1/notifications/', params={'intent_id': mouse['id']}).status_code == 404


def test_preferences_do_not_filter_and_exclusions_are_not_positive_requirements(client):
    login(client)
    task = intent(client, '万柳300以内鼠标，最好静音').json()['intent']
    assert task['preferences'] == ['静音']
    login(client, 'seller')
    plain = publish(client, title='普通办公鼠标', description='普通办公鼠标，功能正常，附接收器。', tags=['鼠标']).json()
    login(client)
    notices = client.get('/api/v1/notifications/').json()
    notice = next(n for n in notices if n['item']['id'] == plain['id'])
    assert notice['verdict'] == 'MATCH'
    assert any('静音' in q for q in notice['questions'])
    assert '静音' in client.post(f"/api/v1/items/{plain['id']}/message-draft").json()['draft']
    excluded_task = intent(client, '万柳300以内鼠标，不要游戏鼠标').json()['intent']['id']
    login(client, 'seller')
    gaming = publish(client, title='游戏鼠标', description='电竞游戏鼠标，功能正常，附接收器。').json()
    office = publish(client, title='非游戏鼠标', description='这是一只非游戏鼠标，适合办公，功能正常。').json()
    login(client)
    ids = {n['item']['id'] for n in client.get('/api/v1/notifications/').json() if n['intent_id'] == excluded_task}
    assert gaming['id'] not in ids
    assert office['id'] in ids


def test_explicit_negative_required_feature_never_creates_local_match(client):
    login(client)
    task = intent(client).json()['intent']['id']
    login(client, 'seller')
    noisy = publish(client, title='非静音无线鼠标', description='这款鼠标不静音，按键声音较大，功能正常。', tags=['鼠标']).json()
    login(client)
    assert noisy['id'] not in {n['item']['id'] for n in client.get('/api/v1/notifications/').json() if n['intent_id'] == task}


def test_remote_parser_and_worker_use_single_chat_key_and_confirmed_fields(tmp_path, monkeypatch):
    calls = []
    def handler(request):
        assert request.url.path == '/chat/completions'
        payload = json.loads(request.content)
        assert payload['response_format'] == {'type': 'json_object'}
        data = json.loads(payload['messages'][1]['content'])
        calls.append(data)
        if 'query' in data:
            return json_reply({'category': '数码与影音', 'max_price': 300, 'budget_quote': '300',
                               'campus': '万柳学区', 'campus_quote': '万柳',
                               'condition_grade': None, 'condition_quote': '',
                               'conditions': [{'role': 'required', 'term': '鼠标', 'quote': '鼠标'},
                                              {'role': 'required', 'term': '无线', 'quote': '无线'},
                                              {'role': 'excluded', 'term': '游戏鼠标', 'quote': '游戏鼠标'},
                                              {'role': 'preferred', 'term': '静音', 'quote': '静音'}],
                               'clarification': None})
        # Confirmed fields, not the original sentence, are the only source of constraints.
        assert data['intent']['excluded_keywords'] == []
        return json_reply(sample_review(data))
    fake_provider(monkeypatch, handler)
    app = create_app(remote_settings(tmp_path))
    with TestClient(app) as client:
        login(client)
        parsed = client.post('/api/v1/intents/parse', json={'raw_query': '万柳300以内无线鼠标，不要游戏鼠标，最好静音'}).json()['parsed']
        parsed['excluded_keywords'] = []
        response = client.post('/api/v1/intents/', json={'raw_query': '原句不要游戏鼠标', 'parsed': parsed})
        assert response.status_code == 201
        await_jobs(app)
        notice = client.get('/api/v1/notifications/').json()[0]
        assert notice['item']['id'] == 'sample-1'
        assert notice['review_mode'] == 'remote' and notice['verdict'] == 'MATCH'
        assert notice['score_kind'] == 'keyword_coverage'
        assert '是否仍有原装接收器' in client.post('/api/v1/items/sample-1/message-draft').json()['draft']
        client.patch(f"/api/v1/intents/{response.json()['intent']['id']}", json={'action': 'renew'})
        await_jobs(app)
        assert len(client.get('/api/v1/notifications/').json()) == 1
        assert len(calls) == 2  # Already notified pairs do not spend additional model tokens.


@pytest.mark.parametrize('bad', [None, [], {}, {'choices': []}, {'choices': [{'message': {'content': ''}}]}])
def test_invalid_provider_responses_are_sanitized_502(tmp_path, monkeypatch, bad):
    fake_provider(monkeypatch, lambda request: httpx.Response(200, json=bad))
    with TestClient(create_app(remote_settings(tmp_path))) as client:
        login(client)
        response = client.post('/api/v1/intents/parse', json={'raw_query': '想要鼠标'})
        assert response.status_code == 502
        assert 'test-credential' not in response.text


@pytest.mark.parametrize('damage', ['unknown_id', 'duplicate', 'missing', 'fabricated_quote', 'preference_rejection', 'truncated'])
def test_semantic_review_rejects_ungrounded_or_incomplete_batches(tmp_path, monkeypatch, damage):
    item = {'id': 'one', 'title': '无线鼠标', 'description': '无线鼠标，功能正常。', 'tags': ['鼠标']}
    spec = {'keywords': ['鼠标'], 'excluded_keywords': [], 'preferences': ['静音']}
    def handler(request):
        data = sample_review({'items': [item], 'intent': spec})
        row = data['assessments'][0]
        if damage == 'unknown_id': row['item_id'] = 'invented'
        if damage == 'duplicate': data['assessments'].append(row)
        if damage == 'missing': data['assessments'] = []
        if damage == 'fabricated_quote': row['evidence'][0]['quote'] = '全新未拆，保修一年'
        if damage == 'preference_rejection':
            row['verdict'] = 'NO_MATCH'
            row['evidence'][0]['criterion'] = '静音'
        return json_reply(data, finish_reason='length' if damage == 'truncated' else 'stop')
    fake_provider(monkeypatch, handler)
    with pytest.raises(ModelUnavailable):
        review_candidates(spec, [item], remote_settings(tmp_path))


def test_missing_hard_evidence_becomes_uncertain(tmp_path, monkeypatch):
    item = {'id': 'one', 'title': '无线鼠标', 'description': '无线鼠标，功能正常。', 'tags': ['鼠标']}
    fake_provider(monkeypatch, lambda request: json_reply({'assessments': [{'item_id': 'one', 'verdict': 'MATCH',
        'evidence': [{'criterion': '鼠标', 'quote': '无线鼠标'}], 'questions': []}]}))
    result = review_candidates({'keywords': ['鼠标', '静音'], 'excluded_keywords': ['游戏鼠标'], 'preferences': []},
                               [item], remote_settings(tmp_path))[0]
    assert result.verdict == 'UNCERTAIN' and '静音' in result.questions[0]


def test_absent_exclusion_does_not_block_match(tmp_path, monkeypatch):
    item = {'id': 'one', 'title': '无线鼠标', 'description': '无线鼠标，功能正常。', 'tags': ['鼠标']}
    fake_provider(monkeypatch, lambda request: json_reply({'assessments': [{'item_id': 'one', 'verdict': 'MATCH',
        'evidence': [{'criterion': '鼠标', 'quote': '无线鼠标'}], 'questions': []}]}))
    result = review_candidates({'keywords': ['鼠标'], 'excluded_keywords': ['游戏鼠标'], 'preferences': []},
                               [item], remote_settings(tmp_path))[0]
    assert result.verdict == 'MATCH'


def test_empty_candidates_skip_provider(tmp_path):
    assert review_candidates({'keywords': ['鼠标']}, [], remote_settings(tmp_path)) == []


def test_assessment_rejects_criterion_outside_intent_whitelist():
    item = {'id': 'one', 'title': '静音无线鼠标', 'description': '无线鼠标，功能正常。', 'tags': ['鼠标']}
    with pytest.raises(ValueError):
        buyer_agent.Assessment.checked(
            {'item_id': 'one', 'verdict': 'MATCH', 'questions': [],
             'evidence': [{'criterion': '静音', 'quote': '静音'}]},
            item, {'keywords': ['鼠标'], 'excluded_keywords': [], 'preferences': []})


def test_uncertain_assessment_requires_a_question():
    item = {'id': 'one', 'title': '无线鼠标', 'description': '无线鼠标，功能正常。', 'tags': ['鼠标']}
    with pytest.raises(ValueError):
        buyer_agent.Assessment.checked(
            {'item_id': 'one', 'verdict': 'UNCERTAIN', 'evidence': [], 'questions': []},
            item, {'keywords': ['鼠标'], 'excluded_keywords': [], 'preferences': []})


def test_exclusion_present_in_text_cannot_be_match(tmp_path, monkeypatch):
    item = {'id': 'one', 'title': '静音游戏鼠标', 'description': '静音游戏鼠标，RGB 灯效。', 'tags': ['鼠标']}
    fake_provider(monkeypatch, lambda request: json_reply({'assessments': [{'item_id': 'one', 'verdict': 'MATCH',
        'evidence': [{'criterion': '鼠标', 'quote': '静音游戏鼠标'}], 'questions': []}]}))
    with pytest.raises(ModelUnavailable):
        review_candidates({'keywords': ['鼠标'], 'excluded_keywords': ['游戏鼠标'], 'preferences': []},
                          [item], remote_settings(tmp_path))


def test_failed_jobs_remain_saved_can_retry_and_are_owner_scoped(tmp_path, monkeypatch):
    failing = True
    def handler(request):
        if failing:
            return httpx.Response(429, json={'error': 'provider failure'})
        return json_reply(sample_review(json.loads(json.loads(request.content)['messages'][1]['content'])))
    fake_provider(monkeypatch, handler)
    app = create_app(remote_settings(tmp_path, match_attempts=1))
    with TestClient(app) as client:
        login(client)
        response = client.post('/api/v1/intents/', json={'raw_query': '万柳鼠标', 'parsed': {'keywords': ['鼠标'], 'category': '数码与影音', 'campus': '万柳学区', 'max_price': 300}})
        assert response.status_code == 201
        task_id = response.json()['intent']['id']
        await_jobs(app, 'FAILED')
        assert client.get('/api/v1/intents/my').json()[0]['matching_state'] == 'FAILED'
        assert client.get('/api/v1/notifications/').json() == []
        login(client, 'seller')
        assert client.post(f'/api/v1/intents/{task_id}/retry').status_code == 404
        login(client)
        failing = False
        assert client.post(f'/api/v1/intents/{task_id}/retry').status_code == 200
        await_jobs(app)
        assert len(client.get('/api/v1/notifications/').json()) == 1


@pytest.mark.parametrize('change', ['sold', 'pause', 'completed'])
def test_provider_work_holds_no_write_lock_and_revalidates_before_notify(tmp_path, monkeypatch, change):
    entered, release = threading.Event(), threading.Event()
    def handler(request):
        entered.set()
        assert release.wait(timeout=4)
        return json_reply(sample_review(json.loads(json.loads(request.content)['messages'][1]['content'])))
    fake_provider(monkeypatch, handler)
    app = create_app(remote_settings(tmp_path))
    with TestClient(app) as client:
        login(client)
        response = client.post('/api/v1/intents/', json={'raw_query': '万柳鼠标', 'parsed': {'keywords': ['鼠标'], 'category': '数码与影音', 'campus': '万柳学区', 'max_price': 300}})
        task_id = response.json()['intent']['id']
        assert entered.wait(timeout=3)
        assert app.state.mutation_lock.acquire(blocking=False)
        app.state.mutation_lock.release()
        try:
            if change == 'sold':
                login(client, 'seller')
                assert client.patch('/api/v1/items/sample-1/status', json={'status': 'SOLD'}).status_code == 200
            elif change == 'pause':
                assert client.patch(f'/api/v1/intents/{task_id}', json={'action': 'pause'}).status_code == 200
            else:
                with app.state.session_factory() as db:
                    db.get(Intent, task_id).status = 'COMPLETED'
                    db.commit()
        finally:
            release.set()
        await_jobs(app)
        login(client)
        assert client.get('/api/v1/notifications/').json() == []


def test_existing_database_is_upgraded_without_losing_notifications(tmp_path):
    url = f'sqlite:///{tmp_path / "old.db"}'
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        old = Intent(id='old-intent', buyer_id='demo-buyer', raw_query='鼠标', keywords=['鼠标'])
        db.add(old)
        db.flush()
        db.add(Notification(id='old-notice', buyer_id='demo-buyer', intent_id=old.id, item_id='sample-1', score=1, reason='原通知'))
        db.commit()
    with engine.begin() as conn:
        for table, columns in [('buyer_intents', ['excluded_keywords', 'preferences']),
                               ('match_notifications', ['verdict', 'questions', 'evidence', 'review_mode'])]:
            for column in columns:
                conn.execute(text(f'ALTER TABLE {table} DROP COLUMN {column}'))
        conn.execute(text('DROP TABLE match_jobs'))
    engine.dispose()
    settings = Settings(database_url=url, data_dir=tmp_path, ai_mode='local', embedding_mode='local')
    for _ in range(2):
        with TestClient(create_app(settings)) as client:
            login(client)
            task = client.get('/api/v1/intents/my').json()[0]
            assert task['id'] == 'old-intent' and task['excluded_keywords'] == []
            notice = client.get('/api/v1/notifications/').json()[0]
            assert notice['reason'] == '原通知' and notice['questions'] == []


def test_unfinished_job_resumes_on_restart(tmp_path):
    settings = Settings(database_url=f'sqlite:///{tmp_path / "restart.db"}', data_dir=tmp_path, ai_mode='local', embedding_mode='local')
    app = create_app(settings)
    with TestClient(app) as client:
        login(client)
        task = intent(client).json()['intent']['id']
        with app.state.session_factory() as db:
            db.query(Notification).delete()
            job = db.scalar(select(MatchJob).where(MatchJob.target_id == task))
            job.status = 'RUNNING'
            db.commit()
    app = create_app(settings)
    with TestClient(app) as client:
        login(client)
        await_jobs(app)
        assert len(client.get('/api/v1/notifications/').json()) == 1


def test_transient_provider_failure_retries_automatically_and_new_item_triggers_job(tmp_path, monkeypatch):
    calls = 0
    def handler(request):
        nonlocal calls
        data = json.loads(json.loads(request.content)['messages'][1]['content'])
        if 'catalog' in data:  # Concept learning is a separate async node.
            return json_reply({'assignments': []})
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return json_reply(sample_review(data))
    fake_provider(monkeypatch, handler)
    app = create_app(remote_settings(tmp_path))
    with TestClient(app) as client:
        login(client)
        response = client.post('/api/v1/intents/', json={'raw_query': '万柳鼠标', 'parsed': {'keywords': ['鼠标'], 'category': '数码与影音', 'campus': '万柳学区', 'max_price': 300}})
        assert response.status_code == 201
        await_jobs(app)
        assert calls == 2
        login(client, 'seller')
        # Hard constraints discard this item without an additional provider request.
        assert publish(client, price=301).status_code == 201
        assert calls == 2
        product = publish(client).json()
        await_jobs(app)
        login(client)
        assert product['id'] in {n['item']['id'] for n in client.get('/api/v1/notifications/').json()}
        assert calls == 3


def test_admin_restore_triggers_matching_for_task_created_while_hidden(client):
    login(client)
    report = client.post('/api/v1/items/sample-1/reports', json={'reason': '请管理员核实商品描述'}).json()['id']
    login(client, 'admin')
    review = {'action': 'hide', 'confirmed': True, 'note': '人工核实期间暂时隐藏'}
    assert client.post(f'/api/v1/admin/reports/{report}/review', json=review).status_code == 200
    login(client)
    task = intent(client).json()['intent']['id']
    assert client.get('/api/v1/notifications/').json() == []
    login(client, 'admin')
    assert client.post(f'/api/v1/admin/reports/{report}/review', json={**review, 'action': 'restore'}).status_code == 200
    login(client)
    assert any(n['intent_id'] == task and n['item']['id'] == 'sample-1' for n in client.get('/api/v1/notifications/').json())


@pytest.mark.parametrize('invalid_vector', [None, [0] * 2, [True] * 1536])
def test_invalid_embeddings_do_not_save_half_finished_intent(tmp_path, monkeypatch, invalid_vector):
    fake_provider(monkeypatch, lambda request: httpx.Response(200, json={'data': [{'embedding': invalid_vector}]}))
    settings = remote_settings(tmp_path)
    settings.embedding_mode, settings.embedding_key = 'remote', 'test-embedding-credential'
    app = create_app(settings)
    with TestClient(app) as client:
        login(client)
        response = client.post('/api/v1/intents/', json={'raw_query': '鼠标', 'parsed': {'keywords': ['鼠标']}})
        assert response.status_code == 502
        assert client.get('/api/v1/intents/my').json() == []
        with app.state.session_factory() as db:
            assert db.scalar(select(MatchJob.id)) is None


def test_observability_callback_is_optional_and_reports_usage(tmp_path, monkeypatch):
    fake_provider(monkeypatch, lambda request: httpx.Response(200, json={
        'choices': [{'message': {'content': json.dumps({'ok': True})}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 12, 'completion_tokens': 3}}))
    settings = remote_settings(tmp_path)
    assert buyer_agent.chat_json('system', {'query': 'x'}, settings) == {'ok': True}
    events = []
    assert buyer_agent.chat_json('system', {'query': 'x'}, settings, observer=events.append) == {'ok': True}
    assert events[0]['node'] == 'chat' and events[0]['usage']['prompt_tokens'] == 12
    assert events[0]['elapsed_ms'] >= 0

    failed = []
    fake_provider(monkeypatch, lambda request: httpx.Response(500, content=b'test-credential'))
    with pytest.raises(ModelUnavailable):
        buyer_agent.chat_json('system', {'query': 'x'}, settings, observer=failed.append)
    assert failed[0]['error'] == 'model_unavailable'
    assert 'test-credential' not in json.dumps(failed)
