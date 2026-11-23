import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import Settings
from app.models import Item, Upload
from app.vision import VisionDraft, VisionService
from conftest import login, photo

ANSWER = {'status': 'ready', 'title': '黑色鼠标', 'category': '数码与影音',
          'description': '黑色鼠标，顶部可见滚轮。', 'tags': ['鼠标', '黑色'],
          'uncertainties': ['请确认型号、功能及包含的配件。']}


@pytest.fixture
def provider(app, monkeypatch):
    settings = app.state.settings
    settings.vision_enabled = True
    settings.vision_key = 'test-secret-never-return'
    requests = []
    replies = []

    def handle(request):
        requests.append(request)
        if replies:
            status, body = replies.pop(0)
            return httpx.Response(status, json=body)
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {
            'content': json.dumps(ANSWER, ensure_ascii=False)}}]})

    client_class = httpx.AsyncClient
    monkeypatch.setattr('app.vision.httpx.AsyncClient', lambda **kwargs:
                        client_class(**kwargs, transport=httpx.MockTransport(handle)))
    return requests, replies


def test_disabled_and_auth(client):
    assert client.get('/api/v1/meta').json()['vision_enabled'] is False
    assert client.post('/api/v1/items/vision-draft', json={'images': ['/uploads/' + 'a' * 36 + '.jpg']}).status_code == 401
    login(client)
    assert client.post('/api/v1/items/vision-draft', json={'images': [photo(client)]}).status_code == 503


def test_owner_only_no_publish_and_cache(client, app, provider):
    login(client)
    url = photo(client)
    with app.state.session_factory() as db:
        count = db.scalar(select(func.count()).select_from(Item))
    payload = {'images': [url], 'note': '只卖鼠标'}
    first = client.post('/api/v1/items/vision-draft', json=payload)
    assert first.status_code == 200, first.text
    assert first.json() == ANSWER
    assert client.post('/api/v1/items/vision-draft', json=payload).json() == ANSWER
    requests, _ = provider
    assert len(requests) == 1
    sent = json.loads(requests[0].content)
    assert sent['model'] == 'qwen/qwen3.7-flash'
    assert sent['thinking'] == {'type': 'disabled'}
    assert sent['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
    assert not {'price', 'campus', 'condition_grade'} & first.json().keys()
    with app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Item)) == count
    login(client, 'seller')
    assert client.post('/api/v1/items/vision-draft', json=payload).status_code == 404
    assert len(requests) == 1


@pytest.mark.parametrize('images', [[], ['https://example.com/a.jpg'], ['/uploads/../secret.jpg'],
                                   ['/api/v1/chat-images/' + 'a' * 36 + '.jpg'],
                                   ['/api/v1/feedback-images/' + 'a' * 36 + '.jpg'],
                                   ['/uploads/' + 'a' * 36 + '.jpg'] * 2,
                                   ['/uploads/' + str(i) * 36 + '.jpg' for i in range(4)]])
def test_reject_invalid_input(client, provider, images):
    login(client)
    assert client.post('/api/v1/items/vision-draft', json={'images': images}).status_code == 422
    assert not provider[0]


def test_origin_and_missing_file_and_ownership_rechecked_on_cache(client, app, provider):
    login(client)
    url = photo(client)
    payload = {'images': [url]}
    assert client.post('/api/v1/items/vision-draft', json=payload,
                       headers={'origin': 'https://attacker.example'}).status_code == 403
    assert client.post('/api/v1/items/vision-draft', json=payload).status_code == 200
    with app.state.session_factory() as db:
        db.delete(db.get(Upload, url))
        db.commit()
    assert client.post('/api/v1/items/vision-draft', json=payload).status_code == 404
    missing = photo(client)
    (app.state.settings.data_dir / missing.lstrip('/')).unlink()
    assert client.post('/api/v1/items/vision-draft', json={'images': [missing]}).status_code == 404
    assert len(provider[0]) == 1


def test_two_photos_share_one_request(client, provider):
    login(client)
    first, second = photo(client), photo(client)
    response = client.post('/api/v1/items/vision-draft', json={'images': [first, second]})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'ready'
    assert len(provider[0]) == 1
    content = json.loads(provider[0][0].content)['messages'][1]['content']
    assert len([part for part in content if part['type'] == 'image_url']) == 2


def test_ready_without_any_evidence_degrades_to_unclear():
    result = VisionDraft.model_validate({'status': 'ready', 'title': None, 'category': None,
                                         'description': None, 'tags': [], 'uncertainties': []})
    assert result.status == 'unclear'
    assert result.title is None and result.uncertainties


def test_corrupt_photo(client, app, provider):
    login(client)
    url = photo(client)
    (app.state.settings.data_dir / url.lstrip('/')).write_text('not an image')
    assert client.post('/api/v1/items/vision-draft', json={'images': [url]}).status_code == 422
    assert not provider[0]


