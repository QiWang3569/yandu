from conftest import login


def test_profile_is_private_editable_and_persistent(client, app):
    assert client.get('/api/v1/users/me/overview').status_code == 401
    assert client.patch('/api/v1/users/me', json={}).status_code == 401

    original = login(client)
    counts = client.get('/api/v1/users/me/overview')
    assert counts.status_code == 200
    assert set(counts.json()) == {'intents', 'listings', 'favorites', 'wanted'}
    assert all(isinstance(value, int) for value in counts.json().values())

    changed = client.patch('/api/v1/users/me', json={
        'nickname': '爱读旧书',
        'bio': '在燕园寻找旧书和有趣的小物。', 'avatar_color': 'peach',
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()['user']['email'] == original['email']
    assert changed.json()['user']['bio'] == '在燕园寻找旧书和有趣的小物。'
    assert client.get('/api/v1/auth/me').json()['user']['avatar_color'] == 'peach'
    with app.state.session_factory() as db:
        from app.models import User
        assert db.get(User, original['id']).nickname == '爱读旧书'

    for payload in (
        {'nickname': 'A'},
        {'nickname': '新同学', 'avatar_color': 'javascript:red'},
    ):
        assert client.patch('/api/v1/users/me', json=payload).status_code == 422
    assert client.get('/api/v1/auth/me').json()['user']['nickname'] == '爱读旧书'
