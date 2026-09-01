# e-commerce-Backend

## Environment

Copy `.env.example` to `.env` and set secrets. The API will not start without `JWT_SECRET_KEY`.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `JWT_SECRET_KEY` | Yes | none | Signs access tokens. Use a long random value. Production requires 32+ characters. Placeholder values are rejected. |
| `SECRET_KEY` | No | same as `JWT_SECRET_KEY` | Flask session signing. |
| `FLASK_ENV` | No | treated as production if unset | `development` required for `seed.py` and relaxes JWT secret length. Unset/`production` is fail-closed. |
| `SEED_PASSWORD_ANGEL` | No | generated if unset | Local seed password for `Angel`. Never commit a real value. |
| `SEED_PASSWORD_MITCHELLE` | No | generated if unset | Local seed password for `Mitchelle`. Never commit a real value. |
| `DATABASE_URL` | No | `sqlite:///../instance/products.db` | SQLAlchemy database URI. |
| `FLASK_DEBUG` | No | `0` | Set to `1` only for local debugging. |
| `FLASK_HOST` | No | `127.0.0.1` | Dev server bind address. |
| `FLASK_PORT` | No | `5000` | Dev server port. |

From `python/`:

```bash
export FLASK_APP=app.py
flask db upgrade
# Seed is local-only. It refuses to run unless FLASK_ENV=development.
FLASK_ENV=development python seed.py
python app.py
```

`seed.py` does not run at app startup or during `flask db upgrade`. If `SEED_PASSWORD_ANGEL` / `SEED_PASSWORD_MITCHELLE` are unset, it generates random passwords and prints them once. Re-running seed does not change existing users or wipe products. `SEED_ALLOW=1` cannot enable seeding in production.
