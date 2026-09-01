import os

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
