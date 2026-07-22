# Migrations - Actual Location

Alembic migrations for api_gateway's models live at
`backend/api_gateway/migrations/`, not here.

Why: Alembic's `env.py` needs to import `app.models` and `app.core.database`
directly to autogenerate migrations from the SQLAlchemy models - that only
works cleanly when Alembic is co-located with the app package that owns
those models, given how Python resolves imports. This folder is kept as a
pointer since the original Phase 1 folder plan placed migrations here.

Run migrations from `backend/api_gateway/`:
```bash
alembic upgrade head
alembic revision --autogenerate -m "description"
```
