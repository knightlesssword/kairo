# kairo - next features roadmap

current state: phases 0-3 shipped. phase 4 (hardening) ~70% done.
this doc covers what to build next, in priority order.

---

## close-out: phase 4 remaining (ship blockers)

finish these before any new feature work.

| item | what | status |
|------|------|--------|
| tests | cross-user isolation, oauth callback, context budget, sync recovery, provider swap, taste hash | not done |
| packaging | docker prod config (single-worker constraint), README self-host guide | not done |
| prompts | audit system/entity/taste prompts for hallucination risk, token cost, schema clarity | not done |

---

## v1.1 — polish (low effort, high value)

### 1. LLM-generated conversation titles

**problem:** `conversations.py:229` sets title as `content[:80]` — raw truncation of the first message. looks bad for long or question-format messages.

**what to build:**
- add `llm/title_generation.py` (or inline in chat_service): single cheap LLM call after first assistant response completes, prompt: "given this user message and assistant reply, generate a 5-8 word conversation title. no punctuation, no quotes."
- emit a new SSE event type: `{"type": "title", "title": "..."}` so the frontend updates without a page refresh
- `conversation_service.set_title()` already exists — just call it with the generated string instead of `content[:80]`
- use `get_extraction_llm()` (cheap model, same as entity extraction)

**files:**
- `backend/app/routers/conversations.py` — replace `set_title(content[:80])` call
- `backend/app/services/chat_service.py` — yield `title` SSE event after `done`
- `frontend/lib/stream.ts` — add `TitleEvent` type + `onTitle` callback
- `frontend/app/chat/[id]/page.tsx` — handle `onTitle` to update topbar title state

**effort:** ~3 hours

---

### 2. taste profile UI page

**problem:** `GET /profile/taste` exists but there's no frontend UI showing the user what kairo thinks about their taste. it's a black box.

**what to build:**
- new page: `app/profile/page.tsx`
- display `likes`, `dislikes`, `favorites`, `watch_style` from taste profile
- show last sync time + "sync now" button (sync-status component already exists)
- show aggregate stats from `GET /profile/anime-list` (counts per status, mean score)
- link from sidebar (add entry below conversation list)

**files:**
- `frontend/app/profile/page.tsx` (new)
- `frontend/components/sidebar/conversation-list.tsx` — add profile nav link
- `frontend/lib/api.ts` — `getTasteProfile()` + `getAnimeList()` already exist structurally, verify or add

**effort:** ~2 hours

---

### 3. anime card — AniList deep link + format badge

**problem:** anime cards show title/score/genres but no way to click through to AniList. also missing format (TV/Movie/OVA) which helps disambiguation.

**what to build:**
- add `url: string` to `AnimeSearchResult.to_dict()` — AniList canonical URL is `https://anilist.co/anime/{id}`
- add `format` to SSE payload (already in model as `format` field)
- frontend `AnimeCard` component: make title a link (`target="_blank"`), show format badge next to genres

**files:**
- `backend/app/services/anilist_service.py` — `to_dict()` add `url` field
- `frontend/lib/stream.ts` — add `url?: string` to `AnimeCard` interface
- `frontend/components/chat/anime-card.tsx` — title as link, format badge

**effort:** ~1 hour

---

### 4. `title` SSE event — frontend receives title without polling

**already partially described in item 1.** pulling it out because it unblocks the topbar title updating live during the first message — currently needs a page refresh to show the generated title.

this is a dependency of item 1 anyway.

---

## v1.2 — chat intelligence (medium effort)

### 5. character and staff search

**problem:** entity extraction only catches anime titles and `wants_current_season`. questions like "who voices Levi?" or "what other anime did the director of Frieren make?" get no structured lookup — the LLM has to guess.

**what to build:**
- extend entity extraction schema: add `character_names: list[str]`, `staff_names: list[str]`
- extend `anilist_service.py`: add `search_character(name)` and `search_staff(name)` using AniList Character/Staff queries
- inject results into context bundle as `character_block` / `staff_block`
- emit `character_card` and `staff_card` SSE events (optional — could just inject into context without cards)

**AniList queries needed:**
```graphql
query ($search: String) {
  Character(search: $search) {
    id, name { full }, description, media(type: ANIME) { nodes { title { romaji } } }
  }
}

query ($search: String) {
  Staff(search: $search) {
    id, name { full }, primaryOccupations
    staffMedia(type: ANIME) { nodes { title { romaji } } }
  }
}
```

