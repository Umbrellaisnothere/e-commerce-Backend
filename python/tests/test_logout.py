import os
from datetime import timedelta

import pytest
from flask_jwt_extended import create_access_token, decode_token

os.environ.setdefault('JWT_SECRET_KEY', 'a' * 32)
os.environ.setdefault('FLASK_ENV', 'development')

from app import app, db
from models import TokenBlocklist, User


@pytest.fixture
def client(tmp_path):
    uri = f'sqlite:///{tmp_path / "logout.db"}'
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


def _register_and_login(client, username, email, password):
    register = client.post('/register', json={
        'username': username,
        'email': email,
        'password': password,
    })
    assert register.status_code == 201, register.get_json()
    login = client.post('/login', json={
        'username': username,
        'password': password,
    })
    assert login.status_code == 200, login.get_json()
    token = login.get_json()['access_token']
    assert token
    return token


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_login_returns_access_token(client):
    token = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    claims = decode_token(token)
    assert 'jti' in claims
    assert claims.get('sub')


def test_token_accesses_protected_endpoint_before_logout(client):
    token = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    resp = client.get('/api/user/products', headers=_auth(token))
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_logout_returns_200_and_stores_jti(client):
    token = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    jti = decode_token(token)['jti']
    resp = client.post('/logout', headers=_auth(token))
    assert resp.status_code == 200
    assert resp.get_json().get('message') == 'Logged out'
    with app.app_context():
        row = TokenBlocklist.query.filter_by(jti=jti).first()
        assert row is not None
        assert row.jti == jti
        assert row.revoked_at is not None
        assert row.expires_at is not None


def test_revoked_token_cannot_access_protected_endpoint(client):
    token = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    assert client.post('/logout', headers=_auth(token)).status_code == 200
    resp = client.get('/api/user/products', headers=_auth(token))
    assert resp.status_code == 401
    assert resp.get_json().get('msg') == 'Token has been revoked'


def test_missing_token_on_logout_returns_401(client):
    resp = client.post('/logout')
    assert resp.status_code == 401


def test_invalid_token_on_logout_is_rejected(client):
    resp = client.post('/logout', headers=_auth('not-a-valid-jwt'))
    assert resp.status_code in (401, 422)


def test_already_revoked_token_on_logout_returns_401(client):
    token = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    assert client.post('/logout', headers=_auth(token)).status_code == 200
    resp = client.post('/logout', headers=_auth(token))
    assert resp.status_code == 401
    assert resp.get_json().get('msg') == 'Token has been revoked'


def test_other_valid_token_remains_usable_after_logout(client):
    token_a = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    token_b = _register_and_login(client, 'bob', 'bob@example.com', 'bob-pass')
    assert client.post('/logout', headers=_auth(token_a)).status_code == 200
    resp = client.get('/api/user/products', headers=_auth(token_b))
    assert resp.status_code == 200
    still_revoked = client.get('/api/user/products', headers=_auth(token_a))
    assert still_revoked.status_code == 401


def test_unrevoked_token_remains_usable(client):
    token = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    first = client.get('/api/user/products', headers=_auth(token))
    second = client.get('/api/user/products', headers=_auth(token))
    assert first.status_code == 200
    assert second.status_code == 200


def test_expired_token_returns_expired_not_revoked(client):
    token = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    with app.app_context():
        user = User.query.filter_by(username='alice').first()
        expired = create_access_token(
            identity=str(user.user_id),
            expires_delta=timedelta(seconds=-1),
        )
    resp = client.get('/api/user/products', headers=_auth(expired))
    assert resp.status_code == 401
    assert resp.get_json().get('msg') == 'Token has expired'
    logout = client.post('/logout', headers=_auth(expired))
    assert logout.status_code == 401
    assert logout.get_json().get('msg') == 'Token has expired'


def test_product_ownership_still_enforced(client):
    token_a = _register_and_login(client, 'alice', 'alice@example.com', 'alice-pass')
    token_b = _register_and_login(client, 'bob', 'bob@example.com', 'bob-pass')
    created = client.post('/api/products', headers=_auth(token_b), json={
        'name': 'Bob Item',
        'price': 10,
        'category': 'Test',
    })
    assert created.status_code == 201
    product_id = created.get_json()['id']
    put = client.put(
        f'/api/products/{product_id}',
        headers=_auth(token_a),
        json={'name': 'Hacked'},
    )
    delete = client.delete(f'/api/products/{product_id}', headers=_auth(token_a))
    assert put.status_code == 403
    assert delete.status_code == 403
    own = client.put(
        f'/api/products/{product_id}',
        headers=_auth(token_b),
        json={'name': 'Bob Item Updated'},
    )
    assert own.status_code == 200


def test_production_access_token_expiry_still_15_minutes():
    from flask_jwt_extended.config import config as jwt_config
    with app.app_context():
        assert jwt_config.access_expires == timedelta(minutes=15)
