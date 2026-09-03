import os

import pytest

os.environ.setdefault('JWT_SECRET_KEY', 'a' * 32)
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

from app import app, db
from settings import normalize_rate_limit_username


RATE_LIMIT_ERROR = {'error': 'Too many requests'}


@pytest.fixture
def client(tmp_path):
    uri = f'sqlite:///{tmp_path / "rate_limit.db"}'
    app.config['SQLALCHEMY_DATABASE_URI'] = uri
    app.config['TESTING'] = True
    with app.app_context():
        db.session.remove()
        engines = db._app_engines.setdefault(app, {})
        for engine in list(engines.values()):
            engine.dispose()
        engines.clear()
        options = {'url': uri}
        db._apply_driver_defaults(options, app)
        engines[None] = db._make_engine(None, options, app)
        db.create_all()
        yield app.test_client()
        db.session.remove()


def _post(client, path, ip, payload):
    return client.post(
        path,
        json=payload,
        environ_overrides={'REMOTE_ADDR': ip},
    )


def _login(client, ip, username, password='wrong-password'):
    return _post(client, '/login', ip, {
        'username': username,
        'password': password,
    })


def _register(client, ip, username, email):
    return _post(client, '/register', ip, {
        'username': username,
        'email': email,
        'password': 'register-pass',
    })


def _create_user(client, ip, username, email):
    return _post(client, '/api/users', ip, {
        'username': username,
        'email': email,
        'password': 'register-pass',
    })


def _assert_rate_limited(response):
    assert response.status_code == 429
    assert response.is_json
    assert response.get_json() == RATE_LIMIT_ERROR
    body = response.get_data(as_text=True)
    assert 'password' not in body.lower()
    assert 'access_token' not in body


def test_normalize_rate_limit_username():
    assert normalize_rate_limit_username(None) == ''
    assert normalize_rate_limit_username(' Alice ') == 'alice'
    assert normalize_rate_limit_username('ALICE') == 'alice'
    assert normalize_rate_limit_username(123) == '123'


def test_login_succeeds_below_the_limit(client):
    created = _register(client, '203.0.113.10', 'alice', 'alice@example.com')
    assert created.status_code == 201
    resp = _login(client, '203.0.113.10', 'alice', 'register-pass')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['access_token']
    assert payload['user']['username'] == 'alice'


def test_login_invalid_credentials_unchanged_below_limit(client):
    resp = _login(client, '203.0.113.11', 'nobody', 'bad-pass')
    assert resp.status_code == 401
    assert resp.get_json() == {'message': 'Invalid credentials'}


def test_login_ip_limit_returns_stable_json_429(client):
    ip = '203.0.113.12'
    statuses = []
    for index in range(11):
        resp = _login(client, ip, f'user{index}')
        statuses.append(resp.status_code)
        if index < 10:
            assert resp.status_code == 401
            assert resp.get_json() == {'message': 'Invalid credentials'}
        else:
            _assert_rate_limited(resp)
    assert statuses.count(429) == 1


def test_different_ip_has_its_own_login_budget(client):
    blocked_ip = '203.0.113.13'
    other_ip = '203.0.113.14'
    for index in range(10):
        assert _login(client, blocked_ip, f'spray{index}').status_code == 401
    _assert_rate_limited(_login(client, blocked_ip, 'spray-over'))
    resp = _login(client, other_ip, 'other-user')
    assert resp.status_code == 401
    assert resp.get_json() == {'message': 'Invalid credentials'}


def test_username_limit_applies_across_ips(client):
    for index in range(10):
        ip = f'198.51.100.{index + 1}'
        resp = _login(client, ip, 'target-user', 'wrong')
        assert resp.status_code == 401
    _assert_rate_limited(_login(client, '198.51.100.50', 'target-user', 'wrong'))


def test_username_normalization_shares_login_budget(client):
    variants = [
        'NormUser',
        ' normuser ',
        'NORMUSER',
        'Normuser',
        ' normUser',
        'normuser',
        ' nOrMuSeR ',
        'NORMUSER ',
        ' NormUser',
        'normUSER',
    ]
    assert len(variants) == 10
    for index, username in enumerate(variants):
        ip = f'192.0.2.{index + 1}'
        resp = _login(client, ip, username, 'wrong')
        assert resp.status_code == 401, resp.get_json()
    _assert_rate_limited(_login(client, '192.0.2.50', '  NORMUSER  ', 'wrong'))


def test_register_is_limited_to_five_per_hour_per_ip(client):
    ip = '203.0.113.20'
    for index in range(5):
        resp = _register(client, ip, f'reg{index}', f'reg{index}@example.com')
        assert resp.status_code == 201, resp.get_json()
    _assert_rate_limited(
        _register(client, ip, 'reg-over', 'reg-over@example.com')
    )


def test_api_users_is_limited_to_five_per_hour_per_ip(client):
    ip = '203.0.113.21'
    for index in range(5):
        resp = _create_user(client, ip, f'api{index}', f'api{index}@example.com')
        assert resp.status_code == 201, resp.get_json()
    _assert_rate_limited(
        _create_user(client, ip, 'api-over', 'api-over@example.com')
    )


def test_registration_routes_share_ip_budget(client):
    ip = '203.0.113.22'
    for index in range(5):
        resp = _register(client, ip, f'share{index}', f'share{index}@example.com')
        assert resp.status_code == 201, resp.get_json()
    _assert_rate_limited(
        _create_user(client, ip, 'share-over', 'share-over@example.com')
    )


def test_registration_still_works_below_the_limit(client):
    resp = _register(client, '203.0.113.23', 'okuser', 'okuser@example.com')
    assert resp.status_code == 201
    assert resp.get_json()['message'] == 'User registered successfully'
    created = _create_user(
        client,
        '203.0.113.24',
        'okapi',
        'okapi@example.com',
    )
    assert created.status_code == 201
    assert created.get_json()['message'] == 'User created successfully'
    assert 'password' not in created.get_json()['user']
