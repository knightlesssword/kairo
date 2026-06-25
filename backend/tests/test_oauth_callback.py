"""oauth callback: state validation, token encrypted at rest, session cookie set.

patches exchange_code + fetch_viewer so no real AniList network call is made.
the real get_current_user, upsert_user, create_session, and encrypt_token all run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.db.user import Session, User
from app.services.crypto import decrypt_token

_STATE_COOKIE = "kairo_oauth_state"
_SESSION_COOKIE = "kairo_session"
_STATE = "aaaabbbbccccdddd1234567890abcdef"
_PLAINTEXT_TOKEN = "anilist_access_token_plaintext_xyz"


def _state_hdr(state: str) -> dict[str, str]:
    return {"Cookie": f"{_STATE_COOKIE}={state}"}


async def test_missing_state_cookie_returns_400(client):
    r = await client.get(
        "/auth/anilist/callback",
        params={"code": "some_code", "state": _STATE},
    )
    assert r.status_code == 400


async def test_mismatched_state_returns_400(client):
    r = await client.get(
        "/auth/anilist/callback",
        params={"code": "some_code", "state": _STATE},
        headers=_state_hdr("different_state_value_xyz"),
    )
    assert r.status_code == 400


async def test_error_param_returns_400(client):
    r = await client.get(
        "/auth/anilist/callback",
        params={"error": "access_denied"},
        headers=_state_hdr(_STATE),
    )
    assert r.status_code == 400


async def test_successful_callback_encrypts_token_and_sets_session(client, db):
    fake_token = SimpleNamespace(
        access_token=_PLAINTEXT_TOKEN, token_type="Bearer", expires_in=None
    )
    fake_viewer = SimpleNamespace(id=5001, name="AniUser")

    with (
        patch(
            "app.services.auth_service.exchange_code",
            new_callable=AsyncMock,
            return_value=fake_token,
        ),
        patch(
            "app.services.auth_service.fetch_viewer",
            new_callable=AsyncMock,
            return_value=fake_viewer,
        ),
    ):
        r = await client.get(
            "/auth/anilist/callback",
            params={"code": "fake_code", "state": _STATE},
            headers=_state_hdr(_STATE),
        )

    assert r.status_code == 302
    assert _SESSION_COOKIE in r.cookies

    # token encrypted at rest: stored ciphertext is not the plaintext token
    result = await db.execute(select(User).where(User.anilist_id == 5001))
    user = result.scalar_one()
    assert user.access_token_enc != _PLAINTEXT_TOKEN
    assert decrypt_token(user.access_token_enc) == _PLAINTEXT_TOKEN

    # session row exists and is valid
    session_id = uuid.UUID(r.cookies[_SESSION_COOKIE])
    session = await db.get(Session, session_id)
    assert session is not None
    assert session.user_id == user.id
    assert session.expires_at > datetime.now(timezone.utc)
