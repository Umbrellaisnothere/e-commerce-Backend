import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

from seed import (
    ANGEL_EMAIL,
    ANGEL_USERNAME,
    MITCHELLE_EMAIL,
    MITCHELLE_USERNAME,
    SeedRefused,
    assert_seed_allowed,
    hash_seed_password,
    resolve_seed_password,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
SEED_SOURCE = (BACKEND_DIR / 'seed.py').read_text()


def test_development_seeding_is_allowed():
    assert_seed_allowed({'FLASK_ENV': 'development'})
    assert_seed_allowed({'FLASK_ENV': 'dev'})


def test_production_seeding_is_rejected():
    with pytest.raises(SeedRefused, match='production'):
        assert_seed_allowed({'FLASK_ENV': 'production'})
    with pytest.raises(SeedRefused, match='production'):
        assert_seed_allowed({'FLASK_ENV': 'prod'})


def test_unset_flask_env_is_rejected():
    with pytest.raises(SeedRefused, match='FLASK_ENV'):
        assert_seed_allowed({})


def test_seed_allow_cannot_bypass_production():
    with pytest.raises(SeedRefused, match='SEED_ALLOW cannot override production'):
        assert_seed_allowed({'FLASK_ENV': 'production', 'SEED_ALLOW': '1'})


def test_seed_allow_cannot_bypass_unset_env():
    with pytest.raises(SeedRefused, match='SEED_ALLOW cannot override this'):
        assert_seed_allowed({'SEED_ALLOW': '1'})


def test_no_hardcoded_passwords_in_seed_source():
    assert re.search(r"generate_password_hash\(\s*['\"]", SEED_SOURCE) is None
    assert ANGEL_PASSWORD_ENV_PRESENT()
    assert 'SEED_PASSWORD_MITCHELLE' in SEED_SOURCE


def ANGEL_PASSWORD_ENV_PRESENT():
    return 'SEED_PASSWORD_ANGEL' in SEED_SOURCE


def test_demo_identities_preserved():
    assert ANGEL_USERNAME == 'Angel'
    assert ANGEL_EMAIL == 'angel@example.com'
    assert MITCHELLE_USERNAME == 'Mitchelle'
    assert MITCHELLE_EMAIL == 'mitchelle@example.com'
    assert ANGEL_EMAIL in SEED_SOURCE
    assert MITCHELLE_EMAIL in SEED_SOURCE


def test_supplied_password_is_hashed_with_scrypt():
    plain = 'supplied-dev-password-for-tests'
    hashed = hash_seed_password(plain)
    assert hashed.startswith('scrypt:')
    assert plain not in hashed
    assert check_password_hash(hashed, plain)


def test_generated_password_is_hashed_with_scrypt():
    plain, generated = resolve_seed_password('SEED_PASSWORD_ANGEL', {})
    assert generated is True
    assert len(plain) >= 16
    hashed = hash_seed_password(plain)
    assert hashed.startswith('scrypt:')
    assert check_password_hash(hashed, plain)


def test_supplied_env_password_is_not_generated():
    plain, generated = resolve_seed_password(
        'SEED_PASSWORD_ANGEL',
        {'SEED_PASSWORD_ANGEL': 'from-env-only'},
    )
    assert generated is False
    assert plain == 'from-env-only'


def _run_seed(db_path, extra_env=None):
    env = os.environ.copy()
    env['FLASK_ENV'] = 'development'
    env['JWT_SECRET_KEY'] = 'a' * 32
    env['DATABASE_URL'] = f'sqlite:///{db_path}'
    env['PYTHONPATH'] = str(BACKEND_DIR)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(BACKEND_DIR / 'seed.py')],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _user_password_hash(db_path, email):
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            'SELECT password FROM users WHERE email = ?', (email,)
        ).fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def test_subprocess_rejects_production_seed(tmp_path):
    db_path = tmp_path / 'prod.db'
    env = os.environ.copy()
    env['FLASK_ENV'] = 'production'
    env['SEED_ALLOW'] = '1'
    env['JWT_SECRET_KEY'] = 'a' * 32
    env['DATABASE_URL'] = f'sqlite:///{db_path}'
    env['PYTHONPATH'] = str(BACKEND_DIR)
    result = subprocess.run(
        [sys.executable, str(BACKEND_DIR / 'seed.py')],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert 'production' in (result.stderr + result.stdout).lower()


def test_development_seed_hashes_supplied_passwords_and_keeps_identities(tmp_path):
    db_path = tmp_path / 'dev.db'
    angel_pw = 'test-only-angel-password'
    mitchelle_pw = 'test-only-mitchelle-password'
    result = _run_seed(db_path, {
        'SEED_PASSWORD_ANGEL': angel_pw,
        'SEED_PASSWORD_MITCHELLE': mitchelle_pw,
    })
    assert result.returncode == 0, result.stderr
    assert ANGEL_USERNAME in result.stdout
    assert MITCHELLE_USERNAME in result.stdout

    conn = sqlite3.connect(db_path)
    try:
        users = conn.execute('SELECT username, email, password FROM users').fetchall()
        products = conn.execute('SELECT COUNT(*) FROM products').fetchone()[0]
    finally:
        conn.close()

    emails = {row[1]: row for row in users}
    assert ANGEL_EMAIL in emails
    assert MITCHELLE_EMAIL in emails
    assert emails[ANGEL_EMAIL][0] == ANGEL_USERNAME
    assert emails[MITCHELLE_EMAIL][0] == MITCHELLE_USERNAME
    assert emails[ANGEL_EMAIL][2].startswith('scrypt:')
    assert check_password_hash(emails[ANGEL_EMAIL][2], angel_pw)
    assert check_password_hash(emails[MITCHELLE_EMAIL][2], mitchelle_pw)
    assert products == 16


def test_existing_demo_user_password_is_not_changed(tmp_path):
    db_path = tmp_path / 'dev.db'
    first = _run_seed(db_path, {
        'SEED_PASSWORD_ANGEL': 'first-angel-password',
        'SEED_PASSWORD_MITCHELLE': 'first-mitchelle-password',
    })
    assert first.returncode == 0, first.stderr
    original_hash = _user_password_hash(db_path, ANGEL_EMAIL)

    second = _run_seed(db_path, {
        'SEED_PASSWORD_ANGEL': 'second-angel-password',
        'SEED_PASSWORD_MITCHELLE': 'second-mitchelle-password',
    })
    assert second.returncode == 0, second.stderr
    assert 'already exists' in second.stdout
    assert _user_password_hash(db_path, ANGEL_EMAIL) == original_hash
    assert check_password_hash(original_hash, 'first-angel-password')
