"""taste profile generation from synced anime list.

input_hash guards against redundant LLM calls: if the set of (anilist_anime_id, status,
score) tuples hasn't changed since last generation, the stored profile is returned as-is.

the LLM call is stubbed with NotImplementedError until phase 3 wires up the LLM
abstraction. sync_service treats this as a soft failure and continues.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.llm.base import LLMError, Message
from app.llm.factory import get_extraction_llm
from app.models.db.profile import TasteProfile, UserAnimeList
from app.prompts.taste_extraction import TASTE_EXTRACTION_SYSTEM, build_taste_extraction_prompt

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# output schema
# ---------------------------------------------------------------------------

class WatchStyle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    prefers_completed: bool = True
    preferred_length: str = "medium"  # short | medium | long


class TasteProfileSchema(BaseModel):
    """validated shape of the LLM-generated taste profile."""
    model_config = ConfigDict(extra="ignore")
    likes: list[str]
    dislikes: list[str]
    favorites: list[str]
    watch_style: WatchStyle


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_TASTE_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "likes": {"type": "array", "items": {"type": "string"}},
        "dislikes": {"type": "array", "items": {"type": "string"}},
        "favorites": {"type": "array", "items": {"type": "string"}},
        "watch_style": {
            "type": "object",
            "properties": {
                "prefers_completed": {"type": "boolean"},
                "preferred_length": {"type": "string"},
            },
            "required": ["prefers_completed", "preferred_length"],
            "additionalProperties": False,
        },
    },
    "required": ["likes", "dislikes", "favorites", "watch_style"],
    "additionalProperties": False,
}

_STATUS_PRIORITY = {"COMPLETED": 0, "REPEATING": 1, "CURRENT": 2, "DROPPED": 3}


def _build_entries_summary(entries: list[UserAnimeList], max_entries: int = 200) -> str:
    """compact one-line-per-entry summary, prioritized by status then score."""
    ordered = sorted(
        entries,
        key=lambda e: (_STATUS_PRIORITY.get(e.status, 9), -(e.score or 0.0)),
    )[:max_entries]
    lines = []
    for e in ordered:
        genres = ",".join(e.genres or [])
        score_str = str(e.score) if e.score is not None else "unscored"
        lines.append(f"{e.title or 'Unknown'} | {e.status} | score:{score_str} | genres:{genres}")
    return "\n".join(lines)


def _compute_input_hash(entries: list[UserAnimeList]) -> str:
    """sha256 over sorted (anilist_anime_id, status, score) tuples.

    stable regardless of insertion order; None scores sort as 0.0 for consistency.
    """
    tuples = sorted(
        (e.anilist_anime_id, e.status, e.score or 0.0)
        for e in entries
    )
    raw = json.dumps(tuples, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


async def _call_llm(entries: list[UserAnimeList]) -> dict:
    """generate taste profile via the configured extraction LLM (provider-selectable
    through LLM_PROVIDER; uses llm_extraction_model with fallback to llm_model)."""
    llm = get_extraction_llm()

    entries_summary = _build_entries_summary(entries)
    log.debug("taste LLM: %d entries -> %d chars summary", len(entries), len(entries_summary))
    prompt = build_taste_extraction_prompt(entries_summary)
    messages = [Message(role="user", content=prompt)]

    response = await llm.chat(
        messages,
        system=TASTE_EXTRACTION_SYSTEM,
        response_schema=_TASTE_RESPONSE_SCHEMA,
    )

    try:
        return json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise LLMError(f"taste LLM returned non-JSON: {exc}") from exc


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

async def generate_taste_profile(
    user_id: uuid.UUID, db: AsyncSession
) -> TasteProfile | None:
    """generate (or skip) taste profile for a user.

    returns the existing or newly created TasteProfile, or None if the user has no
    scored/completed/dropped entries to work with.
    """
    result = await db.execute(
        select(UserAnimeList)
        .where(
            UserAnimeList.user_id == user_id,
            UserAnimeList.status.in_(["COMPLETED", "DROPPED", "CURRENT", "REPEATING"]),
        )
    )
    entries = list(result.scalars().all())

    if not entries:
        log.debug("taste profile: no scored/completed entries for user %s, skipping", user_id)
        return None

    input_hash = _compute_input_hash(entries)

    existing_result = await db.execute(
        select(TasteProfile).where(TasteProfile.user_id == user_id)
    )
    existing = existing_result.scalar_one_or_none()

    if existing and existing.input_hash == input_hash:
        log.debug("taste profile: input unchanged for user %s, skipping LLM", user_id)
        return existing

    raw = await _call_llm(entries)
    validated = TasteProfileSchema.model_validate(raw)

    settings = get_settings()
    used_model = settings.llm_extraction_model or settings.llm_model
    new_version = (existing.version + 1) if existing else 1

    stmt = pg_insert(TasteProfile).values(
        user_id=user_id,
        profile=validated.model_dump(),
        input_hash=input_hash,
        model=used_model,
        version=new_version,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id"],
        set_={
            "profile": stmt.excluded.profile,
            "input_hash": stmt.excluded.input_hash,
            "model": stmt.excluded.model,
            "version": stmt.excluded.version,
        },
    )
    await db.execute(stmt)
    await db.flush()

    # re-query by user_id: inserted_primary_key is unreliable in the UPDATE path of
    # ON CONFLICT DO UPDATE (PostgreSQL returns it, but SQLAlchemy's implicit RETURNING
    # behaviour on upserts is not guaranteed across driver versions).
    # populate_existing forces a reload past the ORM identity map; without it a
    # session that already loaded TasteProfile (from the `existing` check above)
    # would return the stale pre-upsert object.
    updated_result = await db.execute(
        select(TasteProfile)
        .where(TasteProfile.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    updated = updated_result.scalar_one()
    log.info("taste profile: generated v%d for user %s", new_version, user_id)
    return updated