**files:**
- `backend/app/prompts/entity_extraction.py` — extend schema + instructions
- `backend/app/services/anilist_service.py` — add search_character, search_staff
- `backend/app/services/context_builder.py` — add character_block, staff_block
- `backend/app/services/chat_service.py` — wire extraction → lookup → context

**effort:** ~4 hours. token cost increase per message is minimal (only when names detected).

---

### 6. recommendation list SSE event

**problem:** when kairo recommends multiple anime, they render as prose. there's no structured "here are 5 anime you should watch" card list.

**what to build:**
- extend chat_service: after streaming completes, parse assistant content for AniList IDs mentioned (can be tagged inline in the response via system prompt instruction: "when listing recommendations, include `[anilist:ID]` tags")
- OR: emit `recommendation_list` SSE event with ordered list of anime IDs, looked up during the stream
- frontend: render a scrollable horizontal card strip when `recommendation_list` event arrives

**approach:** simpler path — instruct system prompt to output `[anilist:ID]` tags inline, then parse them post-stream, batch-lookup any not already in context, emit as a `recommendation_list` event after `done`.

**files:**
- `backend/app/prompts/system.py` — add inline tag instruction
- `backend/app/services/chat_service.py` — post-stream parse + batch lookup + recommendation_list event
- `frontend/lib/stream.ts` — add RecommendationListEvent type
- `frontend/components/chat/` — new `recommendation-list.tsx` component

**effort:** ~5 hours

---

## v1.3 — AniList write-back (larger feature)

### 7. update watchlist from chat

**problem:** users can't act on kairo's recommendations. they have to go to AniList separately to add/update entries.

**what to build:**
- detect "add X to my list", "mark X as watching", "rate X 8/10" intent in entity extraction
- new extraction field: `watchlist_updates: [{anime_id: int, status?: str, score?: float}]`
- new AniList mutation via `anilist_service.py`:
  ```graphql
  mutation ($mediaId: Int, $status: MediaListStatus, $score: Float) {
    SaveMediaListEntry(mediaId: $mediaId, status: $status, score: $score) {
      id, status, score
    }
  }
  ```
- emit `watchlist_update` SSE event: `{type: "watchlist_update", anime_id, status, score, confirmed: true}`
- frontend: show a toast/confirmation card when update succeeds
- guard: only execute if user explicitly confirms or intent is unambiguous; add a `confirm` SSE event type to ask user before writing (or just write + show what was done)

**security note:** requires user's AniList token with write scope. check current OAuth scope — AniList uses `implicit` flow. may need to verify `SaveMediaListEntry` is allowed under current token.

**files:**
- `backend/app/prompts/entity_extraction.py` — add watchlist_updates field
- `backend/app/services/anilist_service.py` — add save_media_list_entry mutation
- `backend/app/services/chat_service.py` — execute mutations pre/post stream, emit events
- `frontend/lib/stream.ts` — add WatchlistUpdateEvent type
- `frontend/components/chat/` — toast or card for update confirmation

**effort:** ~6 hours. highest risk item (write ops, token scope, user intent ambiguity).

---

## v2.0 — platform features (deferred, scope too large for v1.x)

| feature | why deferred |
|---------|-------------|
| native OpenAI/Anthropic providers | openrouter proxies both; no v1 need (already in todo as deferred) |
| conversation search | needs full-text index (pg `tsvector`) or vector embeddings; not worth the infra for small datasets |
| conversation export (JSON/markdown) | low urgency, easy to add when requested |
| distributed rate limiting (redis) | locked: single-worker v1, redis is v2 per plan.md |
| PWA / mobile layout | current design is responsive; PWA requires service worker + offline strategy |
| multi-user sharing | needs public conversation links + visibility model changes |

---

## priority order for next sprint

1. finish phase 4 (tests + packaging + prompts) — ship unblocked
2. LLM titles + `title` SSE event (item 1) — visible polish, quick
3. anime card AniList link (item 3) — 1 hour, obvious UX gap
4. taste profile page (item 2) — surfaces existing data users can't see
5. character/staff search (item 5) — expands chat utility meaningfully
6. recommendation list cards (item 6) — makes recommendations actionable
7. watchlist write-back (item 7) — biggest feature, do last

---

## unresolved questions

- AniList OAuth scope: does current implicit flow include write permissions for `SaveMediaListEntry`? needs verification before starting item 7.
- title generation: should the extraction LLM generate the title, or a dedicated tiny call? extraction model may vary by provider.
- confirmation UX for write-back: silent auto-update vs. explicit confirm card vs. natural language "done, added X to your watchlist" — needs a decision before item 7.
