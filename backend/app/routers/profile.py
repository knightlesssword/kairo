"""profile routes: sync trigger, job status, taste profile, anime list."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.dependencies import get_current_user
from app.middleware.rate_limit import rate_limit_sync
from app.models.db.profile import SyncJob, TasteProfile, UserAnimeList
from app.models.db.user import User
from app.services import sync_service

router = APIRouter(prefix="/profile", tags=["profile"])

_VALID_STATUSES = {"COMPLETED", "CURRENT", "DROPPED", "PLANNING", "PAUSED", "REPEATING"}


# ---------------------------------------------------------------------------
# response schemas
# ---------------------------------------------------------------------------

class SyncJobResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AnimeListEntryResponse(BaseModel):
    anilist_anime_id: int
    title: str | None
    genres: list[str]
    episodes: int | None
    status: str
    score: float | None
    progress: int
    updated_at: datetime | None


# ---------------------------------------------------------------------------
# sync endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/sync",
    response_model=SyncJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_sync)],
)
async def post_sync(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SyncJobResponse:
    job = await sync_service.start_sync(current_user.id, db)
    # only fire the background task for new pending jobs; deduplicated jobs are already running
    if job.status == "pending":
        background_tasks.add_task(
            sync_service.run_sync_background, job.id, current_user.id
        )
    return SyncJobResponse(
        job_id=job.id,
        status=job.status,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/sync/{job_id}", response_model=SyncJobResponse)
async def get_sync_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SyncJobResponse:
    job = await db.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    if job.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return SyncJobResponse(
        job_id=job.id,
        status=job.status,
        error=job.error,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


# ---------------------------------------------------------------------------
# profile read endpoints
# ---------------------------------------------------------------------------

@router.get("/taste")
async def get_taste(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict:
    result = await db.execute(
        select(TasteProfile).where(TasteProfile.user_id == current_user.id)
    )
    taste = result.scalar_one_or_none()
    if taste is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no taste profile yet; trigger a sync first",
        )
    return taste.profile


@router.get("/anime-list", response_model=list[AnimeListEntryResponse])
async def get_anime_list(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[AnimeListEntryResponse]:
    if status_filter is not None and status_filter not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid status '{status_filter}'; must be one of {sorted(_VALID_STATUSES)}",
        )

    query = select(UserAnimeList).where(UserAnimeList.user_id == current_user.id)
    if status_filter:
        query = query.where(UserAnimeList.status == status_filter)
    query = query.order_by(UserAnimeList.updated_at.desc().nullslast()).offset(offset).limit(limit)

    result = await db.execute(query)
    rows = result.scalars().all()

    return [
        AnimeListEntryResponse(
            anilist_anime_id=r.anilist_anime_id,
            title=r.title,
            genres=r.genres or [],
            episodes=r.episodes,
            status=r.status,
            score=r.score,
            progress=r.progress,
            updated_at=r.updated_at,
        )
        for r in rows
    ]
