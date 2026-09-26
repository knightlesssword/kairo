# recommendation retrieval: grounding kairo's suggestions

status: proposed. plan A implemented now. plan B deferred.
author: ai-assisted draft for senior review.
date: 2026-06-26

---

## 0. the actual problem (read this first)

kairo "fumbles" on recommendations not because the prompt is weak, but because
the model has **no data to recommend from**.

current message flow (`chat_service.stream_chat`):

```
1. extract entities      -> {anime_titles, wants_current_season}
2. anilist lookup        -> metadata ONLY for titles the user named, + current season
3. user-entry lookup     -> the user's own rows for those named titles
4. build context         -> system prompt + taste + list slices + looked-up anime
5. stream main LLM call
```

look at step 2. the only anime that ever enter the context are:

- titles the **user typed**, and
- the current season list.

so when someone says "recommend me something like steins;gate," the model has
to **invent** candidate titles from its own memory. then the system prompt tells
it "never recommend anything in their list" and "never fabricate." we are asking
the prompt to police a constraint the model has no data to satisfy. that is the
fumble. on a good day the model's memory is right; on a free OpenRouter model it
is garbage. either way it is **ungrounded**.

the fix is not better prompting. it is **retrieval**: fetch real candidate
titles from anilist, filter out everything the user has already seen, hand that
list to the model, and tell it to choose only from that list.

two ways to do retrieval:

- **plan A — deterministic pipeline.** we (the code) decide what to fetch based
  on the user's intent, fetch it, inject it. the model never calls tools. simple,
  predictable, streams cleanly. **building this now.**
- **plan B — tool-calling / "agentic."** the model decides what to fetch by
  calling functions mid-reasoning. flexible, handles weird multi-constraint
  queries, but adds latency, nondeterminism, and depends on the model being good
  at tool-calling (free models often are not). **deferred until A's limits bite.**

---

## 1. concepts you'll need (domain primer)

short glossary so the rest of the doc makes sense. skip if known.

- **grounding**: giving the model real, verified data in its context instead of
  relying on what it memorized during training. ungrounded = hallucination-prone.
- **retrieval**: the act of fetching that real data (here: anilist GraphQL).
  this whole project is a retrieval problem wearing an anime hat.
- **tool / function calling**: a mode where you describe functions to the model
  (name, params as JSON schema) and it can emit "call `discover_anime` with
  `{genre: 'Thriller'}`" instead of prose. your code runs the function, feeds the
  result back, the model continues. this is what "agentic" means in practice for
  us. plan B uses it; plan A does not.
- **intent classification**: deciding what the user wants (rec vs fact vs general
  chat) so we fetch the right thing. plan A does this in the cheap extraction call.
- **candidate set**: the pre-filtered list of recommendable titles we hand the
  model. the core new object plan A introduces.

why plan A first: it solves the stated problem with the least new machinery,
keeps streaming trivial, and is fully deterministic so you can debug it by
reading logs. tool-calling is strictly more capable and strictly more ways to
break; you adopt it when the deterministic classifier can no longer express the
queries users actually ask.

---

## 2. the full tool / retrieval surface (what's possible)

you asked how expansive this gets. below is the complete menu the anilist API +
your own DB make available. "tool" here means a discrete retrieval capability;
in plan A these are internal functions the pipeline calls, in plan B these become
model-callable functions. same functions, different caller.

anilist's GraphQL schema is large (Media, Character, Staff, Studio, Recommendation,
AiringSchedule, Page filters). this is most of what's reachable and useful for kairo.

### 2.1 discovery (generate candidates to recommend) — the gap plan A fills

