"""Chat service: extract -> lookup -> assemble -> stream.

message flow:
  1. entity extraction: always run LLM call -> {anime_titles, wants_current_season, intent}
  2. AniList lookup: if anime_titles detected, always lookup (no gate)
  3. context assembly via context_builder
  4. main LLM streaming call
  5. yield SSE-ready dicts: {type: delta|anime_card|done|error, ...}
  6. caller persists user + assistant messages after stream completes

the AniList lookup is skipped gracefully if the user's token is disconnected.
extraction failures log + continue without lookup.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.base import LLMError, Message as LLMMessage
from app.llm.factory import get_answer_llm, get_extraction_llm
from app.models.db.user import User
from app.prompts.entity_extraction import (
    ENTITY_EXTRACTION_SCHEMA,
    ENTITY_EXTRACTION_SYSTEM,
    build_entity_extraction_prompt,
)
from app.prompts.system import SYSTEM_PROMPT
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
    extraction = await _extract_entities(user_message)
    if extraction and (extraction.anime_titles or extraction.wants_current_season):
        # step 2: AniList lookup whenever titles detected
        looked_up_anime = await _lookup_anime(user, db, extraction)

    # emit anime_card events before the stream starts so the frontend can render them
    for anime in looked_up_anime:
        yield {"type": "anime_card", "anime": anime}

    # step 3: context assembly
    try:
        bundle = await build_context(
            user_id=user.id,
            conversation_id=conversation_id,
            db=db,
            max_tokens=settings.max_context_tokens,
            history_limit=settings.history_message_limit,
            looked_up_anime=looked_up_anime,
        )
    except Exception as exc:
        log.error("context build failed: %s", exc)
        yield {"type": "error", "message": "failed to assemble context"}
        return

    # step 4: assemble messages for LLM
    user_turn = LLMMessage(role="user", content=user_message)
    messages = [*bundle.history, user_turn]

    # step 5: stream
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
