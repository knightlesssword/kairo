# kairo mvp v1 - architecture

## context

product:

> an ai assistant that remembers my anime taste.

the differentiator is `user context + llm reasoning`, not a recommendation engine.
the llm already does the reasoning. the app's job is to feed it good personal context.

scope was deliberately reduced from an "anime intelligence platform" back to a
chatgpt/claude-style chat ui + anilist integration + anime-specific memory.

confirmed decisions:
- anime facts in v1 = inject the user's own synced list (compacted) + one direct
  AniList lookup when the user names an anime or asks about current season. no tool
  loop, no autonomous agent.
- deployment = self-host OSS via docker. operator supplies keys via `.env`.
- llm = provider-agnostic abstraction (openrouter default, plus openai / anthropic / ollama).

---

## what was removed and why

| removed | why |
|---|---|
| autonomous agent loops | llm reasons in one pass; loops add latency, cost, nondeterminism for no v1 value |
| tool registry / multi-tool dispatch | replaced by a fixed deterministic pre-step (conditional extract -> optional single AniList lookup) |
| vector db / embeddings | no retrieval need at v1 scale; taste profile + list slice fit in context |
| ml recommendation system | llm + injected context answers "why would i like this" better than a score |
| deterministic scoring (genre/tag match %) | product answers "why", not "87.4%" |
| web search tool | paid dependency + injection surface; defer to v2 |
| anime_cache + ranking/analytics tables | denormalize title+genres onto user_anime_list instead; optional in-process TTL cache only |
| background worker process / queue | sync runs as in-process asyncio task with postgres job state |
| microservices / distributed arch | single fastapi service + single postgres |

net effect: fewer tables, fewer services, <=2 llm calls per message, bounded AniList calls.

---

## final architecture

```
[next.js frontend]
       |  HTTPS / SSE
       v
[fastapi single service]
       |
       +-- postgresql            (only datastore)
       +-- anilist graphql       (oauth + sync + minimal named lookup)
       +-- llm provider          (openrouter | openai | anthropic | ollama)
```

### message flow (no agent loop)

```
user message
   |
1. validate + auth + load: taste_profile, compact list slice, last N messages
   |
2. CONDITIONAL extraction pre-step (skipped for general chat):
     - cheap heuristic gate first: run only if the message plausibly names a title
       (quotes, capitalized multi-word spans, "vs", "watch", "this/next season",
       "airing", "right now") OR asks about current season
     - if gate passes: one cheap structured llm call
         -> { anime_titles: [...], wants_current_season: bool, intent: str }
     - if gate fails: skip step 2 and step 3 entirely, go to assemble
   |
3. optional direct AniList lookup (bounded, <=2 graphql queries):
     - if anime_titles: one search query (batched) for their metadata
     - if wants_current_season: one airing query for current season
   |
4. assemble context (see context builder)
   |
5. main llm streaming call
   |
6. stream SSE deltas to client
   |
7. persist user + assistant message (+ context_used for debugging)
```

step 2 is conditional + deterministic control flow, not a tool loop. most general
chat ("recommend something based on my taste") skips it. step 3 is a plain service
call, capped, never recursive.

### context builder (core of the product)

injected into every main call, all bounded:
- `system` prompt (static, not user-controllable)
- `taste_profile` json (the distilled blob, small)
- `list slice`: top ~30 by score, recent ~20 completed, ~15 dropped, aggregate counts
  (NOT the full list - thousands of entries never injected wholesale)
- `looked_up_anime`: metadata fetched in step 3, if any
- `current_date` + `current_season`
- last N (default 20) conversation messages

list slice uses denormalized `title` + `genres` columns on `user_anime_list`, so no
join and no separate anime table needed.

context is capped by a TOKEN BUDGET, not just item counts. context_builder estimates
tokens (tiktoken or chars/4 heuristic) and trims in priority order until under
`MAX_CONTEXT_TOKENS`: drop oldest history first, then shrink the list slice
(dropped -> recent -> top), keeping taste_profile + looked_up_anime + system prompt
last. guarantees a hard upper bound on cost/latency regardless of list/conversation size.

### taste profile generation

one llm call after each sync. input = compact summary of completed/scored/dropped
entries. output = validated json:

