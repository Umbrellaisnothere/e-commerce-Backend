# e-commerce-Backend

## Environment

Copy `.env.example` to `.env` and set secrets. The API will not start without `JWT_SECRET_KEY`.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `JWT_SECRET_KEY` | Yes | none | Signs access tokens. Use a long random value. |
| `SECRET_KEY` | No | same as `JWT_SECRET_KEY` | Flask session signing. |
| `DATABASE_URL` | No | `sqlite:///../instance/products.db` | SQLAlchemy database URI. |
| `FLASK_DEBUG` | No | `0` | Set to `1` only for local debugging. |
| `FLASK_HOST` | No | `127.0.0.1` | Dev server bind address. |
| `FLASK_PORT` | No | `5000` | Dev server port. |

From `python/`:

```bash
export FLASK_APP=app.py
flask db upgrade
python seed.py   # safe to re-run; does not drop existing tables or products
python app.py
```
