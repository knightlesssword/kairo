# Plan 06 — Backend: Pipe cover_image + year into SSE anime_card events

**Goal:** The frontend anime card already renders `cover_image` and `year` if present. The backend
needs to include them in the `anime_card` SSE payload.

**Scope:** backend only. No frontend changes required — the fields are already optional in
`AnimeCard` TypeScript interface and the component handles their absence with a gradient fallback.

---

## Where to change

### `backend/services/anilist_service.py`

The `search_anime` (or equivalent lookup) method fetches AniList data. Ensure the GraphQL query
requests these fields:

```graphql
coverImage { large }
startDate { year }
```

Both are already part of the AniList API schema and cost no extra rate-limit weight.

### `backend/services/chat_service.py` (or wherever `anime_card` events are emitted)

When constructing the `AnimeCard` dict to emit as SSE:

```python
# existing fields
card = {
    "id": anime["id"],
    "title": anime["title"]["romaji"],
    "genres": anime.get("genres", []),
    "episodes": anime.get("episodes"),
    "average_score": anime.get("averageScore"),
    # NEW
    "cover_image": anime.get("coverImage", {}).get("large"),
    "year": anime.get("startDate", {}).get("year"),
}
```

Emit as:
```python
yield f"data: {json.dumps({'type': 'anime_card', 'anime': card})}\n\n"
```

---

## Verification

1. Send a chat message that triggers an anime recommendation.
2. In browser devtools → Network → SSE stream, confirm `anime_card` events contain `cover_image` URL.
3. Confirm anime card in UI renders the cover art (not the fallback gradient).

---

## Risk

- AniList `coverImage.large` can be `null` for obscure titles. Frontend already handles `null` with
  gradient fallback — safe.
- No schema migration required — purely additive SSE payload change.
