"""shared FastAPI dependencies: authenticated user resolution.

`get_current_user` is the single gate for authenticated routes. it reads the session id
from the httponly cookie, validates the session row, slides its expiry, and returns the
owning user. user identity always comes from the session here, never from request input.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.cookies import SESSION_COOKIE_NAME
from app.database import get_session
from app.models.db.user import Session, User

_UNAUTH = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")


async def get_current_user(
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: AsyncSession = Depends(get_session),
) -> User:
    if not session_cookie:
        raise _UNAUTH

    try:
        session_id = uuid.UUID(session_cookie)
    except ValueError:
        # malformed cookie value; treat as unauthenticated, don't 500.
        raise _UNAUTH from None

    session = await db.get(Session, session_id)
    if session is None:
        raise _UNAUTH

    now = datetime.now(timezone.utc)
    if session.expires_at <= now:
        # expired: clean up the dead row so it can't be reused, then reject.
        await db.delete(session)
        raise _UNAUTH

    # sliding expiry: every authenticated request extends the window from now.
    settings = get_settings()
    session.last_used_at = now
    session.expires_at = now + timedelta(days=settings.session_ttl_days)

    user = await db.get(User, session.user_id)
    if user is None:
        # orphaned session (user deleted); reject.
        raise _UNAUTH
    return user
