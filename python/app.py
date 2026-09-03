import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
)
from flask_migrate import Migrate
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from database import db
from models import User, Product, Cart, TokenBlocklist
from settings import flask_cors_kwargs, resolve_cors_origins, resolve_jwt_secret

_backend_dir = Path(__file__).resolve().parent
load_dotenv(_backend_dir / '.env')
load_dotenv(_backend_dir.parent / '.env')

app = Flask(__name__)
jwt_secret = resolve_jwt_secret()
CORS(app, **flask_cors_kwargs(resolve_cors_origins()))

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'sqlite:///../instance/products.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = jwt_secret
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', jwt_secret)

db.init_app(app)
migrate = Migrate(
    app,
    db,
    directory=os.path.join(_backend_dir, 'migrations'),
    render_as_batch=True,
)
jwt = JWTManager(app)


@jwt.token_in_blocklist_loader
def token_is_revoked(jwt_header, jwt_payload):
    jti = jwt_payload.get('jti')
    if not jti:
        return False
    return (
        db.session.query(TokenBlocklist.id).filter_by(jti=jti).first()
        is not None
    )


def get_current_user_id():
    """Return the authenticated user id as an int (JWT sub may be a string)."""
    return int(get_jwt_identity())


def _json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    return data


# User Registration
@app.route('/register', methods=['POST'])
def register():
    data = _json_body()
    if not data:
        return jsonify({'message': 'Request body must be JSON'}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password')
    email = (data.get('email') or '').strip()

    if not username or not password or not email:
        return jsonify({'message': 'Username, email, and password are required'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'message': 'Username already taken'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'message': 'Email already exists'}), 400

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password=hashed_password, email=email)

    db.session.add(new_user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'message': 'Username or email already exists'}), 400

    return jsonify({'message': 'User registered successfully'}), 201


# User Login
@app.route('/login', methods=['POST'])
def login():
    data = _json_body()
    if not data:
        return jsonify({'message': 'Request body must be JSON'}), 400

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({'message': 'Invalid credentials'}), 401

    user = User.query.filter_by(username=username).first()

    if not user or not check_password_hash(user.password, password):
        return jsonify({'message': 'Invalid credentials'}), 401

    access_token = create_access_token(identity=str(user.user_id))
    return jsonify({
        'access_token': access_token,
        'user': {
            'username': user.username,
            'email': user.email
        }
    }), 200


@app.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    claims = get_jwt()
    jti = claims['jti']
    exp = claims['exp']
    if TokenBlocklist.query.filter_by(jti=jti).first() is None:
        revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
        db.session.add(TokenBlocklist(
            jti=jti,
            revoked_at=revoked_at,
            expires_at=expires_at,
        ))
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
    return jsonify({'message': 'Logged out'}), 200


# Protected Route Example
@app.route('/', methods=['GET'])
@jwt_required()
def protected():
    user = db.session.get(User, get_current_user_id())
    if user is None:
        return jsonify({'message': 'User not found'}), 401
    return jsonify({'message': f'Hello {user.username}, this is a protected route!'}), 200


@app.route('/')
def home():
    return "Welcome to the Home Page!"

@app.route('/api/user/products', methods=['GET'])
@jwt_required()
def get_user_products():
    user_id = get_current_user_id()
    products = Product.query.filter_by(user_id=user_id).all()
    return jsonify([product.to_dict() for product in products]), 200
 # GET all products (public)
@app.route('/api/products', methods=['GET'])
def get_products():
    products = Product.query.all()
    return jsonify([product.to_dict() for product in products]), 200

# Create New Product (for Profile Page)
@app.route('/api/products', methods=['POST'])
@jwt_required()
def create_product():
    user_id = get_current_user_id()
    data = _json_body()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    if not all(key in data for key in ['name', 'price', 'category']):
        return jsonify({'error': 'Missing required fields'}), 400

    new_product = Product(
        user_id=user_id,
        name=data['name'],
        price=data['price'],
        category=data['category'],
        description=data.get('description', ''),
        photo_url=data.get('photo_url', '')
    )
    db.session.add(new_product)
    db.session.commit()

    return jsonify(new_product.to_dict()), 201