@pytest.mark.parametrize('content,finish', [('not json', 'stop'), (json.dumps(ANSWER), 'length'),
    (json.dumps({**ANSWER, 'price': 100}), 'stop'), (json.dumps({**ANSWER, 'category': '无效'}), 'stop'),
    (json.dumps({**ANSWER, 'tags': ['x' * 31]}), 'stop'), (json.dumps({**ANSWER, 'title': 123}), 'stop')])
def test_bad_provider_output(client, provider, content, finish):
    login(client)
    provider[1].append((200, {'choices': [{'finish_reason': finish, 'message': {'content': content}}]}))
    response = client.post('/api/v1/items/vision-draft', json={'images': [photo(client)]})
    assert response.status_code == 502
    assert 'test-secret' not in response.text


@pytest.mark.parametrize('status', [429, 503])
def test_transient_retry(client, provider, status):
    login(client)
    provider[1].append((status, {'error': 'provider error'}))
    response = client.post('/api/v1/items/vision-draft', json={'images': [photo(client)]})
    assert response.status_code == 200
    assert len(provider[0]) == 2


def test_error_sanitized_not_cached(client, provider):
    login(client)
    url = photo(client)
    provider[1].append((401, {'error': 'test-secret-never-return'}))
    response = client.post('/api/v1/items/vision-draft', json={'images': [url]})
    assert response.status_code == 502 and 'test-secret' not in response.text
    assert client.post('/api/v1/items/vision-draft', json={'images': [url]}).status_code == 200
    assert len(provider[0]) == 2


@pytest.mark.parametrize('body', [{'choices': [None]}, {'choices': []}, {'choices': ['unexpected']}, []])
def test_invalid_provider_envelope(client, provider, body):
    login(client)
    provider[1].append((200, body))
    assert client.post('/api/v1/items/vision-draft', json={'images': [photo(client)]}).status_code == 502


@pytest.mark.parametrize('status', ['unclear', 'multiple_items'])
def test_unclear_results_cannot_fill(status):
    result = VisionDraft.model_validate({**ANSWER, 'status': status, 'uncertainties': []})
    assert result.title is result.description is result.category is None
    assert not result.tags and result.uncertainties


def test_rate_limit_cache_and_changed_note(client, app, provider):
    app.state.settings.vision_hourly_limit = 1
    login(client)
    payload = {'images': [photo(client)]}
    assert client.post('/api/v1/items/vision-draft', json=payload).status_code == 200
    assert client.post('/api/v1/items/vision-draft', json=payload).status_code == 200
    assert client.post('/api/v1/items/vision-draft', json={**payload, 'note': '只卖鼠标'}).status_code == 429
    assert len(provider[0]) == 1


def test_inflight_deduplication_and_concurrency(monkeypatch):
    async def run():
        service = VisionService(Settings())
        gate = asyncio.Event()
        calls = []

        async def recognize(images, note):
            calls.append(note)
            await gate.wait()
            return VisionDraft.model_validate(ANSWER)

        monkeypatch.setattr(service, '_request', recognize)
        first = asyncio.create_task(service.generate('user', [b'photo'], 'same'))
        duplicate = asyncio.create_task(service.generate('user', [b'photo'], 'same'))
        await asyncio.sleep(.01)
        with pytest.raises(HTTPException) as exc:
            await service.generate('user', [b'other photo'], 'different')
        assert exc.value.status_code == 429
        others = [asyncio.create_task(service.generate(str(i), [b'photo'], 'same')) for i in range(3)]
        await asyncio.sleep(.01)
        with pytest.raises(HTTPException) as exc:
            await service.generate('fifth', [b'photo'], 'same')
        assert exc.value.status_code == 429
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        gate.set()
        assert (await duplicate).title == ANSWER['title']
        await asyncio.gather(*others)
        assert len(calls) == 4 and not service.pending
        await service.close()
    asyncio.run(run())


def test_timeout_frees_slot_and_retry_possible(monkeypatch):
    async def run():
        settings = Settings()
        settings.vision_timeout = .02
        service = VisionService(settings)

        async def slow(images, note):
            await asyncio.sleep(1)
        monkeypatch.setattr(service, '_request', slow)
        with pytest.raises(HTTPException) as exc:
            await service.generate('user', [b'photo'], '')
        assert exc.value.status_code == 504 and not service.pending and not service.cache
        async def fast(images, note):
            return VisionDraft.model_validate(ANSWER)
        monkeypatch.setattr(service, '_request', fast)
        assert (await service.generate('user', [b'photo'], '')).status == 'ready'
    asyncio.run(run())


@pytest.mark.parametrize('kwargs', [{'vision_enabled': True}, {'vision_url': 'http://api.example.com'},
    {'vision_url': 'https://secret@api.example.com'}, {'vision_thinking': 'invalid'},
    {'vision_timeout': 0}, {'vision_timeout': 61}, {'vision_hourly_limit': 0}, {'vision_model': ''},
    {'vision_url': 'https://example.com:bad'}, {'vision_url': 'https://example.com:0'},
    {'vision_enabled': True, 'vision_key': '   '}])
def test_vision_config_validation(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_vision_does_not_reuse_text_key(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'text-only')
    with pytest.raises(ValueError, match='VISION_API_KEY'):
        Settings(vision_enabled=True)
