"""Chat service: extract -> lookup -> assemble -> stream.

message flow:
  1. entity extraction: always run LLM call -> {anime_titles, wants_current_season}
  2. AniList metadata lookup: if anime_titles detected (no gate)
  3. user list entry lookup: for detected titles, fetch exact rows from user_anime_list
  4. context assembly via context_builder
  5. main LLM streaming call
  6. yield SSE-ready dicts: {type: delta|anime_card|done|error, ...}
  7. caller persists user + assistant messages after stream completes

the AniList lookup is skipped gracefully if the user's token is disconnected.
extraction failures log + continue without lookup.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.base import LLMError, Message as LLMMessage
from app.llm.factory import get_answer_llm, get_extraction_llm
from app.models.db.profile import UserAnimeList
from app.models.db.user import User
from app.prompts.entity_extraction import (
    ENTITY_EXTRACTION_SCHEMA,
    ENTITY_EXTRACTION_SYSTEM,
    build_entity_extraction_prompt,
)
from app.services.anilist_guard import AniListDisconnected, assert_token_valid
from app.services.anilist_service import (
    AniListError,
    AnimeSearchResult,
    fetch_current_season,
    search_anime,
)
from app.services.context_builder import build_context
from app.services.crypto import decrypt_token

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# extraction output schema
# ---------------------------------------------------------------------------

class _ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    anime_titles: list[str] = []
    wants_current_season: bool = False


# ---------------------------------------------------------------------------
# extraction step
# ---------------------------------------------------------------------------

async def _extract_entities(message: str) -> _ExtractionResult | None:
    """run cheap extraction LLM call. returns None on any failure (gate treated as miss)."""
    try:
        llm = get_extraction_llm()
        resp = await llm.chat(
            messages=[LLMMessage(role="user", content=build_entity_extraction_prompt(message))],
            system=ENTITY_EXTRACTION_SYSTEM,
            response_schema=ENTITY_EXTRACTION_SCHEMA,
        )
        raw = json.loads(resp.content)
        return _ExtractionResult.model_validate(raw)
    except (LLMError, json.JSONDecodeError, ValidationError) as exc:
        log.warning("entity extraction failed (treating as gate miss): %s", exc)
        return None


# ---------------------------------------------------------------------------
# user list entry lookup step
# ---------------------------------------------------------------------------

async def _lookup_user_entries(
    user_id: uuid.UUID,
    db: AsyncSession,
    anilist_ids: list[int],
    title_fallback: list[str],
) -> list[dict]:
    """look up user_anime_list rows for specifically mentioned titles.

    prefers anilist_id match (authoritative). falls back to case-insensitive
    title match when ids are unavailable (no AniList token or lookup miss).
    """
    if anilist_ids:
        result = await db.execute(
            select(UserAnimeList).where(
                UserAnimeList.user_id == user_id,
                UserAnimeList.anilist_anime_id.in_(anilist_ids),
            )
        )
    elif title_fallback:
        result = await db.execute(
            select(UserAnimeList).where(
                UserAnimeList.user_id == user_id,
                or_(*[UserAnimeList.title.ilike(t) for t in title_fallback]),
            )
        )
    else:
        return []

    rows = result.scalars().all()
    return [
        {
            "title": r.title,
            "status": r.status,
            "score": r.score,
            "progress": r.progress,
            "updated_at": r.updated_at.date().isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# AniList lookup step
# ---------------------------------------------------------------------------

async def _lookup_anime(
    user: User,
    db: AsyncSession,
    extraction: _ExtractionResult,
) -> list[dict]:
    """perform AniList lookups. at most 2 queries. skips gracefully on token issues."""
    results: list[AnimeSearchResult] = []

    try:
        await assert_token_valid(db, user)
        token = decrypt_token(user.access_token_enc)
    except (AniListDisconnected, Exception) as exc:
        log.info("skipping AniList lookup (token unavailable): %s", exc)
        return []

    query_count = 0

    if extraction.anime_titles and query_count < 2:
        try:
            found = await search_anime(token, extraction.anime_titles)
            results.extend(found)
            query_count += 1
        except AniListError as exc:
            log.warning("AniList title search failed: %s", exc)

    if extraction.wants_current_season and query_count < 2:
        try:
            season = await fetch_current_season(token)
            results.extend(season)
            query_count += 1
        except AniListError as exc:
            log.warning("AniList season fetch failed: %s", exc)

    return [r.to_dict() for r in results]


# ---------------------------------------------------------------------------
# main streaming entry point
# ---------------------------------------------------------------------------

async def stream_chat(
    user: User,
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_message: str,
) -> AsyncGenerator[dict, None]:
    """yields SSE event dicts. caller must collect assistant content and persist messages.

    event shapes:
      {"type": "delta", "content": "<str>"}
      {"type": "anime_card", "anime": {id, title, genres, episodes, average_score}}
      {"type": "done"}
      {"type": "error", "message": "<str>"}
    """
    settings = get_settings()

    # step 1: always extract entities
    looked_up_anime: list[dict] = []
    user_entries: list[dict] = []
    extraction = await _extract_entities(user_message)
    if extraction and (extraction.anime_titles or extraction.wants_current_season):
        # step 2: AniList metadata lookup whenever titles detected
        looked_up_anime = await _lookup_anime(user, db, extraction)

        # step 3: user list entry lookup for mentioned titles
        # prefer anilist_id match; fall back to title when lookup was skipped
        anilist_ids = [a["id"] for a in looked_up_anime if "id" in a]
        user_entries = await _lookup_user_entries(
            user.id,
            db,
            anilist_ids=anilist_ids,
            title_fallback=extraction.anime_titles if not anilist_ids else [],
        )

    # emit anime_card events before the stream starts so the frontend can render them
    for anime in looked_up_anime:
        yield {"type": "anime_card", "anime": anime}

    # step 4: context assembly
    try:
        bundle = await build_context(
            user_id=user.id,
            conversation_id=conversation_id,
            db=db,
            max_tokens=settings.max_context_tokens,
            history_limit=settings.history_message_limit,
            looked_up_anime=looked_up_anime,
            user_entries=user_entries,
        )
    except Exception as exc:
        log.error("context build failed: %s", exc)
        yield {"type": "error", "message": "failed to assemble context"}
        return

    # step 5: assemble messages for LLM
    user_turn = LLMMessage(role="user", content=user_message)
    messages = [*bundle.history, user_turn]

    # step 6: stream
    log.debug(
        "final_messages | system=%d chars | history=%d | user=%r | looked_up=%d",
        len(bundle.system_prompt),
        len(bundle.history),
        user_message[:120],
        len(looked_up_anime),
    )
    if log.isEnabledFor(logging.DEBUG):
        log.debug("system_prompt_sent:\n%s", bundle.system_prompt)
    try:
        llm = get_answer_llm()
        async for delta in llm.stream(messages, system=bundle.system_prompt):
            yield {"type": "delta", "content": delta}
    except LLMError as exc:
        log.error("LLM stream error: %s", exc)
        yield {"type": "error", "message": f"LLM error: {exc}"}
        return

    yield {"type": "done"}
