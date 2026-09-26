# Kairo backend

FastAPI + SQLAlchemy 2.0 async + asyncpg + Alembic API for Kairo: AniList OAuth,
list sync + taste profiling, token-budgeted streaming chat. Postgres 16 only
(`UUID`, `ARRAY`, `JSONB` — no SQLite fallback). Single uvicorn worker
(`--workers 1` pinned in `Dockerfile`; rate-limit buckets are in-process).

## Layout

- `app/routers/` — `auth.py`, `profile.py`, `conversations.py`
- `app/services/` — auth, anilist (GraphQL), sync (in-process jobs), taste, context_builder, chat, conversation
- `app/llm/` — `base.py`, `factory.py`, `openrouter.py`, `ollama.py` (v1: `openrouter` + `ollama` only)
- `app/prompts/`, `app/middleware/rate_limit.py`, `app/models/`
- `alembic/` migrations, `tests/` pytest suite, `.env.example` (all keys)

## Setup

```sh
cp .env.example .env   # POSIX
# PowerShell: Copy-Item .env.example .env
```

Fill `FERNET_KEY`, `SESSION_SECRET` (generate, see root `README.md`),
`ANILIST_CLIENT_ID/SECRET`, `LLM_API_KEY`/`LLM_MODEL`. All other keys are
optional and default to the values shown in `.env.example` when unset.
`DATABASE_URL` uses host `db` inside compose; use `@localhost:5432` (or `:5433`
for the compose-mapped port) when running natively.

## Run

```sh
# Docker dev (from repo root): docker compose up --build, then first boot only:
docker compose exec backend alembic upgrade head

# Native (Python 3.11+):
py -m venv .venv && .venv\Scripts\activate
pip install -e .[dev]
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000   # health: /health, docs: /docs (dev)
```

## Tests (31, isolated throwaway DB — never the dev DB)

```sh
docker run -d --name kairo-testpg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=kairo_test -p 5434:5432 postgres:16
# PowerShell: $env:TEST_DATABASE_URL="postgresql+asyncpg://test:test@localhost:5434/kairo_test"
# POSIX:      export TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5434/kairo_test
pytest   # refuses :5433 by design
```

Lint: `ruff check .` (line-length 100).
