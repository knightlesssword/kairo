"""context builder: token budget enforcement.

build_context is called directly against the test DB (no HTTP, no LLM).
verifies that the trimming logic runs in the documented priority order and that
the context_snapshot counters reflect what was actually kept.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.conversation import Conversation, Message
from app.models.db.profile import UserAnimeList
from app.models.db.user import User
from app.services.context_builder import build_context

_NOW = datetime.now(timezone.utc)


async def _seed_user(db: AsyncSession, anilist_id: int = 7001) -> uuid.UUID:
    user = User(anilist_id=anilist_id, username="ctx_user", access_token_enc="enc")
    db.add(user)
    await db.flush()
    uid = user.id
    await db.commit()
    return uid


async def _seed_conversation(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    conv = Conversation(user_id=user_id)
    db.add(conv)
    await db.flush()
    cid = conv.id
    await db.commit()
    return cid


async def _add_messages(db: AsyncSession, conv_id: uuid.UUID, count: int) -> None:
    for i in range(count):
        db.add(Message(
            conversation_id=conv_id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"message body {i} " * 40,  # ~200 chars each
        ))
    await db.commit()


async def _add_entries(
    db: AsyncSession,
    user_id: uuid.UUID,
    count: int,
    status: str = "COMPLETED",
    score: float | None = 7.5,
    id_start: int = 10000,
) -> None:
    for i in range(count):
        db.add(UserAnimeList(
            user_id=user_id,
            anilist_anime_id=id_start + i,
            title=f"Anime {i} " * 8,
            genres=["Action"],
            status=status,
            score=score,
            progress=12,
            updated_at=_NOW,
        ))
    await db.commit()


# ---------------------------------------------------------------------------

async def test_empty_list_no_history_fits_large_budget(db):
    uid = await _seed_user(db)
    cid = await _seed_conversation(db, uid)

    bundle = await build_context(
        user_id=uid,
        conversation_id=cid,
        db=db,
        max_tokens=8000,
        history_limit=20,
    )

    snap = bundle.context_snapshot
    assert bundle.token_estimate > 0          # system prompt always present
    assert bundle.token_estimate <= 8000
    assert snap["history_count"] == 0
    assert snap["top_count"] == 0
    assert snap["dropped_count"] == 0


async def test_tight_budget_trims_all_slices(db):
    uid = await _seed_user(db)
    cid = await _seed_conversation(db, uid)

    await _add_entries(db, uid, 30, status="COMPLETED", score=8.0, id_start=10000)
    await _add_entries(db, uid, 15, status="DROPPED", score=None, id_start=20000)
    await _add_messages(db, cid, 10)

    bundle = await build_context(
        user_id=uid,
        conversation_id=cid,
        db=db,
        max_tokens=1,   # impossible budget -> forces every trim pass
        history_limit=20,
    )

    snap = bundle.context_snapshot
    assert snap["dropped_count"] == 0
    assert snap["recent_count"] == 0
    assert snap["top_count"] == 0
    # history trimmed down to min 1 (loop guard is `len > 1`)
    assert snap["history_count"] <= 1


async def test_large_budget_keeps_all_content(db):
    uid = await _seed_user(db)
    cid = await _seed_conversation(db, uid)

    await _add_entries(db, uid, 10, status="COMPLETED", score=8.0, id_start=10000)
    await _add_entries(db, uid, 5, status="DROPPED", score=None, id_start=20000)
    await _add_messages(db, cid, 4)

    bundle = await build_context(
        user_id=uid,
        conversation_id=cid,
        db=db,
        max_tokens=50_000,
        history_limit=20,
    )

    snap = bundle.context_snapshot
    assert snap["top_count"] == 10     # 10 completed with scores
    assert snap["dropped_count"] == 5
    assert snap["history_count"] == 4
    assert bundle.token_estimate <= 50_000


async def test_trim_order_drops_oldest_history_first(db):
    """history is trimmed before list slices; with a budget that fits slices but
    not history, the snapshot should show history reduced but slices intact."""
    uid = await _seed_user(db)
    cid = await _seed_conversation(db, uid)

    # add 2 entries only (small) + 6 long history messages
    await _add_entries(db, uid, 2, status="COMPLETED", score=8.0)
    await _add_messages(db, cid, 6)

    # base system prompt + 2 entries fits comfortably; 6 history messages push it over
    # we need a budget just large enough for the system prompt + slices but not history
    # use a generous fixed budget that our 2-entry system message fits under
    bundle_full = await build_context(
        user_id=uid, conversation_id=cid, db=db, max_tokens=50_000, history_limit=20,
    )
    tight = bundle_full.token_estimate - 100  # just below the full estimate

    bundle_tight = await build_context(
        user_id=uid, conversation_id=cid, db=db, max_tokens=tight, history_limit=20,
    )

    snap = bundle_tight.context_snapshot
    # slices survived; only history was reduced
    assert snap["top_count"] == 2
    assert snap["history_count"] < 6
