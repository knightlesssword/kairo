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

## phase 1 - auth + sessions  [done]

- [x] db models + migration: `users` (incl. `anilist_connected`, `revoked_at`),
      `sessions` (incl. `last_used_at`)
- [x] Fernet encrypt/decrypt helper for AniList token (`FERNET_KEY`)
- [x] `auth_service`: state generation, code exchange, user upsert (resets
      `anilist_connected=true` on reconnect), session create/delete
- [x] `GET /auth/anilist/login` (random state in httponly cookie)
- [x] `GET /auth/anilist/callback` (validate+consume state, exchange code, upsert, set session)
- [x] `POST /auth/logout`, `GET /auth/me` (returns `anilist_connected`, `last_synced_at`)
- [x] `current_user` dependency: load session, check expiry, bump `last_used_at`
- [x] AniList-call guard: pre-call expiry check + 401 handling -> set
      `anilist_connected=false` + `revoked_at`, abort cleanly (no silent sync failure)
- [x] frontend: login page -> AniList -> callback -> redirect to `/chat`;
      reconnect banner when `anilist_connected=false`

---

## phase 2 - profile sync + taste  [done]

- [x] db models + migration: `anilist_profiles`, `user_anime_list` (denormalized
      title+genres), `taste_profiles` (incl. `input_hash`), `sync_jobs`
- [x] AniList graphql client (httpx, typed responses, unknown fields dropped)
- [x] `sync_service`: in-process asyncio task, idempotent upserts, job state transitions
- [x] sync recovery: startup + on-request stale-job reaper (`SYNC_STALE_SECONDS`),
      dedupe active jobs (return existing job instead of starting duplicate)
- [x] `POST /profile/sync` -> `{job_id}`; `GET /profile/sync/{job_id}`
- [x] `taste_service`: compute `input_hash`, skip-if-unchanged, llm generation stubbed
      (NotImplementedError; soft failure in sync), pydantic schema validation, persist
- [x] `GET /profile/taste`, `GET /profile/anime-list`
- [x] frontend: post-login sync trigger + progress polling state
- [x] frontend: sync-freshness indicator ("synced X ago" + [Sync now] button)
      driven by `last_synced_at` from `/auth/me`
- note: AniList status values are COMPLETED|CURRENT|DROPPED|PLANNING|PAUSED|REPEATING
        (not WATCHING — corrected from plan.md)

---

## phase 3 - llm abstraction + chat

execution order: A (parallel) -> B (parallel) -> C -> D -> E -> F
success = streaming chat works end-to-end with taste context injected

### A - foundations (parallel, no deps)

- [x] **A1** `llm/base.py`: `Message(role, content)`, `ChatResponse(content, input_tokens,
      output_tokens)` pydantic models; `LLMProvider` ABC with `chat()` + `stream()`;
      `response_schema: dict | None` on `chat()` only.
      done when: ABC imports clean, mypy/pyright happy on the signatures.

- [x] **A2** `prompts/system.py`: static system prompt string (anime assistant persona,
      instructs model to use injected taste + list context, no tool calls, markdown ok).
      `prompts/taste_extraction.py`: user prompt template that takes compact list summary,
      instructs structured JSON output matching TasteProfileSchema.
      `prompts/entity_extraction.py`: user prompt that takes a raw user message, outputs
      `{anime_titles: list[str], wants_current_season: bool, intent: str}`.
      done when: all three are importable strings/callables, no placeholder text.

- [x] **A3** db models + migration: `Conversation(id, user_id, title, summary, created_at,
      updated_at)`, `Message(id, conversation_id, role, content, context_used jsonb,
      created_at)`. add indexes from plan.md (idx_messages_conversation,
      idx_conversations_user). register both in model registry (`models/db/__init__.py`).
      done when: `alembic revision --autogenerate` produces correct DDL; `alembic upgrade
      head` runs clean inside docker container.

### B - providers + service layer (parallel, after A)

- [x] **B1** `llm/openrouter.py`: implements `LLMProvider`. `chat()` -> POST
      `https://openrouter.ai/api/v1/chat/completions` with `response_format` when
      `response_schema` set. `stream()` -> same endpoint with `stream=true`, yields
      delta content strings. raises `LLMError` (define in base.py) on non-2xx.
      done when: smoke test with a real key returns a string.

- [ ] **B2** `llm/openai.py`: same interface, `https://api.openai.com/v1/chat/completions`.
      `llm/anthropic.py`: uses messages API + system param separately (Anthropic separates
      system from messages). `llm/ollama.py`: `{ollama_base_url}/api/chat`, stream via
      NDJSON. all raise `LLMError` on failure.
      done when: each file imports clean; only openrouter tested live (others structurally
      correct, tested in phase 4 provider-swap smoke).

- [ ] **B3** `llm/factory.py`: `get_llm_provider(settings) -> LLMProvider` selects impl
      from `settings.llm_provider`. answer model uses `settings.llm_model`, extraction
      model uses `settings.llm_extraction_model` (fallback to llm_model if blank).
      expose `get_answer_llm()` + `get_extraction_llm()` as dependency-injectable
      callables (or plain functions called from services).
      done when: switching `LLM_PROVIDER=openai` in `.env` returns openai impl.