| tool | anilist mechanism | use case |
|---|---|---|
| `discover_anime` | `Page(media: {genre_in, tag_in, format, episodes_*, averageScore_*, seasonYear, source, sort})` | "action shows under 13 eps", "highly-rated romance movies" |
| `recommendations_for(media_id)` | `Media.recommendations` edge | "anime like steins;gate" (anilist's own community rec graph) |
| `trending_now` | `Page(media: {sort: TRENDING_DESC})` | "what's everyone watching rn" |
| `top_ranked` | `Page(media: {sort: SCORE_DESC})` or `Media.rankings` | "best anime of all time / of 2019" |
| `relations(media_id)` | `Media.relations` edge | sequels/prequels/side-stories, "what's the watch order" |

`discover_anime` and `recommendations_for` are the two that kill most fumbles.
the rest are incremental.

### 2.2 factual / metadata (you already have the core of this)

| tool | mechanism | use case | status |
|---|---|---|---|
| `search_anime(titles)` | aliased `Media(search:)` | resolve named titles to data | **exists** |
| `fetch_current_season` | `Page(media: season, status: RELEASING)` | "what's airing this season" | **exists** |
| `anime_detail(media_id)` | `Media(id:)` full fields | deep facts on one title | trivial extension |
| `character_lookup(name)` | `Character(search:)` | "who is okabe", character facts | new |
| `studio_works(name)` | `Studio(search) { media }` | "other ufotable shows" | new |
| `staff_works(name)` | `Staff(search) { roles }` | "what else did this director make" | new |

### 2.3 temporal / airing

| tool | mechanism | use case |
|---|---|---|
| `next_airing(media_id)` | `Media.nextAiringEpisode` | "when's the next episode of X" |
| `upcoming_season` | `Page(media: season=next, status: NOT_YET_RELEASED)` | "what's coming next season" |

### 2.4 user-data (query the local DB smarter, no anilist call)

right now `context_builder` dumps fixed slices (top 30, recent 20, dropped 15)
into every prompt. these tools would instead answer targeted questions:

| tool | mechanism | use case |
|---|---|---|
| `query_my_list(filters)` | SQL over `user_anime_list` | "what did i rate 9+", "my dropped action shows" |
| `my_genre_stats` | `Viewer.statistics.anime.genres` (anilist) or aggregate local | "what do i watch most" |
| `list_summary` | aggregate counts (already injected) | "how many have i completed" |

### 2.5 write / mutation (out of scope, flagged for awareness)

| tool | mechanism | risk |
|---|---|---|
| `set_status(media_id, status)` | anilist `SaveMediaListEntry` mutation | writes to user's real anilist account. auth-sensitive, needs explicit confirm UX. do not build casually. |

### 2.6 validation helpers (support tools)

| tool | mechanism | why |
|---|---|---|
| `genre_collection` | `GenreCollection` | anilist genres are a fixed enum (~20). validating LLM-emitted genres against this avoids empty-result queries from typos like "thriller" vs "Thriller". |
| `tag_collection` | `MediaTagCollection` | same for tags (hundreds). |

### priority for plan A

build only what closes the recommendation gap:

1. `discover_anime` (genre/format/episode/score filters) — primary
2. `recommendations_for(media_id)` — "similar to X"
3. reuse existing `search_anime` to resolve seed titles -> ids

everything else is a later phase or plan B tool. note this so the senior
reviewer sees we are deliberately not gold-plating.

---

## 3. plan A — deterministic candidate retrieval (build now)

### A. design in one paragraph

extend the existing cheap extraction call to also detect "user wants
recommendations" plus any constraints (seed titles, genres). if recs are wanted,
the pipeline fetches a candidate set from anilist (via `recommendations_for` when
there's a seed, else `discover_anime` by genre, else trending as fallback),
removes every title already in the user's list **in code**, caps it, and injects
it as a new `CANDIDATE ANIME` context block. the system prompt is updated to say
"recommend only from CANDIDATE ANIME." the main streaming call is otherwise
unchanged.

key property: titles the user has seen are filtered out **before the model sees
them**, so the "never recommend watched titles" rule becomes structurally true
instead of a prompt the model can violate.

### why this shape

- minimum new surface: one new extraction field group, two new anilist functions,
  one new context block, one prompt edit. no new abstractions, no tool-calling.
- streaming stays trivial: all fetching happens before the stream starts, exactly
  like the current `looked_up_anime` flow.
- deterministic: same input -> same fetch -> debuggable from the existing debug
  log line in `chat_service`.

### phases

each phase is independently testable. do not start the next until the current
one's success criteria pass.

---

#### phase A1 — anilist discovery queries (service layer)

**what**: add two functions to `anilist_service.py`:

- `discover_anime(token, *, genres=None, tags=None, formats=None, min_episodes=None, max_episodes=None, min_score=None, sort="POPULARITY_DESC", limit=20) -> list[AnimeSearchResult]`
- `fetch_recommendations(token, media_id, limit=20) -> list[AnimeSearchResult]`

**why**: pure data layer first, no pipeline coupling. these reuse the existing
`AnimeSearchResult` model and `_MEDIA_FIELDS` constant, so the output shape and
`to_dict()` already match what the context builder and SSE `anime_card` events
expect. zero downstream churn.

**how (notes for implementer)**:
- `discover_anime` builds a `Page(media: {...})` query. only include filter
  variables that are non-None (GraphQL ignores null variables if you guard them).
  anilist filter args: `genre_in: [String]`, `tag_in: [String]`,
  `format_in: [MediaFormat]`, `episodes_greater`/`episodes_lesser` (note: these
  are exclusive bounds), `averageScore_greater`, `sort: [MediaSort]`.
- `fetch_recommendations`: query `Media(id: $id){ recommendations(sort: RATING_DESC){ nodes { mediaRecommendation { <_MEDIA_FIELDS> } } } }`.
  unwrap `nodes[].mediaRecommendation` into `AnimeSearchResult`.
- both follow the existing pattern: `_query(...)`, then `model_validate` each raw
  item inside try/except (skip malformed, never abort).

**files**: `backend/app/services/anilist_service.py` (additive only).

**success criteria**:
- a throwaway script (scratchpad, not committed) calls each function against a
  real token and prints >0 valid `AnimeSearchResult` for a known input
  (e.g. `recommendations_for(steins_gate_id)`, `discover_anime(genres=["Thriller"])`).
- malformed/empty responses return `[]`, never raise.

---

#### phase A2 — intent + constraint extraction

**what**: extend `entity_extraction` schema + prompt with:

- `wants_recommendations: bool`
- `recommendation_seeds: list[str]` — titles the user wants "similar to"
- `genres: list[str]` — genre constraints named in the message

update `_ExtractionResult` in `chat_service.py` to match.

**why**: the pipeline needs to know (a) is this even a rec request, and (b) what
to base recs on, before it can fetch. doing this inside the **existing** extraction
call means no new LLM round-trip and no new latency. we are extending a call that
already runs, not adding one.

**how**:
- add the three fields to `ENTITY_EXTRACTION_SCHEMA` (all required, so the model
  always returns them; empty list / false when absent).
- update `build_entity_extraction_prompt` rules:
  `wants_recommendations`: true only when the user asks for suggestions / "what
  should i watch" / "like X". `recommendation_seeds`: titles to anchor similarity
  on. `genres`: only genres explicitly mentioned.
- this is the brittle part. extraction quality on free models is the main risk.
  the constraint that keeps it safe: even if extraction over-triggers
  `wants_recommendations`, the worst case is we fetch trending and inject a
  candidate block the model can ignore. no correctness violation, just wasted
  tokens. **document this as accepted risk.**

**files**: `backend/app/prompts/entity_extraction.py`, `backend/app/services/chat_service.py` (`_ExtractionResult`).

**success criteria**:
- feed 6-8 sample messages (3 rec requests, 3 factual, 2 ambiguous) through
  `_extract_entities`; rec requests set `wants_recommendations=true` with sane
  seeds/genres, factual ones set it false. log the outputs, eyeball them.
- a malformed model response still returns `None` (existing behavior) and the
  pipeline degrades to no-candidates, not a crash.

---

#### phase A3 — candidate retrieval + user-list exclusion (pipeline)

**what**: in `chat_service.stream_chat`, when `wants_recommendations`:

1. resolve `recommendation_seeds` -> anilist ids (reuse `search_anime`, already
   called for named titles).
2. fetch candidates:
   - seeds present -> `fetch_recommendations(seed_id)` for the first 1-2 seeds.
   - else genres present -> `discover_anime(genres=...)`.
   - else -> `discover_anime(sort="TRENDING_DESC")` (safe fallback).
3. **exclude everything in the user's list**: one query
   `select anilist_anime_id from user_anime_list where user_id=?`, build a set,
   drop any candidate whose id is in it.
4. cap to N (e.g. 15) candidates.

**why**: exclusion in code is the whole point. the model cannot recommend a
watched title if watched titles are not in its context. this converts a
soft prompt rule into a hard guarantee. doing it in SQL (a set of ints) is cheap
even for a 1000-entry list.

**how / tradeoffs**:
- keep the anilist call budget bounded (the file already caps at 2 queries;
  recommendations adds at most 1-2 more — document the new ceiling, e.g. <=4).
- exclusion set query is one extra round-trip to your own DB; negligible.
- edge case: after exclusion the candidate list can be empty (user has seen
  everything in that genre). that is fine and **correct** — the system prompt
  already says "say so rather than padding." pass the empty block through.

**files**: `backend/app/services/chat_service.py`.

**success criteria**:
- for a rec request with a seed, candidates are non-empty and contain **zero**
  ids present in the user's list (assert in a scratchpad test).
- for a user who has completed everything in a narrow genre, candidate list is
  empty and no crash.
- anilist call count per message stays within the documented ceiling.

---

#### phase A4 — candidate context block + system prompt

**what**:
- add a `CANDIDATE ANIME` block to `context_builder._build_system_message`,
  mirroring the existing `LOOKED UP ANIME` block (json lines, "None" when empty).
- thread `candidates` through `build_context` like `looked_up_anime` already is.
- add a system-prompt rule: when recommending, choose **only** from CANDIDATE
  ANIME; these are pre-filtered to exclude the user's list; if empty, say you
  don't have enough qualifying titles rather than inventing any.

**why**: this is where grounding actually lands in the model's context. the block
format reuses the existing pattern so there's nothing novel to learn or break.
the prompt rule ties the model to the candidate set.

**how**:
- `build_context` already takes `looked_up_anime` and `user_entries`; add
  `candidates: list[dict] | None = None` the same way. token-budget: candidates
  should be trimmed before the never-trim taste/system base but you can treat
  them like `looked_up_anime` (currently never trimmed — flag if that's a budget
  risk with 15 candidates; likely fine at ~15 short json lines).
- optionally emit candidates as `anime_card` SSE events too, so the UI shows them
  (reuse the existing loop). decide with the reviewer — not required for grounding.

**files**: `backend/app/services/context_builder.py`, `backend/app/prompts/system.py`,
`backend/app/services/chat_service.py` (pass candidates into `build_context`).

**success criteria**:
- debug log (`system_prompt_sent`) shows a populated `CANDIDATE ANIME` block on
  rec requests.
- the block is absent/None on non-rec messages (no wasted tokens).

---

#### phase A5 — end-to-end verification

**what**: define and run the success bar for the whole feature.

**success criteria (the loop-until-verified bar)**:

1. "recommend something like steins;gate" (user has steins;gate completed):
   - response recommends real titles, none in the user's list, none = steins;gate.
2. "recommend a short action anime":
   - candidates fetched by genre+episode filter, recs drawn only from them.
3. a factual question ("how many episodes is frieren") still works unchanged —
   no candidate fetch, no regression.
4. a user who has seen everything in the requested genre gets an honest "not
   enough qualifying titles," not invented ones.
5. anilist call count per message within documented ceiling; no new crashes in
   logs across the above.

**how to test**: manual, through the real chat endpoint, reading the debug log
line that already prints system size + looked-up count (extend it to print
candidate count). free-model variance means run each prompt 2-3x; grounding
should hold even when prose quality wobbles.

---

### plan A — files touched (complete list)

- `backend/app/services/anilist_service.py` — +2 functions (A1)
- `backend/app/prompts/entity_extraction.py` — +3 schema fields, prompt rules (A2)
- `backend/app/services/chat_service.py` — `_ExtractionResult` fields, candidate
  fetch + exclusion, pass-through (A2, A3, A4)
- `backend/app/services/context_builder.py` — `CANDIDATE ANIME` block + param (A4)
- `backend/app/prompts/system.py` — recommend-only-from-candidates rule (A4)

no new files. no new dependencies. no schema/migration changes.

---

## 4. plan B — tool-calling / agentic (deferred)

build this only when plan A's deterministic classifier can no longer express the
queries users actually ask (e.g. "something like X but the pacing of Y, under 13
eps, not isekai"). until then it is cost without benefit.

### what changes vs A

instead of the code deciding what to fetch, the **main model** decides by calling
functions. the tools from section 2 become model-callable. flow becomes a loop:

```
call model with tool schemas
  -> model emits tool_calls (e.g. discover_anime{genre:Thriller})
  -> code executes them, appends results
  -> call model again
  -> repeat up to N rounds
  -> final answer streams
```

### why deferred (the honest tradeoffs)

- **latency**: each tool round is an extra full LLM round-trip before the first
  token streams (~0.5-1.5s each). plan A fetches in parallel-ish before streaming
  and pays this once.
- **nondeterminism**: the model chooses; same input can fetch differently. harder
  to debug and test than A's fixed branches.
- **model dependency**: tool-calling reliability varies hard by model. **free
  OpenRouter models frequently don't support tools or botch the JSON.** given
  your stated "good sometimes, garbage sometimes," B is fragile until you're on a
  model with solid tool-calling. this is the single biggest reason to wait.
- **streaming complexity**: you can only stream the final turn; intermediate
  tool-call turns are not streamable. more moving parts in the SSE layer.

### phases (sketch, not detailed until we commit)

- **B1 — provider tool-calling support**: extend `LLMProvider` with a
  `chat_with_tools(messages, tools, system)` method returning either text or a
  list of tool calls. implement for OpenRouter (OpenAI-style `tools` param).
- **B2 — tool registry + dispatch**: map tool name -> anilist service fn, with
  JSON-schema definitions per tool (reuse section 2 functions).
- **B3 — agent loop**: bounded loop (max 2 tool rounds) in a new
  `agent_service`; execute tool calls, append observations, re-call.
- **B4 — retire the extraction gate**: the model now decides retrieval, so
  `_extract_entities` and `entity_extraction.py` can be dropped (or kept as a
  cheap pre-filter to skip the agent loop on plain chat — decide then).
- **B5 — streaming integration**: stream only the final turn; emit `anime_card`
  events from tool results; keep the existing SSE event shapes.
- **B6 — verification**: same grounding bar as A5, plus: loop terminates within
  the round cap, tool-call JSON validates, graceful degradation when the model
  emits a malformed tool call (fall back to A-style trending fetch).

### A and B coexist

plan A's anilist functions (section 2 / A1) are the **same functions** B exposes
as tools. building A first means B is mostly wiring (provider support + loop +
schemas), not new retrieval logic. nothing in A is throwaway.

---

## 5. open questions for the reviewer

1. **candidate count + token budget**: 15 candidates as ~15 json lines in the
   system prompt — acceptable, or should candidates be trimmable in
   `context_builder` (currently `looked_up_anime` is never trimmed)?
2. **emit candidates as `anime_card` SSE events?** grounding doesn't need it, but
   the UI could show recommended cards. yes/no affects A4 scope.
3. **genre validation**: validate LLM-emitted genres against anilist's
   `GenreCollection` (section 2.6) to avoid empty-result queries from bad casing,
   or accept empty-result-as-fallback-to-trending and skip the extra call?
4. **seed resolution ambiguity**: if `search_anime(seed)` returns the wrong title
   (common name collision), recs are based on the wrong anchor. accept for v1, or
   add a confidence/exact-match guard?
5. **extraction over-trigger**: accepted-risk stance (wasted tokens, no
   correctness break) ok, or do we want a cheap deterministic pre-check (keyword
   like "recommend/suggest/like") before trusting `wants_recommendations`?
6. **B trigger condition**: what concretely signals "A's classifier isn't enough"
   — a logged rate of multi-constraint queries? define the metric so the defer
   decision is data-driven, not vibes.
