"""AniList OAuth + session lifecycle.

flow: generate state -> redirect to AniList -> callback validates state, exchanges the
code for an access token, fetches the AniList viewer, upserts the user (token encrypted
at rest), and creates a server-side session.

external data (token + viewer responses) is parsed into typed pydantic models with
unknown fields dropped; nothing from AniList is trusted as control flow.

assumption: AniList echoes the `state` query param back to the redirect_uri. it is not in
the official docs but is standard OAuth2 behaviour and used by existing clients. callback
validation fails closed (reject) if state is missing or mismatched.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.db.user import Session, User
from app.services.crypto import encrypt_token

_HTTP_TIMEOUT = httpx.Timeout(10.0)
_VIEWER_QUERY = "query { Viewer { id name } }"


class AniListAuthError(Exception):
    """raised when token exchange or viewer fetch fails. callback maps this to a 4xx."""


class _TokenResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    access_token: str
    token_type: str = "Bearer"
    expires_in: int | None = None  # seconds; AniList tokens last ~1 year


class _Viewer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    name: str


# --- oauth: state + authorize url -------------------------------------------------

def generate_state() -> str:
    """32-byte urlsafe random state for CSRF protection."""
    return secrets.token_urlsafe(32)


def build_authorize_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.anilist_client_id,
        "redirect_uri": settings.anilist_redirect_uri,
        "response_type": "code",
        "state": state,
    }
    return f"{settings.anilist_auth_url}?{urlencode(params)}"


def states_match(cookie_state: str | None, query_state: str | None) -> bool:
    """constant-time compare. fail closed if either side is missing."""
    if not cookie_state or not query_state:
        return False
    return secrets.compare_digest(cookie_state, query_state)


# --- oauth: code exchange + viewer ------------------------------------------------

async def exchange_code(code: str) -> _TokenResponse:
    settings = get_settings()
    payload = {
        "grant_type": "authorization_code",
        "client_id": settings.anilist_client_id,
        "client_secret": settings.anilist_client_secret,
        "redirect_uri": settings.anilist_redirect_uri,
        "code": code,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            settings.anilist_token_url,
            json=payload,
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise AniListAuthError(f"token exchange failed: {resp.status_code}")
    try:
        return _TokenResponse.model_validate(resp.json())
    except Exception as exc:  # malformed token payload
        raise AniListAuthError("malformed token response") from exc


async def fetch_viewer(access_token: str) -> _Viewer:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.post(
            settings.anilist_graphql_url,
            json={"query": _VIEWER_QUERY},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
    if resp.status_code != 200:
        raise AniListAuthError(f"viewer fetch failed: {resp.status_code}")
    body = resp.json()
    viewer = (body.get("data") or {}).get("Viewer")
    if not viewer:
        raise AniListAuthError("viewer response missing data.Viewer")
    try:
        return _Viewer.model_validate(viewer)
    except Exception as exc:
        raise AniListAuthError("malformed viewer response") from exc


# --- persistence: user upsert + sessions ------------------------------------------

async def upsert_user(db: AsyncSession, viewer: _Viewer, token: _TokenResponse) -> User:
    """create or update the user keyed by AniList id. reconnect resets connected state."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=token.expires_in) if token.expires_in else None
    enc = encrypt_token(token.access_token)

    result = await db.execute(select(User).where(User.anilist_id == viewer.id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            anilist_id=viewer.id,
            username=viewer.name,
            access_token_enc=enc,
            token_obtained_at=now,
            token_expires_at=expires_at,
            anilist_connected=True,
        )
        db.add(user)
    else:
        user.username = viewer.name
        user.access_token_enc = enc
        user.token_obtained_at = now
        user.token_expires_at = expires_at
        # reconnect: clear any prior disconnected/revoked state.
        user.anilist_connected = True
        user.revoked_at = None

    await db.flush()
    return user


async def create_session(db: AsyncSession, user: User) -> Session:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    session = Session(
        user_id=user.id,
        expires_at=now + timedelta(days=settings.session_ttl_days),
        last_used_at=now,
    )
    db.add(session)
    await db.flush()
    return session


async def delete_session(db: AsyncSession, session_id: str) -> None:
    """delete a session by id string. no-op if absent or malformed (idempotent logout)."""
    try:
        sid = uuid.UUID(session_id)
    except ValueError:
        return
    session = await db.get(Session, sid)
    if session is not None:
        await db.delete(session)
