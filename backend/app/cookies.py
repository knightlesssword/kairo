"""cookie names + set/clear helpers for session and oauth-state cookies.

centralised so the auth router (set/clear) and the current_user dependency (read) agree
on names and flags. all cookies are httponly + samesite=lax; secure is on in production
(see settings.cookie_secure) and off on http localhost so dev login works.
"""

from __future__ import annotations

from fastapi import Response

from app.config import get_settings

SESSION_COOKIE_NAME = "kairo_session"
STATE_COOKIE_NAME = "kairo_oauth_state"

# oauth state is short-lived: only needs to survive the round-trip to AniList and back.
STATE_COOKIE_MAX_AGE = 600  # seconds


def set_session_cookie(response: Response, session_id: str, max_age_seconds: int) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=max_age_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def set_state_cookie(response: Response, state: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=STATE_COOKIE_NAME,
        value=state,
        max_age=STATE_COOKIE_MAX_AGE,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_state_cookie(response: Response) -> None:
    response.delete_cookie(key=STATE_COOKIE_NAME, path="/")
