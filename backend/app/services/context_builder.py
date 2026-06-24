"""Context assembly for the main LLM chat call.

builds a bounded ContextBundle from:
  - static system prompt + injected taste profile + list slice + dates
  - conversation history (last N messages)
  - optional looked-up anime metadata (from AniList lookup in chat_service)

token budget enforcement trims in this priority order (cheapest to drop first):
  1. oldest conversation history messages
  2. DROPPED list slice
  3. recent COMPLETED list slice
  4. top-scored COMPLETED list slice

taste_profile and system prompt are never trimmed.

token estimation uses tiktoken (cl100k_base) with chars/4 as a fallback.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import Message as LLMMessage
from app.models.db.conversation import Message as DBMessage
from app.models.db.profile import TasteProfile, UserAnimeList
from app.prompts.system import SYSTEM_PROMPT

log = logging.getLogger(__name__)

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text))

except ImportError:
    log.warning("tiktoken not available; using chars/4 token estimate")

    def _count_tokens(text: str) -> int:  # type: ignore[misc]
        return len(text) // 4


# current season helper (static for v1; no live airing query in context builder)
def _current_season_label() -> str:
    now = datetime.now(timezone.utc)
    month = now.month
    year = now.year
    if month in (1, 2, 3):
        season = "Winter"
    elif month in (4, 5, 6):
        season = "Spring"
    elif month in (7, 8, 9):
        season = "Summer"
    else:
        season = "Fall"
    return f"{season} {year}"


@dataclass
class ContextBundle:
    """assembled, token-budgeted context ready for the LLM call."""
    system_prompt: str                    # system message (static + injected blocks)
    history: list[LLMMessage]            # conversation turns (user/assistant, oldest first)
    looked_up_anime: list[dict]          # AniList metadata for named titles; may be empty
    token_estimate: int
    context_snapshot: dict = field(default_factory=dict)  # persisted in messages.context_used


# ---------------------------------------------------------------------------
# list slice formatting
# ---------------------------------------------------------------------------

def _format_entry(e: UserAnimeList) -> str:
    genres = ",".join(e.genres or [])
    score = f"score:{e.score:.1f}" if e.score else "unscored"
    return f"{e.title or 'Unknown'} | {e.status} | {score} | genres:{genres}"


async def _load_list_slices(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> tuple[list[UserAnimeList], list[UserAnimeList], list[UserAnimeList], dict[str, int]]:
    """returns (top_scored, recent_completed, dropped, status_counts)."""
    # top 30 completed by score
    top_result = await db.execute(
        select(UserAnimeList)
        .where(
            UserAnimeList.user_id == user_id,
            UserAnimeList.status == "COMPLETED",
            UserAnimeList.score.isnot(None),
        )
        .order_by(UserAnimeList.score.desc())
        .limit(30)
    )
    top = list(top_result.scalars().all())

    # recent 20 completed (by updated_at)
    recent_result = await db.execute(
        select(UserAnimeList)
        .where(
            UserAnimeList.user_id == user_id,
            UserAnimeList.status == "COMPLETED",
        )
        .order_by(UserAnimeList.updated_at.desc())
        .limit(20)
    )
    recent = list(recent_result.scalars().all())

    # 15 dropped
    dropped_result = await db.execute(
        select(UserAnimeList)
        .where(
            UserAnimeList.user_id == user_id,
            UserAnimeList.status == "DROPPED",
        )
        .order_by(UserAnimeList.updated_at.desc())
        .limit(15)
    )
    dropped = list(dropped_result.scalars().all())

    # aggregate counts per status
    all_result = await db.execute(
        select(UserAnimeList.status)
        .where(UserAnimeList.user_id == user_id)
    )
    counts: dict[str, int] = {}
    for (status,) in all_result.all():
        counts[status] = counts.get(status, 0) + 1

    return top, recent, dropped, counts


# ---------------------------------------------------------------------------
# system message assembly
# ---------------------------------------------------------------------------

def _build_system_message(
    taste_profile: dict | None,
    top: list[UserAnimeList],
    recent: list[UserAnimeList],
    dropped: list[UserAnimeList],
    status_counts: dict[str, int],
    looked_up_anime: list[dict],
    current_date: str,
    current_season: str,
) -> str:
    parts = [SYSTEM_PROMPT, ""]

    parts.append(f"CURRENT DATE: {current_date}")
    parts.append(f"CURRENT SEASON: {current_season}")
    parts.append("")

    if taste_profile:
        import json
        parts.append("TASTE PROFILE:")
        parts.append(json.dumps(taste_profile, indent=2))
        parts.append("")

    if status_counts:
        counts_str = " | ".join(f"{k}:{v}" for k, v in sorted(status_counts.items()))
        parts.append(f"LIST SUMMARY: {counts_str}")
        parts.append("")

    if top:
        parts.append("TOP RATED (completed, by score):")
        parts.extend(f"  {_format_entry(e)}" for e in top)
        parts.append("")

    if recent:
        parts.append("RECENTLY COMPLETED:")
        parts.extend(f"  {_format_entry(e)}" for e in recent)
        parts.append("")

    if dropped:
        parts.append("DROPPED:")
        parts.extend(f"  {_format_entry(e)}" for e in dropped)
        parts.append("")

    if looked_up_anime:
        import json
        parts.append("LOOKED UP ANIME:")
        for anime in looked_up_anime:
            parts.append(f"  {json.dumps(anime)}")
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# history loading
# ---------------------------------------------------------------------------

async def _load_history(
    conversation_id: uuid.UUID,
    db: AsyncSession,
    limit: int,
) -> list[LLMMessage]:
    result = await db.execute(
        select(DBMessage)
        .where(DBMessage.conversation_id == conversation_id)
        .order_by(DBMessage.created_at.asc())
        .limit(limit)
    )
    return [
        LLMMessage(role=m.role, content=m.content)
        for m in result.scalars().all()
    ]


# ---------------------------------------------------------------------------
# main builder
# ---------------------------------------------------------------------------

async def build_context(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: AsyncSession,
    max_tokens: int,
    history_limit: int,
    looked_up_anime: list[dict] | None = None,
) -> ContextBundle:
    looked_up_anime = looked_up_anime or []

    # load taste profile
    taste_result = await db.execute(
        select(TasteProfile).where(TasteProfile.user_id == user_id)
    )
    taste_row = taste_result.scalar_one_or_none()
    taste_profile = taste_row.profile if taste_row else None

    # load list slices
    top, recent, dropped, status_counts = await _load_list_slices(user_id, db)

    # load history
    history = await _load_history(conversation_id, db, history_limit)

    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    current_season = _current_season_label()

    # assemble and check budget, trimming in priority order
    # trim 1: drop oldest history messages one at a time
    # trim 2: drop entire dropped slice
    # trim 3: drop recent slice
    # trim 4: drop top slice
    # taste_profile + system base are never trimmed

    def _assemble(
        top_s: list[UserAnimeList],
        recent_s: list[UserAnimeList],
        dropped_s: list[UserAnimeList],
        hist: list[LLMMessage],
    ) -> tuple[str, int]:
        sys_msg = _build_system_message(
            taste_profile, top_s, recent_s, dropped_s,
            status_counts, looked_up_anime, current_date, current_season,
        )
        hist_tokens = sum(_count_tokens(m.content) for m in hist)
        total = _count_tokens(sys_msg) + hist_tokens
        return sys_msg, total

    sys_msg, token_est = _assemble(top, recent, dropped, history)

    # trim oldest history first
    while token_est > max_tokens and len(history) > 1:
        history = history[1:]
        sys_msg, token_est = _assemble(top, recent, dropped, history)

    # trim dropped slice
    if token_est > max_tokens and dropped:
        dropped = []
        sys_msg, token_est = _assemble(top, recent, dropped, history)

    # trim recent slice
    if token_est > max_tokens and recent:
        recent = []
        sys_msg, token_est = _assemble(top, recent, dropped, history)

    # trim top slice (last resort)
    if token_est > max_tokens and top:
        top = []
        sys_msg, token_est = _assemble(top, recent, dropped, history)

    if token_est > max_tokens:
        log.warning(
            "context still over budget after all trims: %d > %d tokens",
            token_est, max_tokens,
        )

    snapshot = {
        "taste_present": taste_profile is not None,
        "top_count": len(top),
        "recent_count": len(recent),
        "dropped_count": len(dropped),
        "history_count": len(history),
        "looked_up_count": len(looked_up_anime),
        "token_estimate": token_est,
    }

    return ContextBundle(
        system_prompt=sys_msg,
        history=history,
        looked_up_anime=looked_up_anime,
        token_estimate=token_est,
        context_snapshot=snapshot,
    )
