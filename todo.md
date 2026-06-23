# kairo mvp v1 - todo

phased implementation checklist. see `plan.md` for architecture rationale.

---

## phase 0 - project scaffolding  [done]

- [x] repo layout (`frontend/`, `backend/`), `.gitignore`, `README.md` stub
- [x] `docker-compose.yml` (fastapi + postgres 16; db published on host 5433 to avoid
      native pg on 5432)
- [x] backend `pyproject.toml` deps: fastapi, uvicorn, sqlalchemy[asyncio], asyncpg,
      alembic, pydantic-settings, httpx, cryptography, tiktoken (+ dev: pytest, ruff)
- [x] `config.py` pydantic-settings (fail-loud on missing secrets), `.env.example`
- [x] `database.py` async engine/session, `main.py` app factory + `GET /health` (verified 200)
- [x] alembic init + async env.py (connects, exit 0). base migration deferred to phase 1
      (needs models for autogenerate)
- [x] frontend: next.js 16 + typescript + tailwind init (deps installed in phase 1/3)

---

## phase 1 - auth + sessions

- [ ] db models + migration: `users` (incl. `anilist_connected`, `revoked_at`),
      `sessions` (incl. `last_used_at`)
- [ ] Fernet encrypt/decrypt helper for AniList token (`FERNET_KEY`)
- [ ] `auth_service`: state generation, code exchange, user upsert (resets
      `anilist_connected=true` on reconnect), session create/delete
- [ ] `GET /auth/anilist/login` (random state in httponly cookie)
- [ ] `GET /auth/anilist/callback` (validate+consume state, exchange code, upsert, set session)
- [ ] `POST /auth/logout`, `GET /auth/me` (returns `anilist_connected`, `last_synced_at`)
- [ ] `current_user` dependency: load session, check expiry, bump `last_used_at`
- [ ] AniList-call guard: pre-call expiry check + 401 handling -> set
      `anilist_connected=false` + `revoked_at`, abort cleanly (no silent sync failure)
- [ ] frontend: login page -> AniList -> callback -> redirect to `/chat`;
      reconnect banner when `anilist_connected=false`

---

## phase 2 - profile sync + taste

- [ ] db models + migration: `anilist_profiles`, `user_anime_list` (denormalized
      title+genres), `taste_profiles` (incl. `input_hash`), `sync_jobs`
- [ ] AniList graphql client (httpx, rate-limited, typed responses, unknown fields dropped)
- [ ] `sync_service`: in-process asyncio task, idempotent upserts, job state transitions
- [ ] sync recovery: startup + on-request stale-job reaper (`SYNC_STALE_SECONDS`),
      dedupe active jobs (return existing job instead of starting duplicate)
- [ ] `POST /profile/sync` -> `{job_id}`; `GET /profile/sync/{job_id}`
- [ ] `taste_service`: compute `input_hash`, skip-if-unchanged, llm generation,
      pydantic schema validation, persist
- [ ] `GET /profile/taste`, `GET /profile/anime-list`
- [ ] frontend: post-login sync trigger + progress polling state
- [ ] frontend: sync-freshness indicator ("synced 2 hours ago" + [Sync now] button)
      driven by `last_synced_at` from `/auth/me`

---

## phase 3 - llm abstraction + chat

- [ ] `llm/base.py` ABC (`chat` + `stream`, optional `response_schema`) + Message/ChatResponse
- [ ] providers: `openrouter` (default), `openai`, `anthropic`, `ollama`
- [ ] `factory` from `LLM_PROVIDER`; `LLM_MODEL` + `LLM_EXTRACTION_MODEL` read from env
      (no models hardcoded; `.env.example` ships empty with class-guidance comments)
- [ ] prompts: `system`, `taste_extraction`, `entity_extraction`
- [ ] db models + migration: `conversations` (incl. `summary`), `messages`
- [ ] `conversation_service` + CRUD: `POST/GET/GET{id}/DELETE /conversations` (ownership-checked)
- [ ] `context_builder`: bounded list slice + taste + dates + last N msgs, TOKEN-BUDGET
      cap with trim order (oldest history -> dropped -> recent -> top)
- [ ] `chat_service`: heuristic gate -> conditional extraction -> optional AniList lookup
      (<=2 queries) -> assemble -> stream
- [ ] `POST /conversations/{id}/messages` SSE (`delta | anime_card | done | error`)
- [ ] persist user + assistant message (+ `context_used` debug snapshot)
- [ ] frontend: chat ui, `streaming-message`, `message-input`, markdown render,
      `anime-card`, `source-card`, `conversation-list` sidebar

---

## phase 4 - hardening + ship

- [ ] `rate_limit` middleware (auth 10/min/ip, chat 20/min/user, sync 1/min/user)
- [ ] input validation pass (2000-char message cap, uuid validation, pydantic constraints)
- [ ] structured logging + global error handler + error monitoring hook
- [ ] end-to-end reconnect UX verification (expiry/401 -> `anilist_connected=false` ->
      banner -> re-login resets flag) - core logic lives in phase 1 guard
- [ ] docker production config, README self-host setup, finalize `.env.example`
- [ ] tests:
  - [ ] oauth callback (state validation, token encryption)
  - [ ] taste schema validation + `input_hash` skip-on-unchanged
  - [ ] context token-budget bound (large list/conversation stays under cap)
  - [ ] user data isolation (cross-user read returns 403/404)
  - [ ] sync recovery (stale job reaped, retryable)
  - [ ] provider swap (ollama) smoke
