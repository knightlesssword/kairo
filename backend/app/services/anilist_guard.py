"""AniList connection guard.

every AniList API call must pass through `assert_token_valid` first. if the stored token
is past its expiry, or AniList later returns 401, we flip `anilist_connected=false` and
stamp `revoked_at`, then abort cleanly with `AniListDisconnected`. this avoids mysterious
sync/lookup failures and is what the frontend reconnect banner keys off.

there is no refresh flow (AniList does not officially support one for this app); recovery
is a full re-login, which `auth_service.upsert_user` resets back to connected.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.user import User


class AniListDisconnected(Exception):
    """raised when a user's AniList token is expired/revoked. callers should abort."""


async def _mark_disconnected(db: AsyncSession, user: User) -> None:
    """flip the user to disconnected state. idempotent; flush so the change is durable."""
    if user.anilist_connected:
        user.anilist_connected = False
        user.revoked_at = datetime.now(timezone.utc)
        await db.flush()


async def assert_token_valid(db: AsyncSession, user: User) -> None:
    """pre-call check. raises AniListDisconnected (and persists the flag) if expired.

    a null `token_expires_at` is treated as non-expiring (AniList tokens are long-lived;
    absence of an expiry means we never learned one, not that it is expired).
    """
    if not user.anilist_connected:
        raise AniListDisconnected("AniList connection already marked disconnected")

    expires_at = user.token_expires_at
    if expires_at is not None and expires_at <= datetime.now(timezone.utc):
        await _mark_disconnected(db, user)
        raise AniListDisconnected("AniList token expired")


async def handle_unauthorized(db: AsyncSession, user: User) -> None:
    """call when AniList returns 401 mid-request. marks disconnected then raises."""
    await _mark_disconnected(db, user)
    raise AniListDisconnected("AniList returned 401 (token revoked)")