```json
{
  "likes": ["dark fantasy", "psychological stories", "slow burn"],
  "dislikes": ["filler", "very long shows"],
  "favorites": ["Attack on Titan", "Monster"],
  "watch_style": { "prefers_completed": true, "preferred_length": "medium" }
}
```

qualitative descriptors (slow burn, complex characters) require llm interpretation,
so this is llm-generated, not arithmetic. output validated against a pydantic schema
before persist.

regenerated only when inputs change: `input_hash` = sha256 over the sorted
(anilist_anime_id, status, score) tuples used as input. if the stored hash matches,
skip the llm call and keep the existing profile.

---

## folder structure

```
kairo/
├── frontend/
│   ├── app/
│   │   ├── (auth)/login/page.tsx
│   │   ├── (auth)/callback/page.tsx
│   │   ├── chat/page.tsx
│   │   ├── chat/[id]/page.tsx
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components/
│   │   ├── chat/message-list.tsx
│   │   ├── chat/streaming-message.tsx
│   │   ├── chat/message-input.tsx
│   │   ├── chat/anime-card.tsx
│   │   ├── chat/source-card.tsx
│   │   └── sidebar/conversation-list.tsx
│   ├── lib/api.ts          (typed fetch wrapper)
│   ├── lib/stream.ts       (SSE reader)
│   └── types/index.ts
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py            (pydantic-settings from env)
│   │   ├── database.py          (async sqlalchemy engine/session)
│   │   ├── dependencies.py      (current_user, db session, rate limit)
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── profile.py
│   │   │   └── conversations.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── anilist_service.py     (oauth exchange + graphql + sync + lookup)
│   │   │   ├── sync_service.py        (in-process job runner + job state + recovery)
│   │   │   ├── taste_service.py       (llm-generated profile + input_hash)
│   │   │   ├── context_builder.py     (assemble bounded context + token budget)
│   │   │   ├── chat_service.py        (gate -> extract -> lookup -> assemble -> stream)
│   │   │   └── conversation_service.py
│   │   ├── llm/
│   │   │   ├── base.py          (LLMProvider ABC + Message/ChatResponse types)
│   │   │   ├── openrouter.py
│   │   │   ├── openai.py
│   │   │   ├── anthropic.py
│   │   │   ├── ollama.py
│   │   │   └── factory.py       (from LLM_PROVIDER env)
│   │   ├── prompts/
│   │   │   ├── system.py
│   │   │   ├── taste_extraction.py
│   │   │   └── entity_extraction.py
│   │   ├── models/
│   │   │   ├── db/ (user, conversation, anilist, taste, sync_job)
│   │   │   └── schemas/ (auth, chat, profile)
│   │   └── middleware/rate_limit.py
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── .env.example
│
├── docker-compose.yml
├── plan.md
├── todo.md
└── README.md
```

---

## database schema

```sql
CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    anilist_id       INTEGER UNIQUE NOT NULL,
    username         VARCHAR(255) NOT NULL,
    access_token_enc TEXT NOT NULL,          -- fernet-encrypted AniList token
    token_obtained_at TIMESTAMPTZ,
    token_expires_at TIMESTAMPTZ,            -- checked before each AniList call
    anilist_connected BOOLEAN NOT NULL DEFAULT true, -- false when token expired/revoked; drives reconnect UX
    revoked_at       TIMESTAMPTZ,            -- when disconnect happened (audit detail)
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sessions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES users(id) ON DELETE CASCADE,
    expires_at   TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ DEFAULT now(),  -- updated on activity; drives sliding expiry + idle cleanup
    created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE anilist_profiles (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    raw_stats   JSONB NOT NULL,
    anime_count INTEGER,
    mean_score  FLOAT,
    synced_at   TIMESTAMPTZ DEFAULT now()
);

-- title + genres denormalized so context builder needs no anime table/join
CREATE TABLE user_anime_list (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(id) ON DELETE CASCADE,
    anilist_anime_id INTEGER NOT NULL,
    title            VARCHAR(512),
    genres           TEXT[],
    episodes         INTEGER,
    status           VARCHAR(20) NOT NULL,   -- AniList values: COMPLETED|CURRENT|DROPPED|PLANNING|PAUSED|REPEATING
    score            FLOAT,                  -- AniList 0-10, null if unscored
    progress         INTEGER DEFAULT 0,
    updated_at       TIMESTAMPTZ,
    UNIQUE(user_id, anilist_anime_id)
);

CREATE TABLE taste_profiles (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    profile      JSONB NOT NULL,             -- likes/dislikes/favorites/watch_style
    input_hash   VARCHAR(64),                -- sha256 of inputs; skip regen if unchanged
    model        VARCHAR(128),               -- which model generated it
    generated_at TIMESTAMPTZ DEFAULT now(),
    version      INTEGER DEFAULT 1
);

-- minimal postgres sync state, no queue
CREATE TABLE sync_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
    status      VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending|running|completed|failed
    error       TEXT,
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE conversations (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID REFERENCES users(id) ON DELETE CASCADE,
    title      VARCHAR(255),
    summary    TEXT,                          -- rolling summary of older turns; unused in v1, populated in v2
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    role            VARCHAR(10) NOT NULL,    -- 'user' | 'assistant'
    content         TEXT NOT NULL,
    context_used    JSONB,                   -- debug snapshot, droppable
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_user_anime_list_user   ON user_anime_list(user_id);
CREATE INDEX idx_user_anime_list_status ON user_anime_list(user_id, status);
CREATE INDEX idx_user_anime_list_score  ON user_anime_list(user_id, score DESC);
CREATE INDEX idx_messages_conversation  ON messages(conversation_id, created_at);
CREATE INDEX idx_conversations_user     ON conversations(user_id, updated_at DESC);
CREATE INDEX idx_sessions_user          ON sessions(user_id);
CREATE INDEX idx_sync_jobs_user         ON sync_jobs(user_id, created_at DESC);
```

