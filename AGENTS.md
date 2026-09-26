# AGENTS.md — Kairo contributor guide

> Canonical assistant behavior lives in `CLAUDE.md` and applies to all agents
> working in this repo (Claude, Codex, Opencode, etc.). This file adds project
> scope, repo facts, and run instructions. On conflict, `CLAUDE.md` wins for
> behavior; this file wins for repo facts.

## 1. What Kairo is

AI assistant that remembers your anime taste. ChatGPT-style chat UI + AniList
integration + anime-specific memory. Product value is `user context + LLM
reasoning`, not a recommendation engine.

Message flow (no agent loop, no tools): validate/auth/load → conditional
extraction gate (cheap heuristic, skip general chat) → ≤2 bounded AniList
lookups → bounded context builder (system + taste_profile + list slice +
lookups + date/season + last N messages, token-budget trimmed) → streaming SSE
(`delta | anime_card | done | error`) → persist both messages + `context_used`.

Locked v1 constraints (from `docs/plan.md`):
- single FastAPI service + single Postgres 16. No worker, no microservices.
- sync runs as in-process asyncio task with `sync_jobs` state + stale reaper.
- rate limiter is in-process token bucket → **single uvicorn worker only**.
- Postgres-only schema (`UUID`, `ARRAY`, `JSONB`). No SQLite fallback.
- server sessions (httponly `kairo_session` cookie), no JWT. Fernet-encrypted
  AniList token, expiry-aware with `anilist_connected=false` reconnect UX.
- v1 LLM providers: `openrouter` + `ollama` only. `openai`/`anthropic` raise
  `LLMError` (deferred v2, OpenRouter already proxies those models).
- no vector DB, no agent loop, no web search, no public `/anime/*` endpoints.

## 2. Repo layout

```
backend/            FastAPI + SQLAlchemy async + Alembic (app/, alembic/, tests/)
  app/routers/      auth.py, profile.py, conversations.py
  app/services/     auth, anilist, sync, taste, context_builder, chat, conversation
  app/llm/          base.py, factory.py, openrouter.py, ollama.py
  app/prompts/      system.py, entity_extraction.py, taste_extraction.py
  app/middleware/   rate_limit.py (in-process, single-worker)
frontend/           Next.js 16.2.9 + React 19 + TS + Tailwind v4 (app/ router)
  app/login, app/chat, app/chat/[id]   lib/api.ts, lib/stream.ts
docs/               plan.md (architecture), todo.md (checklist), kairo-prompt-guide.md, plans/
docker-compose.yml      dev: db (host 5433) + backend (:8000), manual migrate
docker-compose.prod.yml prod: no exposed db ports, auto-migrate, --workers 1
```

Full architecture: `docs/plan.md`. Task checklist: `docs/todo.md`.
Feature pipeline: `plans/next-features.md`, `plans/recommendation-retrieval.md`.

## 3. Run instructions

### Docker dev (primary path)

```sh
cp backend/.env.example backend/.env   # POSIX
# Copy-Item backend/.env.example backend/.env   # PowerShell
# fill FERNET_KEY, SESSION_SECRET, ANILIST_*, LLM_*
docker compose up --build
docker compose exec backend alembic upgrade head   # first boot only (no auto-migrate in dev)
# health: http://localhost:8000/health ; frontend: cd frontend && npm install && npm run dev
```

### Local run without Docker (Windows, no docker/psql preinstalled)

1. Install Postgres 16 natively, create user/db `kairo`.
2. `DATABASE_URL=postgresql+asyncpg://kairo:kairo@localhost:5432/kairo`
   (Docker value `@db:5432` does not resolve outside compose).
3. `cd backend && py -m venv .venv && .venv\Scripts\activate &&
   pip install -e .[dev] && alembic upgrade head &&
   uvicorn app.main:app --port 8000`.
4. `cd frontend && npm install && npm run dev` (`NEXT_PUBLIC_API_BASE_URL`
   defaults to `http://localhost:8000`; build-time var, rebuild on change).

### Prod

`docker compose -f docker-compose.prod.yml up -d --build` (auto-migrates,
forces `ENVIRONMENT=production`, hides `/docs`). Set `FRONTEND_ORIGIN` to the
frontend domain first; point proxy at `localhost:8000`.

### Tests (31, isolated DB)

```sh
docker run -d --name kairo-testpg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=kairo_test -p 5434:5432 postgres:16
export TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5434/kairo_test
pytest   # from backend/ ; refuses :5433 dev db by design
```

Lint: `ruff check backend` (line-length 100). Frontend: `npm run lint`, `tsc --noEmit`.

## 4. Env reference

Backend: see `backend/.env.example` (48 keys). Required fail-loud:
`DATABASE_URL, FERNET_KEY, SESSION_SECRET, ANILIST_CLIENT_ID/SECRET/REDIRECT_URI`.
Tunable: `LLM_PROVIDER/MODEL/EXTRACTION_MODEL, OLLAMA_BASE_URL,
MAX_CONTEXT_TOKENS=8000, HISTORY_MESSAGE_LIMIT=20, MAX_USER_MESSAGE_CHARS=2000,
SYNC_STALE_SECONDS=600, RATE_LIMIT_* (10/20/1), FRONTEND_ORIGIN`.
Frontend: `NEXT_PUBLIC_API_BASE_URL` (no `.env.example` yet, see issue #21).

Secrets: `backend/.env` and `frontend/.env.local` are gitignored. Never commit
real values. Rotate moved keys if ever exposed (issue #4).

## 5. Assistant behavior (from CLAUDE.md, applies here)

Priorities: correctness > security > maintainability > operational simplicity >
performance > style. Lead with the answer; bullets over paragraphs; list
assumptions; separate facts/assumptions/opinions. Compare ≥2 approaches for
architecture calls. Push back on bad code and security flaws.

Coding: production quality, modular, typed, no magic values, no hidden state,
fail loud, explicit errors, validate inputs, sanitize external data (AniList +
LLM output are untrusted: delimited blocks only, pydantic-validate structured
output), minimize deps, explain non-obvious calls, flag new tech debt.

Before answering: check contradictions, security, edge cases, simpler
alternatives, whether it solves the problem. For code: flag bugs, perf, and
maintainability proactively. Keep it terse; no filler.

## 6. Workflow

- Minimum code that solves the problem; touch only what the task requires.
- Work issue-by-issue via GitHub issues; commit after each task.
- Backend changes need migration when models change; frontend changes need
  `tsc` + lint clean; user-scoped queries always (`WHERE user_id = session`).
- Open questions go at the end of plans as an unresolved list.
