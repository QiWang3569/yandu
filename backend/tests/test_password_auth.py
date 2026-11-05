from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import User
from app.password_auth import hash_password, verify_password
from test_auth_chat import email_client


PASSWORD = '  CampusLife9  '


def register(client, sent, email='reader@stu.pku.edu.cn'):
    assert client.post('/api/v1/auth/email/request-code', json={'email': email}).status_code == 200
    result = client.post('/api/v1/auth/email/verify', json={
        'email': email, 'code': sent[-1][1], 'nickname': '读书同学', 'campus': '燕园校本部',
        'intent': 'register', 'password': PASSWORD,
    })
    assert result.status_code == 200, result.text
    return result.json()['user']


def test_registration_sets_nine_character_password_and_keeps_code_login(tmp_path, monkeypatch):
    app, sent = email_client(tmp_path, monkeypatch)
    email = 'new@pku.edu.cn'
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/email/request-code', json={'email': email}).status_code == 200
        base = {'email': email, 'code': sent[-1][1], 'nickname': '新同学', 'intent': 'register'}
        assert client.post('/api/v1/auth/email/verify', json={**base, 'intent': 'login'}).status_code == 404
        assert client.post('/api/v1/auth/email/verify', json=base).status_code == 422
        for invalid in ('Abcdefg1', 'Abcdefghi', '123456789'):
            response = client.post('/api/v1/auth/email/verify', json={**base, 'password': invalid})
            assert response.status_code == 422 and invalid not in response.text
        password = 'Abcdefgh1'
        created = client.post('/api/v1/auth/email/verify', json={**base, 'password': password})
        assert created.status_code == 200 and created.json()['user']['has_password'] is True
        assert password not in created.text
        client.post('/api/v1/auth/logout')
        assert client.post('/api/v1/auth/password/login', json={'email': email, 'password': password}).status_code == 200
        client.post('/api/v1/auth/logout')
        assert client.post('/api/v1/auth/email/request-code', json={'email': email}).status_code == 200
        challenge = {'email': email, 'code': sent[-1][1]}
        assert client.post('/api/v1/auth/email/verify', json={**challenge, 'intent': 'register',
                           'nickname': '另一个人', 'password': password}).status_code == 409
        assert client.post('/api/v1/auth/email/verify', json={**challenge, 'intent': 'login'}).status_code == 200


def test_password_requires_verified_account_and_code(tmp_path, monkeypatch):
    app, sent = email_client(tmp_path, monkeypatch)
    with TestClient(app) as client:
        assert client.post('/api/v1/auth/password/login', json={
            'email': 'reader@gmail.com', 'password': PASSWORD,
        }).status_code == 422
        assert client.post('/api/v1/auth/password/login', json={
            'email': 'reader@stu.pku.edu.cn', 'password': PASSWORD,
        }).status_code == 401

        email = 'reader@stu.pku.edu.cn'
        assert client.post('/api/v1/auth/email/request-code', json={'email': email}).status_code == 200
        unknown = client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': sent[-1][1], 'password': PASSWORD,
        })
        assert unknown.status_code == 409
        assert client.post('/api/v1/auth/email/verify', json={
            'email': email, 'code': sent[-1][1], 'nickname': '读书同学',
            'intent': 'register', 'password': PASSWORD,
        }).status_code == 200
        assert client.post('/api/v1/auth/logout').status_code == 200

        assert client.post('/api/v1/auth/email/request-code', json={'email': email}).status_code == 200
        bad = client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': '00000000', 'password': PASSWORD,
        })
        assert bad.status_code == 400
        short = client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': sent[-1][1], 'password': 'short',
        })
        assert short.status_code == 422 and 'short' not in short.text
        assert client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': sent[-1][1], 'password': 'abcdefghi',
        }).status_code == 422
        assert client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': sent[-1][1], 'password': '123456789',
        }).status_code == 422
        set_result = client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': sent[-1][1], 'password': PASSWORD,
        })
        assert set_result.status_code == 200, set_result.text
        assert set_result.json()['user']['has_password'] is True
        assert 'password_hash' not in set_result.text and PASSWORD not in set_result.text
        assert client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': sent[-1][1], 'password': PASSWORD,
        }).status_code == 400
        with app.state.session_factory() as db:
            user = db.get(User, set_result.json()['user']['id'])
            assert user.password_hash != PASSWORD and verify_password(PASSWORD, user.password_hash)


