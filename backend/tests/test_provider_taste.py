"""provider swap smoke + taste schema carry-over.

provider swap: factory.get_answer_llm / get_extraction_llm return OllamaProvider
when called with an ollama Settings object (no env needed; settings passed directly).

taste carry-over: generate_taste_profile skips the LLM call when the entry hash
hasn't changed since the stored profile was generated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.llm.factory import get_answer_llm, get_extraction_llm
from app.llm.ollama import OllamaProvider
from app.models.db.profile import TasteProfile, UserAnimeList
from app.models.db.user import User
from app.services.taste_service import _compute_input_hash, generate_taste_profile

_NOW = datetime.now(timezone.utc)


def _ollama_settings() -> Settings:
    """minimal Settings constructed without env; only the fields _build_provider uses."""
    return Settings.model_construct(
        llm_provider="ollama",
        llm_model="llama3",
        llm_extraction_model="",
        ollama_base_url="http://localhost:11434",
    )


# ---------------------------------------------------------------------------
# provider swap smoke (sync, no DB needed)
# ---------------------------------------------------------------------------

def test_answer_llm_is_ollama_when_configured():
    assert isinstance(get_answer_llm(settings=_ollama_settings()), OllamaProvider)


def test_extraction_llm_is_ollama_when_configured():
    assert isinstance(get_extraction_llm(settings=_ollama_settings()), OllamaProvider)


# ---------------------------------------------------------------------------
# taste schema carry-over
# ---------------------------------------------------------------------------

async def _seed_user(db: AsyncSession) -> uuid.UUID:
    user = User(anilist_id=9001, username="taste_user", access_token_enc="enc")
    db.add(user)
    await db.flush()
    uid = user.id
    await db.commit()
    return uid


async def _seed_entries(db: AsyncSession, user_id: uuid.UUID) -> list[UserAnimeList]:
    for i in range(5):
        db.add(UserAnimeList(
            user_id=user_id,
            anilist_anime_id=20000 + i,
            title=f"Test Anime {i}",
            status="COMPLETED",
            score=8.0,
            progress=12,
            updated_at=_NOW,
        ))
    await db.commit()
    result = await db.execute(
        select(UserAnimeList).where(UserAnimeList.user_id == user_id)
    )
    return list(result.scalars().all())


async def _seed_taste_profile(
    db: AsyncSession, user_id: uuid.UUID, input_hash: str, version: int = 1
) -> TasteProfile:
    profile_data = {
        "likes": ["action"],
        "dislikes": ["mecha"],
        "favorites": ["FMA"],
        "watch_style": {"prefers_completed": True, "preferred_length": "medium"},
    }
    stmt = pg_insert(TasteProfile).values(
        user_id=user_id,
        profile=profile_data,
        input_hash=input_hash,
        model="test-model",
        version=version,
    )
    await db.execute(stmt)
    await db.commit()
    result = await db.execute(select(TasteProfile).where(TasteProfile.user_id == user_id))
    return result.scalar_one()


async def test_skips_llm_when_input_hash_unchanged(db):
    uid = await _seed_user(db)
    entries = await _seed_entries(db, uid)
    current_hash = _compute_input_hash(entries)
    existing = await _seed_taste_profile(db, uid, input_hash=current_hash)

    with patch("app.services.taste_service._call_llm", new_callable=AsyncMock) as mock_llm:
        result = await generate_taste_profile(uid, db)
        mock_llm.assert_not_called()

    assert result is not None
    assert result.id == existing.id
    assert result.input_hash == current_hash


async def test_calls_llm_and_bumps_version_when_hash_changed(db):
    uid = await _seed_user(db)
    entries = await _seed_entries(db, uid)
    await _seed_taste_profile(db, uid, input_hash="0" * 64, version=1)

    new_profile = {
        "likes": ["comedy"],
        "dislikes": [],
        "favorites": ["One Piece"],
        "watch_style": {"prefers_completed": False, "preferred_length": "long"},
    }

    with patch(
        "app.services.taste_service._call_llm",
        new_callable=AsyncMock,
        return_value=new_profile,
    ) as mock_llm:
        result = await generate_taste_profile(uid, db)
        mock_llm.assert_called_once()

    assert result is not None
    assert result.input_hash == _compute_input_hash(entries)
    assert result.profile["likes"] == ["comedy"]
    assert result.version == 2
