# Kairo

An AI assistant that remembers your anime taste.

ChatGPT-style chat UI + AniList integration + anime-specific memory. The product
value is `your context + LLM reasoning`, not a recommendation engine: Kairo
syncs your AniList list, distills a taste profile, and injects bounded personal
context into every chat response, with streaming answers and inline anime cards.

## Features

- **AniList OAuth login** — 302 login flow with state cookie, Fernet-encrypted
  token at rest, expiry-aware `anilist_connected` flag + reconnect banner.
- **List sync + taste profile** — async `POST /profile/sync` job (in-process
  asyncio, idempotent upserts, stale-job reaper, active-job dedupe), LLM
  taste generation with `input_hash` skip-if-unchanged, `GET /profile/taste`
  and `GET /profile/anime-list` reads, sync-freshness UI ("synced X ago").
- **Context-aware streaming chat** — conditional extraction gate (skips general
  chat), ≤2 bounded AniList lookups per message, token-budgeted context
  builder (taste + top-30/recent-20/dropped-15 list slice + lookups +
  date/season + last 20 messages), SSE stream
  (`delta | anime_card | done | error`), user + assistant persisted with a
  `context_used` debug snapshot.
- **Conversations** — create/list (keyset cursor)/detail/delete with strict
  ownership checks, markdown assistant rendering, collapsible sidebar,
  `Ctrl/Cmd+B` toggle, anime cards with cover fallback.
- **Hardening** — in-process token-bucket rate limits (auth 10 / chat 20 /
  sync 1 per min, **single worker only**), 2000-char message cap, structured
  JSON logs with request IDs (`X-Request-ID`), global 500 envelope.

## Architecture

```
[Next.js frontend :3000] --HTTPS/SSE--> [FastAPI :8000] --+-- Postgres 16
                                                          +-- AniList GraphQL
                                                          +-- LLM (openrouter | ollama)
```

Per-message flow: validate + auth + load → conditional extraction pre-step →
optional AniList lookup (≤2 queries) → assemble bounded context → stream answer
→ persist. No agent loop, no tool registry, no vector DB, no worker process.
Details: [`docs/plan.md`](docs/plan.md).

## Stack

| Layer    | Tech (pinned)                                              |
| -------- | ---------------------------------------------------------- |
| Backend  | Python 3.11+, FastAPI 0.115.6, SQLAlchemy 2.0 async, asyncpg, Alembic, pydantic-settings, httpx, cryptography (Fernet), tiktoken |
| DB       | Postgres 16 — required (`UUID`, `ARRAY`, `JSONB`); no SQLite fallback |
| Frontend | Next.js 16.2.9, React 19, TypeScript 5, Tailwind v4, react-markdown + remark-gfm |
| LLM (v1) | `openrouter` (default) + `ollama`; `openai`/`anthropic` deferred to v2 and raise `LLMError` |
| Dev      | pytest 8.3.4 + pytest-asyncio (31 tests, isolated DB), ruff 0.8.4, eslint 9 |

## Repo layout

```
backend/                  FastAPI service (app/, alembic/, tests/, pyproject.toml)
  app/routers/            auth.py, profile.py, conversations.py
  app/services/           auth, anilist, sync, taste, context_builder, chat, conversation
  app/llm/                base.py, factory.py, openrouter.py, ollama.py
  app/prompts/            system.py, entity_extraction.py, taste_extraction.py
  app/middleware/         rate_limit.py
frontend/                 Next.js app (app/login, app/chat, app/chat/[id], lib/, components/)
docs/                     plan.md, todo.md, kairo-prompt-guide.md, plans/
plans/                    next-features.md, recommendation-retrieval.md
docker-compose.yml        dev: db (host 5433) + backend (:8000), manual migrate
docker-compose.prod.yml   prod: hidden db, auto-migrate, --workers 1
AGENTS.md / CLAUDE.md     contributor + assistant behavior guides
```

## Prerequisites

- Docker + Python 3.11+ + Node 20+ (Docker path), **or** native Postgres 16 +
  Python + Node (no-Docker path below).
- An AniList API client from https://anilist.co/settings/developer (redirect URI
  must match `ANILIST_REDIRECT_URI`).
- An LLM key: OpenRouter by default, or a local Ollama at `OLLAMA_BASE_URL`.

## Quickstart — Docker dev

```sh
cp backend/.env.example backend/.env
# PowerShell: Copy-Item backend/.env.example backend/.env
```

