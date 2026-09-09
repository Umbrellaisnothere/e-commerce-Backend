import os

import pytest

os.environ.setdefault('JWT_SECRET_KEY', 'a' * 32)
os.environ.setdefault('FLASK_ENV', 'development')
os.environ.setdefault('CORS_ORIGINS', 'http://localhost:3000')

from app import limiter


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Keep limiter tests isolated without disabling production limits."""
    limiter.reset()
    yield
    limiter.reset()