def test_password_login_reset_and_session_revocation(tmp_path, monkeypatch):
    app, sent = email_client(tmp_path, monkeypatch)
    email = 'reader@pku.edu.cn'
    with TestClient(app) as client:
        account = register(client, sent, email)
        assert account['has_password'] is True
        assert client.post('/api/v1/auth/logout').status_code == 200

        for wrong in ('CampusLife9', 'incorrect password over 15 characters'):
            result = client.post('/api/v1/auth/password/login', json={'email': email, 'password': wrong})
            assert result.status_code == 401 and result.json()['detail'] == '邮箱或密码错误'
        signed_in = client.post('/api/v1/auth/password/login', json={'email': email, 'password': PASSWORD})
        assert signed_in.status_code == 200 and signed_in.json()['user']['id'] == account['id']
        old_token = client.cookies.get('yandu_session')

        assert client.post('/api/v1/auth/email/request-code', json={'email': email}).status_code == 200
        replacement = 'NewCampus9'
        reset = client.post('/api/v1/auth/password/set', json={
            'email': email, 'code': sent[-1][1], 'password': replacement,
        })
        assert reset.status_code == 200
        assert client.cookies.get('yandu_session') != old_token
        old_device = TestClient(app)
        old_device.cookies.set('yandu_session', old_token)
        assert old_device.get('/api/v1/auth/me').json()['user'] is None
        assert old_device.post('/api/v1/auth/refresh').status_code == 401
        client.post('/api/v1/auth/logout')
        assert client.post('/api/v1/auth/password/login', json={
            'email': email, 'password': PASSWORD,
        }).status_code == 401
        assert client.post('/api/v1/auth/password/login', json={
            'email': email, 'password': replacement,
        }).status_code == 200

    without_mail = Settings(database_url=f'sqlite:///{tmp_path / "email.db"}', data_dir=tmp_path,
                            demo_mode=False, ai_mode='local', auth_secret='s' * 32,
                            smtp_host='', smtp_from='')
    with TestClient(create_app(without_mail)) as client:
        assert client.get('/api/v1/meta').json()['email_auth_ready'] is False
        assert client.post('/api/v1/auth/password/login', json={
            'email': email, 'password': replacement,
        }).status_code == 200
        assert client.post('/api/v1/auth/email/request-code', json={'email': email}).status_code == 503


def test_password_attempts_are_limited_and_hashes_are_salted(tmp_path, monkeypatch):
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)
    assert first != second and verify_password(PASSWORD, first)
    assert not verify_password(PASSWORD[:-1], first)
    assert not verify_password(PASSWORD, 'scrypt_v1$bad$bad')

    app, sent = email_client(tmp_path, monkeypatch)
    email = 'reader@pku.edu.cn'
    with TestClient(app) as client:
        register(client, sent, email)
        client.post('/api/v1/auth/logout')
        for _ in range(8):
            assert client.post('/api/v1/auth/password/login', json={
                'email': email, 'password': 'wrong password long enough',
            }).status_code == 401
        assert client.post('/api/v1/auth/password/login', json={
            'email': email, 'password': PASSWORD,
        }).status_code == 429
        for _ in range(8):
            unknown = client.post('/api/v1/auth/password/login', json={
                'email': 'unknown@pku.edu.cn', 'password': PASSWORD,
            })
            assert unknown.status_code == 401 and unknown.json()['detail'] == '邮箱或密码错误'
        assert client.post('/api/v1/auth/password/login', json={
            'email': 'unknown@pku.edu.cn', 'password': PASSWORD,
        }).status_code == 429
