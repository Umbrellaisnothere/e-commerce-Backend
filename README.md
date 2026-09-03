# e-commerce-Backend

## Environment

Copy `.env.example` to `.env` and set secrets. The API will not start without `JWT_SECRET_KEY` and `CORS_ORIGINS`.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `JWT_SECRET_KEY` | Yes | none | Signs access tokens. Use a long random value. Production requires 32+ characters. Placeholder values are rejected. |
| `SECRET_KEY` | No | same as `JWT_SECRET_KEY` | Flask session signing. |
| `CORS_ORIGINS` | Yes | none | Comma-separated frontend origins allowed by CORS. Must include scheme and host (and port if not default). Do not include a trailing `/`. `*` is not permitted. Missing/blank values fail closed in development and production; there is no localhost fallback. |
| `FLASK_ENV` | No | treated as production if unset | `development` required for `seed.py` and relaxes JWT secret length. Unset/`production` is fail-closed. |
| `SEED_PASSWORD_ANGEL` | No | generated if unset | Local seed password for `Angel`. Never commit a real value. |
| `SEED_PASSWORD_MITCHELLE` | No | generated if unset | Local seed password for `Mitchelle`. Never commit a real value. |
| `DATABASE_URL` | No | `sqlite:///../instance/products.db` | SQLAlchemy database URI. |
| `FLASK_DEBUG` | No | `0` | Set to `1` only for local debugging. |
| `FLASK_HOST` | No | `127.0.0.1` | Dev server bind address. |
| `FLASK_PORT` | No | `5000` | Dev server port. |

### CORS origins

`CORS_ORIGINS` is an explicit allowlist. Browser requests from any other origin are not granted CORS access. Vercel preview deployments (`https://*.vercel.app`) are not automatically allowed.

Development:

```text
CORS_ORIGINS=http://localhost:3000
```

Production:

```text
CORS_ORIGINS=https://e-commerce-chi-one-94.vercel.app,https://e-commerce-va1l.vercel.app
```

Do not use `http://localhost:5173` or `http://127.0.0.1:3000` unless that origin is later added on purpose. JWT remains `Authorization: Bearer`; `Access-Control-Allow-Credentials` is not enabled.

### Rate limiting

Unauthenticated login and registration are rate limited in memory (single-process). Limits use `request.remote_addr` only; forwarding headers are not trusted.

* `POST /login`: 10 requests per minute per IP, and 10 requests per minute per normalized username (stripped, lowercased). All attempts count, including failures.
* `POST /register` and `POST /api/users`: 5 requests per hour per IP, shared across both routes.

Exceeding a limit returns HTTP `429` with `{"error": "Too many requests"}`. Other routes are not rate limited.

From `python/`:

```bash
export FLASK_APP=app.py
flask db upgrade
# Seed is local-only. It refuses to run unless FLASK_ENV=development.
FLASK_ENV=development python seed.py
python app.py
```

`seed.py` does not run at app startup or during `flask db upgrade`. If `SEED_PASSWORD_ANGEL` / `SEED_PASSWORD_MITCHELLE` are unset, it generates random passwords and prints them once. Re-running seed does not change existing users or wipe products. `SEED_ALLOW=1` cannot enable seeding in production.