- [x] **B4** wire taste_service LLM stub: replace `_call_llm()` `NotImplementedError`
      with real call using `get_extraction_llm().chat(messages, response_schema=...)`.
      fill `model` column with `settings.llm_extraction_model or settings.llm_model`.
      done when: POST /profile/sync completes with a non-null taste_profiles row and
      `profile` column matches TasteProfileSchema.

- [x] **B5** `services/conversation_service.py`: CRUD with ownership checks.
      - `create_conversation(user_id, db) -> Conversation` (title=None initially)
      - `list_conversations(user_id, limit, cursor, db) -> list[Conversation]`
        (cursor = last updated_at for keyset pagination)
      - `get_conversation(user_id, conv_id, db) -> Conversation` (404 if not found,
        403 if wrong user)
      - `delete_conversation(user_id, conv_id, db) -> None`
      - `append_message(conv_id, role, content, context_used, db) -> Message`
      - `get_history(conv_id, limit, db) -> list[Message]` (ordered asc by created_at)
      done when: unit-testable in isolation (just needs a db session).

### C - context builder (after A1, A3, B5)

- [x] **C1** `services/context_builder.py`: assembles bounded context dict.
      inputs: `user_id`, `conversation_id`, `db`, `settings`.
      steps:
      1. load taste_profile json (None -> omit block)
      2. load list slice: top 30 by score (COMPLETED), recent 20 (COMPLETED ordered
         updated_at desc), 15 DROPPED, aggregate counts per status
      3. load last N messages from history (N = settings.history_message_limit)
      4. token budget enforcement: estimate tokens (chars/4 heuristic; tiktoken optional
         import with fallback). trim in order: oldest history first, then DROPPED slice,
         then recent slice, then top slice. never trim taste_profile or system prompt.
      returns: `ContextBundle(system_prompt, taste_block, list_block, history,
               looked_up_anime, current_date, current_season, token_estimate)`.
      done when: with a 602-entry list and 20 messages, `token_estimate <=
      settings.max_context_tokens`.

### D - chat service (after B1-B4, C1, A2)

- [x] **D1** `services/chat_service.py`:
      heuristic gate: regex check on user message for quoted text, capitalized
      multi-word spans, "vs", "watch", "season", "airing" -> bool `needs_extraction`.
      if gate passes: `get_extraction_llm().chat(entity_extraction_prompt(msg),
      response_schema=EXTRACTION_SCHEMA)` -> `{anime_titles, wants_current_season,
      intent}`. validate with pydantic, treat malformed as gate=false (log + continue).
      anilist lookup (if extraction succeeded):
      - anime_titles -> anilist_service.search_anime (new method, <=1 query, batch)
      - wants_current_season -> anilist_service.fetch_current_season (<=1 query)
      context assembly: call context_builder with looked_up_anime injected.
      stream: `get_answer_llm().stream(messages)` -> async generator of str deltas.
      yields SSE events: `delta`, `anime_card` (for each looked-up anime), `done`,
      `error`.
      done when: "why would i like Frieren?" triggers extraction + lookup and streams
      a response with at least one anime_card event; "what should i watch based on my
      taste" skips extraction.

### E - conversation router (after D1, B5)

- [x] **E1** `routers/conversations.py`:
      - `POST /conversations` -> `{id, title, created_at}`
      - `GET /conversations?limit=20&cursor=` -> `{items: [...], next_cursor}`
      - `GET /conversations/{id}` -> conversation + last 50 messages
      - `DELETE /conversations/{id}` -> 204
      - `POST /conversations/{id}/messages` -> SSE stream
        body: `{content: str}` (capped at max_user_message_chars).
        SSE events (text/event-stream): `data: {"type":"delta","content":"..."}`,
        `data: {"type":"anime_card","anime":{...}}`, `data: {"type":"done"}`,
        `data: {"type":"error","message":"..."}`.
        after stream completes: persist user message + assistant message (full
        content assembled from deltas) + context_used snapshot.
      wire into `main.py`.
      done when: curl/httpie SSE call streams tokens and both messages appear in db.

### F - frontend (after E1)

- [x] **F1** `lib/api.ts` additions: `createConversation()`, `listConversations()`,
      `getConversation(id)`, `deleteConversation(id)`.
      `lib/stream.ts`: SSE reader that parses `delta | anime_card | done | error`
      events and calls callbacks.
      done when: typed, tsc --noEmit passes.

- [x] **F2** `components/sidebar/conversation-list.tsx`: list conversations, highlight
      active, "new chat" button at top. links to `/chat/[id]`.
      integrate into chat layout (sidebar + main area split).
      done when: clicking a conversation navigates to it.

