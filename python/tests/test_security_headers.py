import os

import pytest

os.environ.setdefault('JWT_SECRET_KEY', 'a' * 32)
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

from app import app, db


ALLOWED_ORIGIN = 'http://localhost:3000'
UNKNOWN_ORIGIN = 'https://malicious-example.com'


@pytest.fixture
def client(tmp_path):
    uri = f'sqlite:///{tmp_path / "headers.db"}'
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


def _assert_global_security_headers(response):
    assert response.headers.get('X-Content-Type-Options') == 'nosniff'
    assert response.headers.get('X-Frame-Options') == 'DENY'


def _assert_no_store(response):
    assert response.headers.get('Cache-Control') == 'no-store'


def _assert_not_no_store(response):
    cache_control = response.headers.get('Cache-Control', '')
    assert 'no-store' not in cache_control.lower()


def _assert_no_set_cookie(response):
    assert 'Set-Cookie' not in response.headers


def _register(client, username='alice', email='alice@example.com'):
    return client.post('/register', json={
        'username': username,
        'email': email,
        'password': 'alice-pass',
    })


def _login(client, username='alice', password='alice-pass'):
    return client.post('/login', json={
        'username': username,
        'password': password,
    })


def test_public_products_have_global_headers_but_remain_cacheable(client):
    resp = client.get('/api/products')
    assert resp.status_code == 200
    _assert_global_security_headers(resp)
    _assert_not_no_store(resp)
    _assert_no_set_cookie(resp)


def test_successful_login_has_security_headers_and_no_store(client):
    assert _register(client).status_code == 201
    resp = _login(client)
    assert resp.status_code == 200
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)
    payload = resp.get_json()
    assert payload['access_token']
    assert 'password' not in payload


def test_register_has_security_headers_and_no_store(client):
    resp = _register(client)
    assert resp.status_code == 201
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)


def test_api_users_has_security_headers_and_no_store(client):
    resp = client.post('/api/users', json={
        'username': 'carol',
        'email': 'carol@example.com',
        'password': 'carol-pass',
    })
    assert resp.status_code == 201
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)
    assert 'password' not in resp.get_json()['user']


def test_protected_api_response_has_security_headers_and_no_store(client):
    _register(client)
    token = _login(client).get_json()['access_token']
    resp = client.get(
        '/api/user/products',
        headers={'Authorization': f'Bearer {token}'},
    )
    assert resp.status_code == 200
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)


def test_logout_has_security_headers_and_no_store(client):
    _register(client)
    token = _login(client).get_json()['access_token']
    resp = client.post('/logout', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)


def test_login_401_has_security_headers_and_no_store(client):
    resp = _login(client, username='nobody', password='bad')
    assert resp.status_code == 401
    assert resp.get_json() == {'message': 'Invalid credentials'}
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)


def test_jwt_protected_401_has_security_headers_and_no_store(client):
    resp = client.get('/api/cart')
    assert resp.status_code == 401
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)


def test_404_has_global_security_headers(client):
    resp = client.get('/no-such-route')
    assert resp.status_code == 404
    _assert_global_security_headers(resp)


def test_405_has_global_security_headers(client):
    resp = client.get('/api/users')
    assert resp.status_code == 405
    _assert_global_security_headers(resp)


def test_login_429_has_security_headers_and_no_store(client):
    ip = '203.0.113.40'
    for index in range(10):
        resp = client.post(
            '/login',
            json={'username': f'rl{index}', 'password': 'x'},
            environ_overrides={'REMOTE_ADDR': ip},
        )
        assert resp.status_code == 401
    limited = client.post(
        '/login',
        json={'username': 'rl-over', 'password': 'x'},
        environ_overrides={'REMOTE_ADDR': ip},
    )
    assert limited.status_code == 429
    assert limited.get_json() == {'error': 'Too many requests'}
    _assert_global_security_headers(limited)
    _assert_no_store(limited)
    _assert_no_set_cookie(limited)


def test_options_preflight_keeps_cors_and_gains_security_headers(client):
    resp = client.options('/login', headers={
        'Origin': ALLOWED_ORIGIN,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'Authorization, Content-Type',
    })
    assert resp.status_code == 200
    _assert_global_security_headers(resp)
    assert resp.headers.get('Access-Control-Allow-Origin') == ALLOWED_ORIGIN
    allow_headers = resp.headers.get('Access-Control-Allow-Headers', '').lower()
    assert 'authorization' in allow_headers
    assert 'content-type' in allow_headers
    _assert_no_set_cookie(resp)


def test_allowlisted_origin_still_receives_cors_on_products(client):
    resp = client.get('/api/products', headers={'Origin': ALLOWED_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get('Access-Control-Allow-Origin') == ALLOWED_ORIGIN
    _assert_global_security_headers(resp)
    _assert_not_no_store(resp)


def test_unknown_origin_is_still_not_granted_cors(client):
    resp = client.get('/api/products', headers={'Origin': UNKNOWN_ORIGIN})
    assert resp.status_code == 200
    assert resp.headers.get('Access-Control-Allow-Origin') != UNKNOWN_ORIGIN
    assert resp.headers.get('Access-Control-Allow-Origin') != '*'
    _assert_global_security_headers(resp)
    _assert_not_no_store(resp)


def test_protected_cart_response_has_no_store(client):
    _register(client)
    token = _login(client).get_json()['access_token']
    resp = client.get('/api/cart', headers={'Authorization': f'Bearer {token}'})
    assert resp.status_code == 200
    _assert_global_security_headers(resp)
    _assert_no_store(resp)
    _assert_no_set_cookie(resp)
