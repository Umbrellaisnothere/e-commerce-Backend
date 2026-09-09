import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from flask import Flask
from flask_cors import CORS

from settings import (
    CORS_ALLOWED_METHODS,
    flask_cors_kwargs,
    resolve_cors_origins,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
APP_SOURCE = (BACKEND_DIR / 'app.py').read_text()
SETTINGS_SOURCE = (BACKEND_DIR / 'settings.py').read_text()

PROD_ORIGIN_1 = 'https://e-commerce-chi-one-94.vercel.app'
PROD_ORIGIN_2 = 'https://e-commerce-va1l.vercel.app'
DEV_ORIGIN = 'http://localhost:3000'
UNKNOWN_ORIGIN = 'https://malicious-example.com'


def _cors_app(origins):
    test_app = Flask(__name__)
    CORS(test_app, **flask_cors_kwargs(origins))

    @test_app.route('/api/products', methods=['GET', 'POST', 'PUT', 'DELETE'])
    def products():
        return {'ok': True}

    return test_app.test_client()


def _preflight(client, origin, request_headers, method='GET'):
    return client.options(
        '/api/products',
        headers={
            'Origin': origin,
            'Access-Control-Request-Method': method,
            'Access-Control-Request-Headers': request_headers,
        },
    )


def test_missing_cors_origins_fails_in_production():
    with pytest.raises(RuntimeError, match='CORS_ORIGINS environment variable is required'):
        resolve_cors_origins({'FLASK_ENV': 'production'})


def test_missing_cors_origins_fails_in_development():
    with pytest.raises(RuntimeError, match='CORS_ORIGINS environment variable is required'):
        resolve_cors_origins({'FLASK_ENV': 'development'})


def test_blank_cors_origins_fails():
    with pytest.raises(RuntimeError, match='CORS_ORIGINS environment variable is required'):
        resolve_cors_origins({
            'FLASK_ENV': 'production',
            'CORS_ORIGINS': '   ',
        })


def test_wildcard_cors_origins_rejected():
    with pytest.raises(RuntimeError, match='must not contain'):
        resolve_cors_origins({
            'CORS_ORIGINS': '*',
            'FLASK_ENV': 'production',
        })


def test_wildcard_vercel_preview_rejected():
    with pytest.raises(RuntimeError, match='must not contain'):
        resolve_cors_origins({
            'CORS_ORIGINS': 'https://*.vercel.app',
            'FLASK_ENV': 'production',
        })


def test_malformed_origin_without_scheme_rejected():
    with pytest.raises(RuntimeError, match='http or https'):
        resolve_cors_origins({'CORS_ORIGINS': 'localhost:3000'})


def test_non_http_origin_rejected():
    with pytest.raises(RuntimeError, match='http or https'):
        resolve_cors_origins({'CORS_ORIGINS': 'ftp://example.com'})


def test_origin_with_trailing_slash_rejected():
    with pytest.raises(RuntimeError, match='trailing slash'):
        resolve_cors_origins({
            'CORS_ORIGINS': 'https://e-commerce-chi-one-94.vercel.app/',
        })


def test_origin_with_path_rejected():
    with pytest.raises(RuntimeError, match='path or trailing slash'):
        resolve_cors_origins({'CORS_ORIGINS': 'https://example.com/app'})


def test_blank_entry_in_list_rejected():
    with pytest.raises(RuntimeError, match='blank entry'):
        resolve_cors_origins({
            'CORS_ORIGINS': f'{PROD_ORIGIN_1},,{PROD_ORIGIN_2}',
        })


def test_comma_separated_origins_and_whitespace():
    origins = resolve_cors_origins({
        'CORS_ORIGINS': (
            f'  {PROD_ORIGIN_1} , {PROD_ORIGIN_2}, {DEV_ORIGIN} '
        ),
        'FLASK_ENV': 'production',
    })
    assert origins == [PROD_ORIGIN_1, PROD_ORIGIN_2, DEV_ORIGIN]


def test_development_origin_can_be_configured():
    assert resolve_cors_origins({
        'CORS_ORIGINS': DEV_ORIGIN,
        'FLASK_ENV': 'development',
    }) == [DEV_ORIGIN]


def test_flask_cors_kwargs_are_explicit_and_not_wildcard():
    kwargs = flask_cors_kwargs([PROD_ORIGIN_1, PROD_ORIGIN_2])
    assert kwargs['origins'] == [PROD_ORIGIN_1, PROD_ORIGIN_2]
    assert kwargs['supports_credentials'] is False
    assert kwargs['send_wildcard'] is False
    assert kwargs['allow_headers'] == ['Authorization', 'Content-Type']
    assert kwargs['methods'] == ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    assert '*' not in kwargs['origins']
    assert '*' not in kwargs['allow_headers']
    assert 'PATCH' not in kwargs['methods']


def test_allowed_production_origin_is_echoed():
    client = _cors_app([PROD_ORIGIN_1, PROD_ORIGIN_2])
    resp = client.get('/api/products', headers={'Origin': PROD_ORIGIN_1})
    assert resp.headers.get('Access-Control-Allow-Origin') == PROD_ORIGIN_1
    assert resp.headers.get('Access-Control-Allow-Origin') != '*'
    assert resp.headers.get('Access-Control-Allow-Credentials') != 'true'


def test_second_production_origin_is_echoed():
    client = _cors_app([PROD_ORIGIN_1, PROD_ORIGIN_2])
    resp = client.get('/api/products', headers={'Origin': PROD_ORIGIN_2})
    assert resp.headers.get('Access-Control-Allow-Origin') == PROD_ORIGIN_2
    assert resp.headers.get('Access-Control-Allow-Origin') != '*'


def test_local_development_origin_is_echoed_when_configured():
    client = _cors_app([DEV_ORIGIN])
    resp = client.get('/api/products', headers={'Origin': DEV_ORIGIN})
    assert resp.headers.get('Access-Control-Allow-Origin') == DEV_ORIGIN
    assert resp.headers.get('Access-Control-Allow-Origin') != '*'


def test_unknown_origin_is_not_granted_cors_access():
    client = _cors_app([PROD_ORIGIN_1, PROD_ORIGIN_2, DEV_ORIGIN])
    resp = client.get('/api/products', headers={'Origin': UNKNOWN_ORIGIN})
    assert resp.headers.get('Access-Control-Allow-Origin') != UNKNOWN_ORIGIN
    assert resp.headers.get('Access-Control-Allow-Origin') != '*'
    assert resp.headers.get('Access-Control-Allow-Origin') in (None, '')


def test_responses_do_not_use_wildcard_allow_origin():
    client = _cors_app([PROD_ORIGIN_1, PROD_ORIGIN_2, DEV_ORIGIN])
    for origin in (PROD_ORIGIN_1, PROD_ORIGIN_2, DEV_ORIGIN, UNKNOWN_ORIGIN, None):
        headers = {'Origin': origin} if origin else {}
        resp = client.get('/api/products', headers=headers)
        assert resp.headers.get('Access-Control-Allow-Origin') != '*'


def test_preflight_allows_authorization_for_allowed_origin():
    client = _cors_app([PROD_ORIGIN_1, PROD_ORIGIN_2])
    resp = _preflight(client, PROD_ORIGIN_1, 'Authorization')
    allow_headers = resp.headers.get('Access-Control-Allow-Headers', '')
    assert 'authorization' in allow_headers.lower()
    assert resp.headers.get('Access-Control-Allow-Origin') == PROD_ORIGIN_1
    assert resp.headers.get('Access-Control-Allow-Origin') != '*'


def test_preflight_allows_content_type_for_allowed_origin():
    client = _cors_app([PROD_ORIGIN_1])
    resp = _preflight(client, PROD_ORIGIN_1, 'Content-Type', method='POST')
    allow_headers = resp.headers.get('Access-Control-Allow-Headers', '')
    assert 'content-type' in allow_headers.lower()
    assert resp.headers.get('Access-Control-Allow-Origin') == PROD_ORIGIN_1


def test_preflight_does_not_enable_credentials():
    client = _cors_app([PROD_ORIGIN_1, PROD_ORIGIN_2])
    resp = _preflight(
        client,
        PROD_ORIGIN_1,
        'Authorization, Content-Type',
        method='POST',
    )
    assert 'Access-Control-Allow-Credentials' not in resp.headers
    allowed_methods = {
        item.strip().upper()
        for item in resp.headers.get('Access-Control-Allow-Methods', '').split(',')
        if item.strip()
    }
    assert allowed_methods == set(CORS_ALLOWED_METHODS)
    allow_headers = resp.headers.get('Access-Control-Allow-Headers', '').lower()
    assert 'authorization' in allow_headers
    assert 'content-type' in allow_headers


def test_unknown_origin_preflight_is_not_allowed():
    client = _cors_app([PROD_ORIGIN_1])
    resp = _preflight(client, UNKNOWN_ORIGIN, 'Authorization')
    assert resp.headers.get('Access-Control-Allow-Origin') != UNKNOWN_ORIGIN
    assert resp.headers.get('Access-Control-Allow-Origin') != '*'
    assert resp.headers.get('Access-Control-Allow-Origin') in (None, '')


def test_app_source_uses_resolved_allowlist_not_bare_cors():
    assert 'flask_cors_kwargs(resolve_cors_origins())' in APP_SOURCE
    assert re.search(r'CORS\(\s*app\s*\)', APP_SOURCE) is None
    assert "origins='*'" not in APP_SOURCE
    assert 'origins="*"' not in APP_SOURCE
    assert "allow_headers='*'" not in APP_SOURCE
    assert 'allow_headers="*"' not in APP_SOURCE
    assert PROD_ORIGIN_1 not in APP_SOURCE
    assert PROD_ORIGIN_2 not in APP_SOURCE
    assert DEV_ORIGIN not in APP_SOURCE
    assert PROD_ORIGIN_1 not in SETTINGS_SOURCE
    assert PROD_ORIGIN_2 not in SETTINGS_SOURCE
    assert DEV_ORIGIN not in SETTINGS_SOURCE


def test_app_import_fails_without_cors_origins():
    env = os.environ.copy()
    env['JWT_SECRET_KEY'] = 'a' * 32
    env['FLASK_ENV'] = 'production'
    env['CORS_ORIGINS'] = ''
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
    assert 'CORS_ORIGINS' in (result.stderr + result.stdout)
