"""sync recovery: stale job reaper marks stuck jobs failed; active-job dedupe.

service functions are tested directly without firing run_sync_background (which
needs a real AniList token). the background path is integration-level and
deferred to manual testing.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.profile import SyncJob
from app.models.db.user import User
from app.services.sync_service import start_sync, stale_job_reaper

# well past the default 600s stale threshold
_STALE = datetime.now(timezone.utc) - timedelta(hours=2)


async def _seed_user(db: AsyncSession) -> uuid.UUID:
    user = User(anilist_id=8001, username="sync_user", access_token_enc="enc")
    db.add(user)
    await db.flush()
    uid = user.id
    await db.commit()
    return uid


async def _seed_job(
    db: AsyncSession,
    user_id: uuid.UUID,
    status: str,
    created_at: datetime | None = None,
) -> SyncJob:
    kwargs: dict = {"user_id": user_id, "status": status}
    if created_at is not None:
        kwargs["created_at"] = created_at
    job = SyncJob(**kwargs)
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# stale_job_reaper
# ---------------------------------------------------------------------------

async def test_reaper_marks_stale_pending_job_failed(db):
    uid = await _seed_user(db)
    job = await _seed_job(db, uid, status="pending", created_at=_STALE)

    reaped = await stale_job_reaper(db)

    assert reaped == 1
    await db.refresh(job)
    assert job.status == "failed"
    assert job.error is not None and "reaped" in job.error
    assert job.finished_at is not None


async def test_reaper_marks_stale_running_job_failed(db):
    uid = await _seed_user(db)
    job = await _seed_job(db, uid, status="running", created_at=_STALE)

    reaped = await stale_job_reaper(db)

    assert reaped == 1
    await db.refresh(job)
    assert job.status == "failed"


async def test_reaper_ignores_fresh_pending_job(db):
    uid = await _seed_user(db)
    await _seed_job(db, uid, status="pending")  # created_at = now (default)

    reaped = await stale_job_reaper(db)

    assert reaped == 0


async def test_reaper_ignores_completed_job_regardless_of_age(db):
    uid = await _seed_user(db)
    await _seed_job(db, uid, status="completed", created_at=_STALE)

    reaped = await stale_job_reaper(db)

    assert reaped == 0


async def test_reaper_ignores_failed_job_regardless_of_age(db):
    uid = await _seed_user(db)
    await _seed_job(db, uid, status="failed", created_at=_STALE)

    reaped = await stale_job_reaper(db)

    assert reaped == 0


# ---------------------------------------------------------------------------
# start_sync active-job dedupe
# ---------------------------------------------------------------------------

async def test_start_sync_returns_existing_pending_job(db):
    uid = await _seed_user(db)
    existing = await _seed_job(db, uid, status="pending")  # fresh -> survives reaper

    returned = await start_sync(uid, db)

    assert returned.id == existing.id
    count = await db.execute(select(SyncJob).where(SyncJob.user_id == uid))
    assert len(count.scalars().all()) == 1


async def test_start_sync_returns_existing_running_job(db):
    uid = await _seed_user(db)
    existing = await _seed_job(db, uid, status="running")  # fresh running job

    returned = await start_sync(uid, db)

    assert returned.id == existing.id


async def test_start_sync_creates_new_job_when_previous_completed(db):
    uid = await _seed_user(db)
    await _seed_job(db, uid, status="completed")

    new_job = await start_sync(uid, db)
    await db.commit()

    assert new_job.status == "pending"
    result = await db.execute(select(SyncJob).where(SyncJob.user_id == uid))
    assert len(result.scalars().all()) == 2


async def test_start_sync_creates_new_job_when_previous_failed(db):
    uid = await _seed_user(db)
    await _seed_job(db, uid, status="failed")

    new_job = await start_sync(uid, db)
    await db.commit()

    assert new_job.status == "pending"
    result = await db.execute(select(SyncJob).where(SyncJob.user_id == uid))
    assert len(result.scalars().all()) == 2
