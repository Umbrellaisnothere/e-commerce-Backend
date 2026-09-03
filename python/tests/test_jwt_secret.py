import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from settings import resolve_jwt_secret, is_development

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def test_missing_secret_raises():
    with pytest.raises(RuntimeError, match='JWT_SECRET_KEY environment variable is required'):
        resolve_jwt_secret({})


def test_blank_secret_raises():
    with pytest.raises(RuntimeError, match='JWT_SECRET_KEY environment variable is required'):
        resolve_jwt_secret({'JWT_SECRET_KEY': '   '})


def test_placeholder_secret_raises():
    with pytest.raises(RuntimeError, match='placeholder'):
        resolve_jwt_secret({
            'JWT_SECRET_KEY': 'replace-with-a-long-random-value',
            'FLASK_ENV': 'production',
        })


def test_short_secret_rejected_in_production():
    with pytest.raises(RuntimeError, match='at least 32 characters'):
        resolve_jwt_secret({
            'JWT_SECRET_KEY': 'short-dev-secret',
            'FLASK_ENV': 'production',
        })


def test_short_secret_rejected_when_env_unset():
    with pytest.raises(RuntimeError, match='at least 32 characters'):
        resolve_jwt_secret({
            'JWT_SECRET_KEY': 'short-dev-secret',
        })


def test_short_secret_allowed_in_development():
    secret = resolve_jwt_secret({
        'JWT_SECRET_KEY': 'short-dev-secret',
        'FLASK_ENV': 'development',
    })
    assert secret == 'short-dev-secret'


def test_valid_production_secret_returned():
    secret = 'a' * 32
    assert resolve_jwt_secret({
        'JWT_SECRET_KEY': secret,
        'FLASK_ENV': 'production',
    }) == secret


def test_is_development_from_flask_env():
    assert is_development({'FLASK_ENV': 'development'}) is True
    assert is_development({'FLASK_ENV': 'production'}) is False
    assert is_development({}) is False


def test_app_source_does_not_hardcode_jwt_secret():
    source = (BACKEND_DIR / 'app.py').read_text()
    assert 'resolve_jwt_secret()' in source
    assert not re.search(
        r"JWT_SECRET_KEY['\"]?\s*\]?\s*=\s*['\"][0-9a-fA-F]{32,}",
        source,
    )


def test_app_import_fails_without_secret():
    env = os.environ.copy()
    env.pop('JWT_SECRET_KEY', None)
    env.pop('SECRET_KEY', None)
    env['CORS_ORIGINS'] = 'http://localhost:3000'
    env['FLASK_ENV'] = 'production'
    env['PYTHONPATH'] = str(BACKEND_DIR)
    result = subprocess.run(
        [sys.executable, '-c', 'import app'],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert 'JWT_SECRET_KEY' in (result.stderr + result.stdout)
