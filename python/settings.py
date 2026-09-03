import os
from urllib.parse import urlsplit

# Values that must never be used as a real signing key (including .env.example).
_PLACEHOLDER_SECRETS = frozenset({
    'replace-with-a-long-random-value',
    'change-me',
    'changeme',
    'secret',
    'jwt-secret',
    'your-secret-key',
})

_MIN_PRODUCTION_SECRET_LENGTH = 32


def is_development(environ=None):
    env = environ if environ is not None else os.environ
    flask_env = (env.get('FLASK_ENV') or env.get('ENV') or '').strip().lower()
    if flask_env in ('development', 'dev'):
        return True
    if flask_env in ('production', 'prod'):
        return False
    return env.get('FLASK_DEBUG', '0') == '1'


def resolve_jwt_secret(environ=None):
    """Return JWT_SECRET_KEY from the environment, or raise RuntimeError.

    Never falls back to a hardcoded secret. Non-development environments also
    reject placeholders and keys shorter than 32 characters.
    """
    env = environ if environ is not None else os.environ
    secret = (env.get('JWT_SECRET_KEY') or '').strip()

    if not secret:
        raise RuntimeError(
            'JWT_SECRET_KEY environment variable is required. '
            'Copy .env.example to .env and set a long random value.'
        )

    if secret.lower() in _PLACEHOLDER_SECRETS:
        raise RuntimeError(
            'JWT_SECRET_KEY is a placeholder value. '
            'Set a unique random secret; do not commit it to Git.'
        )

    if not is_development(env) and len(secret) < _MIN_PRODUCTION_SECRET_LENGTH:
        raise RuntimeError(
            'JWT_SECRET_KEY must be at least 32 characters '
            'in a non-development environment.'
        )

    return secret


CORS_ALLOWED_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
CORS_ALLOWED_HEADERS = ['Authorization', 'Content-Type']


def _cors_missing_message(env):
    base = (
        'CORS_ORIGINS environment variable is required. '
        'Set a comma-separated allowlist of frontend origins '
        '(scheme and host, optional port, no trailing slash). '
        'Wildcard origins are not permitted.'
    )
    if is_development(env):
        return (
            base
            + ' Development does not automatically allow localhost origins.'
        )
    return base + ' Production has no default or localhost fallback.'


def _normalize_cors_origin(origin):
    if '*' in origin:
        raise RuntimeError(
            'CORS_ORIGINS must not contain "*". '
            'Use an explicit http(s) origin allowlist.'
        )

    parts = urlsplit(origin)
    scheme = (parts.scheme or '').lower()
    if scheme not in ('http', 'https'):
        raise RuntimeError(
            'CORS_ORIGINS entries must be http or https origins, '
            f'got {origin!r}.'
        )
    if not parts.hostname:
        raise RuntimeError(
            'CORS_ORIGINS entries must include a host, '
            f'got {origin!r}.'
        )
    if parts.username or parts.password:
        raise RuntimeError(
            'CORS_ORIGINS entries must not include userinfo, '
            f'got {origin!r}.'
        )
    if parts.path not in ('',):
        raise RuntimeError(
            'CORS_ORIGINS entries must not include a path or trailing slash, '
            f'got {origin!r}.'
        )
    if parts.query or parts.fragment:
        raise RuntimeError(
            'CORS_ORIGINS entries must not include a query or fragment, '
            f'got {origin!r}.'
        )

    return f'{scheme}://{parts.netloc}'


def resolve_cors_origins(environ=None):
    """Return the CORS origin allowlist from CORS_ORIGINS.

    Missing or blank values fail closed in every environment. There is no
    fallback to '*' or localhost.
    """
    env = environ if environ is not None else os.environ
    raw = env.get('CORS_ORIGINS')
    if raw is None or not str(raw).strip():
        raise RuntimeError(_cors_missing_message(env))

    origins = []
    for part in str(raw).split(','):
        origin = part.strip()
        if not origin:
            raise RuntimeError(
                'CORS_ORIGINS contains a blank entry. '
                'Use a comma-separated list of http(s) origins '
                'with no trailing slash.'
            )
        origins.append(_normalize_cors_origin(origin))
    return origins


def flask_cors_kwargs(origins):
    """Keyword arguments for flask_cors.CORS. Never uses wildcard origins."""
    return {
        'origins': list(origins),
        'methods': list(CORS_ALLOWED_METHODS),
        'allow_headers': list(CORS_ALLOWED_HEADERS),
        'supports_credentials': False,
        'send_wildcard': False,
    }


def normalize_rate_limit_username(value):
    """Normalize a login username for rate-limit keys only.

    Does not change authentication or database lookup semantics.
    """
    if value is None:
        return ''
    return str(value).strip().lower()
