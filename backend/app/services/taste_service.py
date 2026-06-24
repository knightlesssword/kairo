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

from app.models.db.profile import TasteProfile, UserAnimeList

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
    """generate taste profile via LLM. stub until phase 3.

    phase 3 will replace this with: build prompt -> call llm provider -> parse json.
    """
    raise NotImplementedError("LLM provider not yet wired (phase 3)")


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

async def generate_taste_profile(
    user_id: uuid.UUID, db: AsyncSession
) -> TasteProfile | None:
    """generate (or skip) taste profile for a user.

    returns the existing or newly created TasteProfile, or None if the user has no
    scored/completed/dropped entries to work with.

    raises NotImplementedError until phase 3 wires the LLM.
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

    # LLM call (raises NotImplementedError until phase 3)
    raw = await _call_llm(entries)
    validated = TasteProfileSchema.model_validate(raw)

    new_version = (existing.version + 1) if existing else 1

    stmt = pg_insert(TasteProfile).values(
        user_id=user_id,
        profile=validated.model_dump(),
        input_hash=input_hash,
        model="",  # phase 3 will fill this from LLM_MODEL env
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
    result = await db.execute(stmt)
    await db.flush()

    # reload to return the ORM object
    updated = await db.get(TasteProfile, result.inserted_primary_key[0])
    log.info("taste profile: generated v%d for user %s", new_version, user_id)
    return updated
