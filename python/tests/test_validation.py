import math
import os

import pytest

os.environ.setdefault('JWT_SECRET_KEY', 'a' * 32)
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

from app import MAX_CART_QUANTITY, MAX_CONTENT_LENGTH, _is_valid_price, app, db
from models import Cart, Product, User

INVALID_STRING_VALUES = (123, 1.5, True, False, None, [], {})
INVALID_QUANTITIES = (0, -1, 1.5, '5', 'abc', True, False, None, [], {}, 1001)
INVALID_PRICES = (-5, -0.01, '9.99', True, False, None, [], {})


@pytest.fixture
def client(tmp_path):
    uri = f'sqlite:///{tmp_path / "validation.db"}'
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


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _register_and_login(client, username='alice', email='alice@example.com', password='alice-pass'):
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
    return login.get_json()['access_token']


def _create_product(client, token, name='Widget', price=9.99, category='tools', **extra):
    payload = {'name': name, 'price': price, 'category': category}
    payload.update(extra)
    resp = client.post('/api/products', headers=_auth(token), json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_valid_quantity_accepted(client):
    token = _register_and_login(client)
    product = _create_product(client, token)
    resp = client.post('/api/cart', headers=_auth(token), json={
        'product_id': product['id'],
        'quantity': 1,
    })
    assert resp.status_code == 201
    cart = client.get('/api/cart', headers=_auth(token))
    assert cart.status_code == 200
    assert cart.get_json() == [{'product_id': product['id'], 'quantity': 1}]


@pytest.mark.parametrize('quantity', [1, 100, 1000])
def test_quantity_bounds_accepted(client, quantity):
    token = _register_and_login(client, f'user{quantity}', f'user{quantity}@example.com')
    product = _create_product(client, token, name=f'Item{quantity}')
    resp = client.post('/api/cart', headers=_auth(token), json={
        'product_id': product['id'],
        'quantity': quantity,
    })
    assert resp.status_code == 201, resp.get_json()


@pytest.mark.parametrize('quantity', INVALID_QUANTITIES)
def test_invalid_quantity_rejected_with_400(client, quantity):
    token = _register_and_login(client)
    product = _create_product(client, token)
    resp = client.post('/api/cart', headers=_auth(token), json={
        'product_id': product['id'],
        'quantity': quantity,
    })
    assert resp.status_code == 400
    body = resp.get_json()
    assert body == {'error': 'Invalid quantity'}
    assert 'Traceback' not in (resp.get_data(as_text=True) or '')


def test_invalid_quantity_is_not_persisted(client):
    token = _register_and_login(client)
    product = _create_product(client, token)
    for quantity in INVALID_QUANTITIES:
        resp = client.post('/api/cart', headers=_auth(token), json={
            'product_id': product['id'],
            'quantity': quantity,
        })
        assert resp.status_code == 400
    cart = client.get('/api/cart', headers=_auth(token))
    assert cart.get_json() == []
    with app.app_context():
        assert Cart.query.count() == 0


def test_valid_positive_and_zero_prices_accepted_on_create(client):
    token = _register_and_login(client)
    positive = _create_product(client, token, name='Priced', price=9.99)
    assert positive['price'] == 9.99
    zero = client.post('/api/products', headers=_auth(token), json={
        'name': 'Free',
        'price': 0,
        'category': 'tools',
    })
    assert zero.status_code == 201
    assert zero.get_json()['price'] == 0
    zero_float = client.post('/api/products', headers=_auth(token), json={
        'name': 'FreeFloat',
        'price': 0.0,
        'category': 'tools',
    })
    assert zero_float.status_code == 201
    assert zero_float.get_json()['price'] == 0.0


@pytest.mark.parametrize('price', INVALID_PRICES)
def test_invalid_price_rejected_on_create(client, price):
    token = _register_and_login(client)
    resp = client.post('/api/products', headers=_auth(token), json={
        'name': 'BadPrice',
        'price': price,
        'category': 'tools',
    })
    assert resp.status_code == 400
    assert resp.get_json() == {'error': 'Invalid price'}


def test_create_rejects_infinity_and_does_not_persist(client):
    token = _register_and_login(client)
    resp = client.post(
        '/api/products',
        headers=_auth(token),
        data='{"name":"InfPrice","price":1e999,"category":"tools"}',
        content_type='application/json',
    )
    assert resp.status_code == 400
    assert resp.get_json() == {'error': 'Invalid price'}
    listing = client.get('/api/products')
    assert all(item['name'] != 'InfPrice' for item in listing.get_json())


def test_create_rejects_nan_price(client):
    token = _register_and_login(client)
    resp = client.post(
        '/api/products',
        headers=_auth(token),
        data='{"name":"NanPrice","price":NaN,"category":"tools"}',
        content_type='application/json',
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert body is not None
    assert 'error' in body or 'message' in body
    listing = client.get('/api/products')
    assert all(item['name'] != 'NanPrice' for item in listing.get_json())
    assert not _is_valid_price(float('nan'))
    assert not _is_valid_price(float('inf'))
    assert not _is_valid_price(float('-inf'))
    assert not math.isfinite(float('nan'))


def test_invalid_price_is_not_persisted_on_create(client):
    token = _register_and_login(client)
    for price in INVALID_PRICES:
        resp = client.post('/api/products', headers=_auth(token), json={
            'name': 'ShouldNotExist',
            'price': price,
            'category': 'tools',
        })
        assert resp.status_code == 400
    listing = client.get('/api/products')
    assert listing.get_json() == []
    with app.app_context():
        assert Product.query.count() == 0


def test_put_accepts_valid_and_zero_price(client):
    token = _register_and_login(client)
    product = _create_product(client, token, price=5)
    updated = client.put(
        f'/api/products/{product["id"]}',
        headers=_auth(token),
        json={'price': 12.5},
    )
    assert updated.status_code == 200
    assert updated.get_json()['price'] == 12.5
    zero = client.put(
        f'/api/products/{product["id"]}',
        headers=_auth(token),
        json={'price': 0},
    )
    assert zero.status_code == 200
    assert zero.get_json()['price'] == 0


@pytest.mark.parametrize('price', INVALID_PRICES)
def test_invalid_price_rejected_on_put(client, price):
    token = _register_and_login(client)
    product = _create_product(client, token, price=9.99)
    resp = client.put(
        f'/api/products/{product["id"]}',
        headers=_auth(token),
        json={'price': price},
    )
    assert resp.status_code == 400
    assert resp.get_json() == {'error': 'Invalid price'}
    current = client.get('/api/products').get_json()[0]
    assert current['price'] == 9.99


def test_put_rejects_infinity_and_does_not_change_price(client):
    token = _register_and_login(client)
    product = _create_product(client, token, price=9.99)
    resp = client.put(
        f'/api/products/{product["id"]}',
        headers=_auth(token),
        data='{"price":1e999}',
        content_type='application/json',
    )
    assert resp.status_code == 400
    assert resp.get_json() == {'error': 'Invalid price'}
    current = client.get('/api/products').get_json()[0]
    assert current['price'] == 9.99


def test_put_rejects_nan_and_does_not_change_price(client):
    token = _register_and_login(client)
    product = _create_product(client, token, price=9.99)
    resp = client.put(
        f'/api/products/{product["id"]}',
        headers=_auth(token),
        data='{"price":NaN}',
        content_type='application/json',
    )
    assert resp.status_code == 400
    current = client.get('/api/products').get_json()[0]
    assert current['price'] == 9.99


@pytest.mark.parametrize('field', ['username', 'password', 'email'])
@pytest.mark.parametrize('value', INVALID_STRING_VALUES)
def test_register_rejects_non_string_fields(client, field, value):
    payload = {
        'username': 'bob',
        'password': 'bob-pass',
        'email': 'bob@example.com',
    }
    payload[field] = value
    resp = client.post('/register', json=payload)
    assert resp.status_code == 400
    assert resp.status_code != 500
    assert resp.get_json() == {'error': f'Invalid {field}'}
    with app.app_context():
        assert User.query.count() == 0


@pytest.mark.parametrize('field', ['username', 'password', 'email'])
@pytest.mark.parametrize('value', INVALID_STRING_VALUES)
def test_api_users_rejects_non_string_fields(client, field, value):
    payload = {
        'username': 'carol',
        'password': 'carol-pass',
        'email': 'carol@example.com',
    }
    payload[field] = value
    resp = client.post('/api/users', json=payload)
    assert resp.status_code == 400
    assert resp.get_json() == {'error': f'Invalid {field}'}
    with app.app_context():
        assert User.query.count() == 0


@pytest.mark.parametrize('field', ['username', 'password'])
@pytest.mark.parametrize('value', INVALID_STRING_VALUES)
def test_login_rejects_non_string_fields(client, field, value):
    _register_and_login(client)
    payload = {'username': 'alice', 'password': 'alice-pass'}
    payload[field] = value
    resp = client.post('/login', json=payload)
    assert resp.status_code == 400
    assert resp.status_code != 500
    assert resp.get_json() == {'error': f'Invalid {field}'}


@pytest.mark.parametrize('field', ['name', 'category', 'description', 'photo_url'])
@pytest.mark.parametrize('value', INVALID_STRING_VALUES)
def test_create_product_rejects_non_string_fields(client, field, value):
    token = _register_and_login(client)
    payload = {
        'name': 'Gadget',
        'price': 3.5,
        'category': 'tools',
        'description': 'nice',
        'photo_url': 'http://example.com/a.png',
    }
    payload[field] = value
    resp = client.post('/api/products', headers=_auth(token), json=payload)
    assert resp.status_code == 400
    assert resp.get_json() == {'error': f'Invalid {field}'}
    assert client.get('/api/products').get_json() == []


@pytest.mark.parametrize('field', ['name', 'category', 'description', 'photo_url'])
@pytest.mark.parametrize('value', INVALID_STRING_VALUES)
def test_update_product_rejects_non_string_fields(client, field, value):
    token = _register_and_login(client)
    product = _create_product(
        client,
        token,
        name='KeepMe',
        category='tools',
        description='old',
        photo_url='http://example.com/old.png',
    )
    resp = client.put(
        f'/api/products/{product["id"]}',
        headers=_auth(token),
        json={field: value},
    )
    assert resp.status_code == 400
    assert resp.get_json() == {'error': f'Invalid {field}'}
    current = client.get('/api/products').get_json()[0]
    assert current['name'] == 'KeepMe'
    assert current['category'] == 'tools'
    assert current['description'] == 'old'
    assert current['photo_url'] == 'http://example.com/old.png'


def test_register_missing_fields_still_use_existing_message(client):
    resp = client.post('/register', json={
        'username': '',
        'password': '',
        'email': '',
    })
    assert resp.status_code == 400
    assert resp.get_json() == {
        'message': 'Username, email, and password are required',
    }


def test_login_empty_credentials_still_401(client):
    resp = client.post('/login', json={'username': '', 'password': ''})
    assert resp.status_code == 401
    assert resp.get_json() == {'message': 'Invalid credentials'}


def test_api_users_missing_keys_still_use_existing_error(client):
    resp = client.post('/api/users', json={'username': 'only-name'})
    assert resp.status_code == 400
    assert resp.get_json() == {'error': 'Missing required fields'}


def test_request_exceeding_max_content_length_is_rejected(client):
    oversized = b'x' * (MAX_CONTENT_LENGTH + 1)
    resp = client.post(
        '/login',
        data=oversized,
        content_type='application/json',
    )
    assert resp.status_code == 413
    assert resp.get_json() == {'error': 'Request too large'}
    assert MAX_CART_QUANTITY == 1000


def test_boolean_is_not_accepted_as_integer_quantity_or_price():
    assert not _is_valid_price(True)
    assert not _is_valid_price(False)
    assert _is_valid_price(0)
    assert _is_valid_price(9.99)
    assert not _is_valid_price(float('nan'))
    assert not _is_valid_price(float('inf'))