Generate secrets and fill `.env` (commands work in Git Bash/macOS/Linux;
CMD and PowerShell variants below):

```sh
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # SESSION_SECRET
```

```powershell
# PowerShell (py launcher; quoting is safe here: no nested quotes inside)
py -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
py -c "import secrets; print(secrets.token_urlsafe(32))"
# CMD: same two lines with python instead of py
```

Set `ANILIST_CLIENT_ID` / `ANILIST_CLIENT_SECRET` / `ANILIST_REDIRECT_URI`
(default `http://localhost:8000/auth/anilist/callback`), plus `LLM_API_KEY`
and `LLM_MODEL` (e.g. `anthropic/claude-3.5-sonnet` via OpenRouter).

```sh
docker compose up --build
docker compose exec backend alembic upgrade head   # first boot only
```

- API health: http://localhost:8000/health — interactive docs: `/docs` (dev only).
- Frontend (separate terminal, not in compose):
  `cd frontend && npm install && npm run dev` → http://localhost:3000.
- Login at `/login` → Connect AniList → land in `/chat` → Sync → ask
  "why would i like Frieren?" (lookup path) vs "recommend from my taste"
  (gate-skipped path).

## Run without Docker (native Postgres)

1. Install Postgres 16, create role/db `kairo` (password `kairo`).
2. Point `.env` at localhost — the shipped `@db:5432` hostname only resolves
   inside compose:
   `DATABASE_URL=postgresql+asyncpg://kairo:kairo@localhost:5432/kairo`.
3. Backend:
   ```sh
   cd backend && py -m venv .venv && .venv\Scripts\activate
   pip install -e .[dev] && alembic upgrade head
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
4. Frontend: `cd frontend && npm install && npm run dev`.
   `NEXT_PUBLIC_API_BASE_URL` defaults to `http://localhost:8000` (build-time
   var — rebuild after changing it). Ensure it matches backend `FRONTEND_ORIGIN`
   (`http://localhost:3000` default) or cookies/CORS break.

## Production deploy

```sh
cp backend/.env.example backend/.env   # then fill secrets, set ENVIRONMENT=production
# PowerShell: Copy-Item backend/.env.example backend/.env
docker compose -f docker-compose.prod.yml up -d --build
curl http://localhost:8000/health
```