---

## api routes

```
# auth
GET  /auth/anilist/login        -> 302 to AniList (state in httponly cookie)
GET  /auth/anilist/callback     -> validate state, exchange code, upsert user, set session
POST /auth/logout               -> delete session
GET  /auth/me                   -> {id, username, anilist_id, anilist_connected, last_synced_at}

# profile / sync (async, no queue)
POST /profile/sync              -> {job_id}        (spawns in-process asyncio task)
GET  /profile/sync/{job_id}     -> {status, error?}
GET  /profile/taste             -> taste_profile json
GET  /profile/anime-list?status=&limit=&offset=

# conversations
POST   /conversations                    -> {id, title, created_at}
GET    /conversations?limit=&cursor=
GET    /conversations/{id}               -> conversation + last 50 messages
DELETE /conversations/{id}
POST   /conversations/{id}/messages      -> SSE stream
        body: {content}
        events: delta | anime_card | done | error
```

no public `/anime/*` endpoints. the AniList lookup is internal to chat_service only,
which shrinks attack surface and keeps the app from becoming a db frontend.

---

## llm abstraction

```python
class Message(BaseModel):
    role: str            # system|user|assistant
    content: str

class ChatResponse(BaseModel):
    content: str
    input_tokens: int
    output_tokens: int

class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[Message], system: str | None = None,
                   response_schema: dict | None = None) -> ChatResponse: ...
    @abstractmethod
    async def stream(self, messages: list[Message],
                     system: str | None = None) -> AsyncIterator[str]: ...
```

- `chat()` used for taste generation + entity extraction (structured json).
- `stream()` used for the final user-facing answer.
- `response_schema` enforces json where supported; otherwise validate with a strict
  pydantic parse + one retry.
- factory selects impl from `LLM_PROVIDER`. openrouter is default.
- no tool/function-calling surface in the ABC for v1.

env (no models hardcoded in code; `.env.example` ships empty values with guidance):
```
LLM_PROVIDER=openrouter
# answer model - needs natural explanations (Claude Sonnet / GPT-4.1 / Gemini Pro class)
LLM_MODEL=
# gate/extraction model - cheap + fast, shallow output (GPT-4.1-mini / Claude Haiku class)
LLM_EXTRACTION_MODEL=
OLLAMA_BASE_URL=
```
answer model carries the product (the "why would i like this" explanations). extraction
model only emits `{anime_titles, intent}`, so optimize it for cost/latency.

---

## security review

oauth
- state param: 32-byte random, httponly+secure+samesite=lax cookie, validated then deleted
- AniList token encrypted at rest (Fernet, `FERNET_KEY` env), never sent to frontend
- callback validates AniList user id before upsert

session
- server-side sessions (uuid in httponly+secure+samesite=lax cookie)
- no JWT, no token in localStorage; revocation = delete row
- 30-day expiry, sliding via last_used_at