- [x] **F3** `components/chat/message-list.tsx`: renders messages list (user + assistant).
      `components/chat/streaming-message.tsx`: renders partial assistant text during
      stream (appends deltas, switches to final on done).
      `components/chat/message-input.tsx`: textarea, submit on enter (shift+enter =
      newline), disabled during stream.
      done when: send a message, see it echo back, see assistant stream in.

- [x] **F4** markdown render in assistant messages (react-markdown or marked; no html
      injection). `components/chat/anime-card.tsx`: compact card (title, genres, score)
      rendered inline when `anime_card` SSE event arrives.
      done when: a markdown response renders with bold/lists; anime_card event renders
      a visible card below the message.

- [x] **F5** `app/chat/[id]/page.tsx`: conversation-specific page that loads history on
      mount and plugs into the same message-list + input components.
      `app/chat/page.tsx`: redirects to most recent conversation or creates a new one.
      done when: page refresh preserves conversation history; back-navigation works.

---

## phase 4 - hardening + ship

execution order: security -> provider abstraction -> observability -> tests ->
packaging -> prompts. commit after each task; senior review before merge.

operating rules for this phase:
- minimum code that solves the problem; nothing speculative
- touch only what the task requires; clean up only own mess
- define success criteria per task; loop until verified

### 1 - security

- [x] **rate_limit** middleware: in-process token bucket. auth 10/min/ip,
      chat 20/min/user, sync 1/min/user.
      DECISION (locked): v1 is SINGLE-WORKER only. the in-process bucket is the
      accepted v1 implementation (operational simplicity over horizontal scaling
      per plan.md). distributed limiter (redis/equiv) is v2.
      done when: documented single-worker-only; limits verified under a one-worker
      run (over-limit -> 429, under-limit passes).
- [x] input validation pass: 2000-char user message cap at api layer, uuid
      validation on path params, pydantic constraints on bodies.
      done when: oversized msg -> 422/400; malformed uuid -> 422; valid unaffected.
      audit: path uuid + query bounds + status set-check already enforced. only gap
      was SendMessageRequest (bare str) -> added strip + min_length + hard-cap Field;
      tunable product cap stays in handler.

### 2 - provider abstraction (factory + ollama only; openai/anthropic deferred v2)

- [x] **B3** `llm/factory.py`: `get_answer_llm()` / `get_extraction_llm()` (extraction
      model falls back to llm_model), `_build_provider` selects from llm_provider.
      openrouter + ollama only; openai/anthropic raise LLMError (deferred v2). ollama
      lazy-imported in its branch (ships in next task). settings override param for tests.
      done when: switching `LLM_PROVIDER` selects the right impl; imports clean. [verified]
- [x] **B2 (partial)** `llm/ollama.py`: implements LLMProvider against
      `{ollama_base_url}/api/chat`; stream via NDJSON; raises LLMError.
      done when: imports clean; structurally matches ABC; ollama swap streams.
      [verified vs real api shapes via mocked transport: chat() stream=false +
      token counts, response_schema->format, NDJSON stream deltas, non-200->LLMError]
- [ ] replace hardcoded `OpenRouterProvider` in chat_service.py + taste_service.py
      with factory calls; remove the local `_get_answer_llm`/`_get_extraction_llm`
      helpers.
      done when: no `OpenRouterProvider` import in services; chat + taste still
      work via openrouter default.

### 3 - observability

- [ ] structured logging + global exception handler in main.py (consistent error
      envelope, log with request context, no stack trace to client, fail loud).
      done when: unhandled error -> structured json error + structured log line.

### 4 - tests

- [ ] **test harness** (belongs to this bucket, not incidental): pytest +
      pytest-asyncio; dedicated test `DATABASE_URL` (NOT the dev compose pg on
      5433); alembic migrations applied in test setup; async session fixture;
      transactional rollback or schema recreate per test.
      done when: `pytest` runs green against the isolated test db.
- [ ] cross-user data isolation (second user read/delete -> 403/404)
- [ ] oauth callback (state validation, token encrypted at rest, session set)
- [ ] context token-budget bound (large list/conversation stays under cap)
- [ ] sync recovery (stale job reaped + retryable, active-job dedupe)
- [ ] provider swap (ollama) smoke
- [ ] (carry-over) taste schema validation + `input_hash` skip-on-unchanged

### 5 - packaging

- [ ] docker PRODUCTION config: single uvicorn worker (matches rate-limit
      decision), README self-host setup, finalize `.env.example` (all required
      keys + ollama_base_url, guidance comments, no real values).
      done when: fresh operator can bring the stack up from README + .env.example.

### 6 - prompts

- [ ] review prompt quality (system / taste_extraction / entity_extraction):
      anti-hallucination rules, grounding, schema clarity, token cost. produce a
      findings list with proposed edits for senior review BEFORE changing.

### deferred / out of v1 scope

- [ ] **B2 (rest)** native `llm/openai.py` + `llm/anthropic.py` -> v2 (openrouter
      already proxies these models; no v1 need).
- [ ] end-to-end reconnect UX verification (expiry/401 -> `anilist_connected=false`
      -> banner -> re-login) - core logic already in phase 1 guard; manual verify
      at ship time.