Notes: migrations run automatically; single worker enforced (in-process rate
buckets); `/docs` and `/openapi.json` hidden; set `FRONTEND_ORIGIN` to the real
frontend domain and proxy it to `localhost:8000` (nginx/Caddy, HTTPS required
for `Secure` cookies). Frontend needs its own host: build with the prod
`NEXT_PUBLIC_API_BASE_URL` (see issue #21).

## Configuration

Backend env: [`backend/.env.example`](backend/.env.example) (all keys, fail-loud
on missing secrets). Only `FERNET_KEY`, `SESSION_SECRET`, `ANILIST_CLIENT_ID`,
`ANILIST_CLIENT_SECRET`, `DATABASE_URL`, and the LLM keys are required; every
other key falls back to the default shown in the example when unset, so a local
`.env` omitting them is intentional, not drift. Key groups: core (`ENVIRONMENT`, `DATABASE_URL`,
`LOG_LEVEL`), secrets (`FERNET_KEY`, `SESSION_SECRET`), session TTL,
AniList OAuth + API URLs, LLM (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`,
`LLM_EXTRACTION_MODEL`, `OLLAMA_BASE_URL`), context budgets
(`MAX_CONTEXT_TOKENS=8000`, `HISTORY_MESSAGE_LIMIT=20`,
`MAX_USER_MESSAGE_CHARS=2000`), sync (`SYNC_STALE_SECONDS=600`), rate limits
(`RATE_LIMIT_ENABLED`, auth/chat/sync per-min), CORS (`FRONTEND_ORIGIN`).
Frontend: `NEXT_PUBLIC_API_BASE_URL` only. `.env` files are gitignored — never
commit real values.

## API reference

| Method | Route | Auth | Notes |
| ------ | ----- | ---- | ----- |
| GET | `/health` | no | `{status: ok}` + `X-Request-ID` |
| GET | `/auth/anilist/login` | no | 302 to AniList, state cookie |
| GET | `/auth/anilist/callback` | no | validates state, upserts user, sets session, 302 to `${FRONTEND_ORIGIN}/chat` |
| POST | `/auth/logout` | cookie | deletes session |
| GET | `/auth/me` | cookie | `{id, username, anilist_id, anilist_connected, last_synced_at}` (401 logged out) |
| POST | `/profile/sync` | cookie | spawns job → `{job_id}` (202); dedupes active job |
| GET | `/profile/sync/{job_id}` | cookie | `{status: pending\|running\|completed\|failed, error?}` |
| GET | `/profile/taste` | cookie | taste profile JSON (null before first sync) |
| GET | `/profile/anime-list?status=&limit=&offset=` | cookie | denormalized slice |
| POST | `/conversations` | cookie | `{id, title, created_at}` |
| GET | `/conversations?cursor=` | cookie | `{items, next_cursor}` keyset page |
| GET | `/conversations/{id}` | cookie | conversation + last 50 messages (403/404 isolated) |
| DELETE | `/conversations/{id}` | cookie | 204 |
| POST | `/conversations/{id}/messages` | cookie | SSE `text/event-stream`, body `{content}` ≤2000 chars |

SSE events: `data: {"type":"delta","content":"..."}`,
`{"type":"anime_card","anime":{title, genres, score, cover_image, year}}`,
`{"type":"done"}`, `{"type":"error","message":"..."}`. Client reader:
`frontend/lib/stream.ts`.

## Testing

Isolated throwaway Postgres (never the dev db — `:5433` refused by design):

```sh
docker run -d --name kairo-testpg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test \
  -e POSTGRES_DB=kairo_test -p 5434:5432 postgres:16
export TEST_DATABASE_URL=postgresql+asyncpg://test:test@localhost:5434/kairo_test
cd backend && pytest
```

Harness (`tests/conftest.py`): copies `TEST_DATABASE_URL` → `DATABASE_URL`
pre-import, rebinds engine to `NullPool`, runs `alembic upgrade head` once,
`TRUNCATE … CASCADE` per test. 31 tests: harness smoke, OAuth callback,
sync recovery, provider/taste, context budget, cross-user isolation.
Lint: `ruff check backend`; frontend `npm run lint`, `tsc --noEmit`.

## Security model

OAuth state: 32-byte random httponly `SameSite=Lax` cookie, consumed once.
Sessions: server-side UUID cookie, 30-day sliding expiry, revocation = row
delete. AniList token Fernet-encrypted, expiry pre-checked + 401 → disconnect
flag (no silent failures, no refresh flow). All data queries user-scoped from
session. AniList/LLM output treated untrusted (delimited blocks, pydantic
validation, markdown-only render, cards from validated AniList data only).
Rate limits in-process (see single-worker rule). Secrets via env only.

## Troubleshooting

- **Backend can't reach DB locally** → `.env` still points at `@db:5432`;
  switch to `@localhost:5432` (or `:5433` for compose-mapped host).
- **First boot 500s** → run `alembic upgrade head`; dev compose does not
  auto-migrate (prod does).
- **Login lands but chat redirects to /login** → backend down (guard treats any
  fetch failure as unauth) — check `:8000/health` first.
- **LLM errors** → v1 supports `openrouter`/`ollama` only; `openai`/`anthropic`
  raise by design; verify `LLM_MODEL` is a real OpenRouter model id.
- **Ollama refused in Docker** → `localhost:11434` inside container ≠ host;
  override with `host.docker.internal`.
- **Cookie/CORS failures in prod** → `FRONTEND_ORIGIN` and
  `NEXT_PUBLIC_API_BASE_URL` must match (rebuild frontend after change), HTTPS
  on for `Secure` cookies.
- Full known-issue list (24): https://github.com/knightlesssword/kairo/issues.

## Status & roadmap

Phase 4 done: auth, sync, taste, streaming chat, logging, rate limiting,
openrouter/ollama abstraction, 31 green tests. Open hardening: prod packaging
docs, prompt audit (see [`docs/todo.md`](docs/todo.md)). Next: LLM titles,
taste page, card links, deterministic retrieval Plan A, AniList write-back —
see [`plans/next-features.md`](plans/next-features.md) and
[`plans/recommendation-retrieval.md`](plans/recommendation-retrieval.md).

## Docs index

- [`docs/plan.md`](docs/plan.md) — architecture, schema, routes, security, risks.
- [`docs/todo.md`](docs/todo.md) — phased checklist with done criteria.
- [`docs/kairo-prompt-guide.md`](docs/kairo-prompt-guide.md) — user prompt catalog.
- [`docs/plans/`](docs/plans/) — frontend redesign, SSE cover-image notes.
- [`AGENTS.md`](AGENTS.md) / [`CLAUDE.md`](CLAUDE.md) — contributor + assistant rules.