anilist token lifetime (expiry-aware, no refresh flow)
- before each AniList call: if `token_expires_at` passed, set `anilist_connected=false`
  + `revoked_at=now()`, abort the call cleanly (no mysterious sync failure)
- a 401 from AniList does the same
- frontend surfaces "your AniList connection expired, reconnect" and routes to re-login
- no refresh-token handling unless AniList officially supports it

prompt injection (treat AniList + llm output as untrusted)
- AniList titles/usernames/descriptions inserted only as delimited data blocks, never
  into the system prompt or as instructions
- system prompt static and never user-controllable
- user message capped (2000 chars) at api layer
- extraction + taste outputs validated against pydantic schema before use; reject+retry
  on mismatch, never eval/exec

data isolation
- every query scoped `WHERE user_id = :session_user`
- user_id always from session, never from request body
- conversation/message ownership checked before any read/write

external data validation
- AniList graphql responses parsed into typed models, unknown fields dropped
- AniList lookup bounded: <=2 queries per message, no recursion

rate limiting (in-process token bucket, single-process MVP limitation)
- auth: 10/min/ip
- chat: 20/min/user
- sync: 1/min/user (AniList global limit 90/min)

secrets
- all via env; `.env` gitignored, `.env.example` committed with no real values
- required: `DATABASE_URL`, `FERNET_KEY`, `SESSION_SECRET`, `ANILIST_CLIENT_ID`,
  `ANILIST_CLIENT_SECRET`, `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`

llm output
- rendered as markdown only, no server-side execution
- anime_card events built from validated AniList data, not from free-text llm output

---

## verification

- `docker-compose up`, run alembic migrations, confirm tables exist
- oauth: complete AniList login end-to-end, confirm session cookie + encrypted token row
- sync: trigger on a large list, poll job to `completed`, confirm user_anime_list
  populated and taste_profiles row generated and schema-valid; re-sync with no changes
  skips llm via input_hash
- sync recovery: kill mid-sync, restart, confirm stale job marked failed and retryable
- context bound test: assert assembled context stays under token budget regardless of
  list/conversation size
- chat: "recommend something based on my taste" (gate skips extraction) and
  "why would i like Frieren?" (gate triggers lookup); confirm SSE streams + taste reflected
- isolation: second user cannot read first user's conversations (403/404)
- provider swap: flip `LLM_PROVIDER` to ollama, confirm chat still streams

---

## remaining risks

- llm parametric knowledge is stale for 2025+ / obscure titles; the single AniList
  lookup mitigates named titles but not vague "what's airing" beyond one season query.
  full airing/seasonal tooling is v2.
- conditional extraction gate can misfire (skip a needed lookup or do an unneeded one);
  bounded, low blast radius.
- in-process sync task is lost on restart mid-sync; mitigated by stale-job reaper +
  idempotent upserts. a real worker is v2.
- in-process rate limiter does not work across multiple workers; single-process only.
- injected list slice grows token cost with active users; capped by token budget.
- AniList lookups uncached by choice; optional in-process TTL dict if rate limits bite.
- taste profile quality depends on the model; a weak model yields generic likes/dislikes.

## future scope

- v2: current airing tools, web search, external sources, anime metadata tools,
  conversation summarization (trigger when a conversation exceeds 50 messages; fills the
  `summary` column and prepends it to the bounded history), real sync worker.
- v3: embeddings, vector search, advanced memory/retrieval.

## resolved decisions (locked)

```
anilist:
  token: { encrypted: true, expiry_checked: true, refresh_flow: no, reauth_on_expiry: yes }
  anilist_connected flag drives reconnect UX
llm:
  answer_model: medium/high quality (Sonnet / GPT-4.1 / Gemini Pro class)
  extraction_model: cheap/fast (GPT-4.1-mini / Haiku class)
  provider: openrouter default; models via empty env + .env.example comments
memory:
  history: last 20 messages
  summary_field: yes (column present)
  summarization: deferred; trigger later when conversation > 50 messages
anime_cards:
  only_from_anilist: true (no card for parametric-only mentions)
auth:
  anilist_required: true
  anonymous_mode: no
ux:
  sync_freshness_indicator: yes ("synced 2 hours ago" + [Sync now])
```

## unresolved questions

- none blocking v1. confirm AniList actual token TTL during implementation (informational
  only; expiry-aware flow handles any value).