# Update Product (only if it belongs to the logged-in user)
@app.route('/api/products/<int:product_id>', methods=['PUT'])
@jwt_required()
def update_product(product_id):
    user_id = get_current_user_id()
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({'error': 'Product not found'}), 404

    if product.user_id != user_id:
        return jsonify({'error': 'Unauthorized access'}), 403

    data = _json_body()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    product.name = data.get('name', product.name)
    product.price = data.get('price', product.price)
    product.description = data.get('description', product.description)
    product.category = data.get('category', product.category)
    product.photo_url = data.get('photo_url', product.photo_url)

    db.session.commit()
    return jsonify(product.to_dict()), 200

# Delete Product (only if it belongs to the logged-in user)
@app.route('/api/products/<int:product_id>', methods=['DELETE'])
@jwt_required()
def delete_product(product_id):
    user_id = get_current_user_id()
    product = db.session.get(Product, product_id)
    if product is None:
        return jsonify({'error': 'Product not found'}), 404

    if product.user_id != user_id:
        return jsonify({'error': 'Unauthorized access'}), 403

    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted'}), 200


# POST create a new user (registration)
@app.route('/api/users', methods=['POST'])
def create_user():
    data = _json_body()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    if not all(key in data for key in ['username', 'password', 'email']):
        return jsonify({'error': 'Missing required fields'}), 400

    username = (data.get('username') or '').strip()
    password = data.get('password')
    email = (data.get('email') or '').strip()

    if not username or not password or not email:
        return jsonify({'error': 'Missing required fields'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already taken'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Email already exists'}), 400

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password=hashed_password, email=email)

    db.session.add(new_user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': 'Username or email already exists'}), 400

    return jsonify({'message': 'User created successfully', 'user': new_user.to_dict()}), 201


# POST add a product to the cart (for authenticated users)
@app.route('/api/cart', methods=['POST'])
@jwt_required()
def add_to_cart():
    user_id = get_current_user_id()
    data = _json_body()
    if not data:
        return jsonify({'error': 'Request body must be JSON'}), 400

    if 'product_id' not in data or 'quantity' not in data:
        return jsonify({'error': 'Missing required fields'}), 400

    product = db.session.get(Product, data['product_id'])
    if product is None:
        return jsonify({'error': 'Product not found'}), 404

    cart_item = Cart.query.filter_by(user_id=user_id, product_id=product.product_id).first()
    if cart_item:
        cart_item.quantity += data['quantity']
    else:
        cart_item = Cart(user_id=user_id, product_id=product.product_id, quantity=data['quantity'])
        db.session.add(cart_item)

    db.session.commit()
    return jsonify({'message': 'Item added to cart'}), 201


# GET cart items for the current user
@app.route('/api/cart', methods=['GET'])
@jwt_required()
def view_cart():
    user_id = get_current_user_id()
    cart_items = Cart.query.filter_by(user_id=user_id).all()
    return jsonify([{
        'product_id': item.product_id,
        'quantity': item.quantity
    } for item in cart_items]), 200


# DELETE a product from the cart (for authenticated users)
@app.route('/api/cart/<int:product_id>', methods=['DELETE'])
@jwt_required()
def delete_cart_item(product_id):
    user_id = get_current_user_id()
    cart_item = Cart.query.filter_by(user_id=user_id, product_id=product_id).first()
    if cart_item is None:
        return jsonify({'error': 'Cart item not found'}), 404

    db.session.delete(cart_item)
    db.session.commit()
    return jsonify({'message': 'Cart item deleted'}), 200

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', '5000'))
    app.run(host=host, port=port, debug=debug)
