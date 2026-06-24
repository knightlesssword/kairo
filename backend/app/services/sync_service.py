"""AniList sync: in-process asyncio task with postgres job state.

design:
- start_sync() creates the SyncJob row and returns it. the router fires
  run_sync_background() via FastAPI BackgroundTasks (runs after response + session commit),
  so the background task always sees a committed job row.
- run_sync_background() opens its own DB session; it must not share the request session.
- upserts are idempotent: INSERT ... ON CONFLICT DO UPDATE, so a re-sync is safe.
- stale_job_reaper() marks stuck pending/running jobs failed; called before start_sync.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import SessionFactory
from app.models.db.profile import AnilistProfile, SyncJob, UserAnimeList
from app.models.db.user import User
from app.services import anilist_service, taste_service
from app.services.anilist_guard import AniListDisconnected, assert_token_valid, handle_unauthorized
from app.services.anilist_service import AniListAuthError
from app.services.crypto import decrypt_token

log = logging.getLogger(__name__)

_ACTIVE_STATUSES = ("pending", "running")


# ---------------------------------------------------------------------------
# stale job reaper
# ---------------------------------------------------------------------------

async def stale_job_reaper(db: AsyncSession) -> int:
    """mark pending/running jobs older than SYNC_STALE_SECONDS as failed.

    returns the number of jobs reaped. idempotent; safe to call before every sync.
    """
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.sync_stale_seconds)

    stmt = (
        update(SyncJob)
        .where(
            SyncJob.status.in_(_ACTIVE_STATUSES),
            SyncJob.created_at < cutoff,
        )
        .values(
            status="failed",
            error="reaped: job stalled (process restart or timeout)",
            finished_at=datetime.now(timezone.utc),
        )
        .returning(SyncJob.id)
    )
    result = await db.execute(stmt)
    reaped = len(result.fetchall())
    if reaped:
        log.warning("stale_job_reaper: marked %d stalled sync job(s) as failed", reaped)
    return reaped


# ---------------------------------------------------------------------------
# job management
# ---------------------------------------------------------------------------

async def start_sync(user_id: uuid.UUID, db: AsyncSession) -> SyncJob:
    """return existing active job (dedupe) or create a new pending one.

    does NOT fire the background task; caller (router) must call run_sync_background
    via FastAPI BackgroundTasks after this returns.
    """
    await stale_job_reaper(db)

    result = await db.execute(
        select(SyncJob)
        .where(SyncJob.user_id == user_id, SyncJob.status.in_(_ACTIVE_STATUSES))
        .order_by(SyncJob.created_at.desc())
        .limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    job = SyncJob(user_id=user_id, status="pending")
    db.add(job)
    await db.flush()  # assigns id; request session commits after this returns
    return job


# ---------------------------------------------------------------------------
# background task (runs in its own session, post-commit)
# ---------------------------------------------------------------------------

async def run_sync_background(job_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """the actual sync work. must be called via FastAPI BackgroundTasks, not directly."""
    async with SessionFactory() as db:
        try:
            await db.begin()
            await _run_sync(db, job_id, user_id)
            await db.commit()
        except Exception:
            await db.rollback()
            # exception already logged + job marked failed inside _run_sync
            raise


async def _run_sync(db: AsyncSession, job_id: uuid.UUID, user_id: uuid.UUID) -> None:
    job = await db.get(SyncJob, job_id)
    if job is None:
        log.error("sync job %s not found; skipping", job_id)
        return

    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    await db.flush()

    try:
        user = await db.get(User, user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")

        await assert_token_valid(db, user)
        token = decrypt_token(user.access_token_enc)

        # fetch
        try:
            entries = await anilist_service.fetch_anime_list(token, user.anilist_id)
            stats = await anilist_service.fetch_viewer_stats(token)
        except AniListAuthError:
            await handle_unauthorized(db, user)
            raise  # AniListDisconnected now raised by handle_unauthorized

        log.info("sync user=%s: fetched %d anime entries", user_id, len(entries))

        # upsert anime list
        if entries:
            now = datetime.now(timezone.utc)
            rows = [
                {
                    "user_id": user_id,
                    "anilist_anime_id": e.mediaId,
                    "title": e.title,
                    "genres": e.genres or [],
                    "episodes": e.episodes,
                    "status": e.status,
                    "score": e.score,
                    "progress": e.progress,
                    "updated_at": e.updated_at or now,
                }
                for e in entries
            ]
            stmt = pg_insert(UserAnimeList).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_user_anime",
                set_={
                    "title": stmt.excluded.title,
                    "genres": stmt.excluded.genres,
                    "episodes": stmt.excluded.episodes,
                    "status": stmt.excluded.status,
                    "score": stmt.excluded.score,
                    "progress": stmt.excluded.progress,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await db.execute(stmt)

        # upsert anilist_profiles
        profile_stmt = pg_insert(AnilistProfile).values(
            user_id=user_id,
            raw_stats=stats.model_dump(),
            anime_count=stats.anime_count,
            mean_score=stats.mean_score,
            synced_at=datetime.now(timezone.utc),
        )
        profile_stmt = profile_stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "raw_stats": profile_stmt.excluded.raw_stats,
                "anime_count": profile_stmt.excluded.anime_count,
                "mean_score": profile_stmt.excluded.mean_score,
                "synced_at": profile_stmt.excluded.synced_at,
            },
        )
        await db.execute(profile_stmt)

        # taste profile generation (soft failure: LLM not available until phase 3)
        try:
            await taste_service.generate_taste_profile(user_id, db)
        except NotImplementedError:
            log.debug("taste profile generation skipped: LLM not yet implemented")
        except Exception as exc:
            log.warning("taste profile generation failed (non-fatal): %s", exc)

        job.status = "completed"
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
        log.info("sync user=%s job=%s completed (%d entries)", user_id, job_id, len(entries))

    except (AniListDisconnected, Exception) as exc:
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = datetime.now(timezone.utc)
        await db.flush()
        log.error("sync user=%s job=%s failed: %s", user_id, job_id, exc)
        raise
