import os

import pytest

os.environ.setdefault('JWT_SECRET_KEY', 'a' * 32)
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

from app import app, db
from models import User


@pytest.fixture
def client(tmp_path):
    uri = f'sqlite:///{tmp_path / "users.db"}'
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


def _assert_not_user_directory(response):
    assert response.status_code != 200
    body = response.get_json(silent=True)
    if isinstance(body, list):
        assert not any(
            isinstance(item, dict) and 'email' in item
            for item in body
        )


def test_get_api_users_without_token_is_not_a_user_directory(client):
    _assert_not_user_directory(client.get('/api/users'))


def test_get_api_users_with_token_is_not_a_user_directory(client):
    created = client.post('/api/users', json={
        'username': 'alice',
        'email': 'alice@example.com',
        'password': 'alice-pass',
    })
    assert created.status_code == 201
    login = client.post('/login', json={
        'username': 'alice',
        'password': 'alice-pass',
    })
    token = login.get_json()['access_token']
    resp = client.get('/api/users', headers={'Authorization': f'Bearer {token}'})
    _assert_not_user_directory(resp)


def test_post_api_users_registration_still_works(client):
    resp = client.post('/api/users', json={
        'username': 'carol',
        'email': 'carol@example.com',
        'password': 'carol-pass',
    })
    assert resp.status_code == 201
    payload = resp.get_json()
    assert payload['message'] == 'User created successfully'
    assert payload['user']['username'] == 'carol'
    assert payload['user']['email'] == 'carol@example.com'
    assert 'password' not in payload['user']
    with app.app_context():
        user = User.query.filter_by(email='carol@example.com').first()
        assert user is not None
        assert user.password != 'carol-pass'


def test_user_to_dict_does_not_expose_password(client):
    client.post('/api/users', json={
        'username': 'dave',
        'email': 'dave@example.com',
        'password': 'dave-pass',
    })
    with app.app_context():
        user = User.query.filter_by(username='dave').first()
        serialized = user.to_dict()
        assert 'password' not in serialized
        assert set(serialized.keys()) == {'id', 'username', 'email'}
        assert serialized['username'] == 'dave'
        assert serialized['email'] == 'dave@example.com'
