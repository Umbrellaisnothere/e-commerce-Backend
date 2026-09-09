import os

import pytest

os.environ.setdefault('JWT_SECRET_KEY', 'a' * 32)
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

from app import app, db
from models import User


REGISTRATION_CONFLICT = {'error': 'Registration failed'}
REGISTRATION_PATHS = ('/register', '/api/users')


@pytest.fixture
def client(tmp_path):
    uri = f'sqlite:///{tmp_path / "register_enum.db"}'
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


def _payload(username, email, password='new-pass'):
    return {
        'username': username,
        'email': email,
        'password': password,
    }


def _create_alice(client, path):
    created = client.post(
        path,
        json=_payload('alice', 'alice@example.com', 'alice-pass'),
    )
    assert created.status_code == 201
    return created


def _assert_generic_conflict(response):
    assert response.status_code == 400
    assert response.is_json
    assert response.get_json() == REGISTRATION_CONFLICT
    body = response.get_data(as_text=True).lower()
    assert 'already taken' not in body
    assert 'already exists' not in body
    assert 'username' not in body
    assert 'email' not in body


def _comparable_headers(response):
    return {
        key: value
        for key, value in response.headers.items()
        if key.lower() not in ('date', 'set-cookie')
    }


@pytest.mark.parametrize('path', REGISTRATION_PATHS)
def test_duplicate_username_returns_generic_conflict(client, path):
    _create_alice(client, path)
    resp = client.post(
        path,
        json=_payload('alice', 'other@example.com'),
    )
    _assert_generic_conflict(resp)
    with app.app_context():
        assert User.query.count() == 1


@pytest.mark.parametrize('path', REGISTRATION_PATHS)
def test_duplicate_email_returns_generic_conflict(client, path):
    _create_alice(client, path)
    resp = client.post(
        path,
        json=_payload('other', 'alice@example.com'),
    )
    _assert_generic_conflict(resp)
    with app.app_context():
        assert User.query.count() == 1


@pytest.mark.parametrize('path', REGISTRATION_PATHS)
def test_username_and_email_conflicts_are_indistinguishable(client, path):
    _create_alice(client, path)
    username_conflict = client.post(
        path,
        json=_payload('alice', 'other@example.com'),
    )
    email_conflict = client.post(
        path,
        json=_payload('other', 'alice@example.com'),
    )
    both_conflict = client.post(
        path,
        json=_payload('alice', 'alice@example.com'),
    )

    _assert_generic_conflict(username_conflict)
    _assert_generic_conflict(email_conflict)
    _assert_generic_conflict(both_conflict)

    assert username_conflict.status_code == email_conflict.status_code
    assert username_conflict.get_json() == email_conflict.get_json()
    assert both_conflict.get_json() == username_conflict.get_json()
    assert _comparable_headers(username_conflict) == _comparable_headers(email_conflict)
    assert _comparable_headers(both_conflict) == _comparable_headers(username_conflict)


def test_register_and_api_users_conflicts_match(client):
    _create_alice(client, '/register')

    register_username = client.post(
        '/register',
        json=_payload('alice', 'other@example.com'),
    )
    api_username = client.post(
        '/api/users',
        json=_payload('alice', 'another@example.com'),
    )
    register_email = client.post(
        '/register',
        json=_payload('other', 'alice@example.com'),
    )
    api_email = client.post(
        '/api/users',
        json=_payload('another', 'alice@example.com'),
    )

    for resp in (register_username, api_username, register_email, api_email):
        _assert_generic_conflict(resp)

    assert register_username.status_code == api_username.status_code
    assert register_username.get_json() == api_username.get_json()
    assert register_email.get_json() == api_email.get_json()
    assert register_username.get_json() == register_email.get_json()
    assert api_username.get_json() == api_email.get_json()


def test_register_success_still_works(client):
    resp = client.post(
        '/register',
        json=_payload('bob', 'bob@example.com', 'bob-pass'),
    )
    assert resp.status_code == 201
    assert resp.get_json() == {'message': 'User registered successfully'}
    with app.app_context():
        user = User.query.filter_by(username='bob').first()
        assert user is not None
        assert user.email == 'bob@example.com'


def test_api_users_success_still_works(client):
    resp = client.post(
        '/api/users',
        json=_payload('carol', 'carol@example.com', 'carol-pass'),
    )
    assert resp.status_code == 201
    payload = resp.get_json()
    assert payload['message'] == 'User created successfully'
    assert payload['user']['username'] == 'carol'
    assert payload['user']['email'] == 'carol@example.com'
    with app.app_context():
        assert User.query.filter_by(email='carol@example.com').first() is not None
