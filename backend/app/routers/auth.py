"""auth routes: AniList OAuth login/callback, logout, current user.

login sets a short-lived state cookie and 302s to AniList. callback validates the state
(fail closed), exchanges the code, upserts the user, opens a session, sets the session
cookie, and redirects to the frontend. logout deletes the session row + clears the cookie.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.cookies import (
    SESSION_COOKIE_NAME,
    STATE_COOKIE_NAME,
    clear_session_cookie,
    clear_state_cookie,
    set_session_cookie,
    set_state_cookie,
)
from app.database import get_session
from app.dependencies import get_current_user
from app.models.db.user import User
from app.models.schemas.auth import MeResponse
from app.services import auth_service

logger = logging.getLogger("kairo.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/anilist/login")
async def anilist_login() -> RedirectResponse:
    state = auth_service.generate_state()
    response = RedirectResponse(
        url=auth_service.build_authorize_url(state),
        status_code=status.HTTP_302_FOUND,
    )
    set_state_cookie(response, state)
    return response


@router.get("/anilist/callback")
async def anilist_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    state_cookie: str | None = Cookie(default=None, alias=STATE_COOKIE_NAME),
    db: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    settings = get_settings()

    # AniList denied / user cancelled.
    if error or not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="oauth denied")

    # CSRF: state must match the cookie we set at login. fail closed.
    if not auth_service.states_match(state_cookie, state):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid state")

    try:
        token = await auth_service.exchange_code(code)
        viewer = await auth_service.fetch_viewer(token.access_token)
    except auth_service.AniListAuthError as exc:
        logger.warning("anilist auth failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="anilist auth failed")

    user = await auth_service.upsert_user(db, viewer, token)
    session = await auth_service.create_session(db, user)

    response = RedirectResponse(
        url=f"{settings.frontend_origin}/chat",
        status_code=status.HTTP_302_FOUND,
    )
    clear_state_cookie(response)
    set_session_cookie(
        response,
        str(session.id),
        max_age_seconds=settings.session_ttl_days * 86400,
    )
    return response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_session),
) -> Response:
    if session_cookie:
        await auth_service.delete_session(db, session_cookie)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        anilist_id=user.anilist_id,
        anilist_connected=user.anilist_connected,
        last_synced_at=None,
    )
