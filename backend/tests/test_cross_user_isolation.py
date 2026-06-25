"""cross-user data isolation.

verifies that one authenticated user cannot read or delete another user's resources.
ownership is enforced with 404 (not 403) to avoid leaking resource existence.

approach: seed users + sessions directly into the test DB, then drive the real ASGI
app via the client fixture. no mocking of auth; the real get_current_user dependency
reads the session row we inserted.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.conversation import Conversation
from app.models.db.user import Session, User

_SESSION_COOKIE = "kairo_session"
_FAR_FUTURE = datetime(2099, 1, 1, tzinfo=timezone.utc)


def _auth(session_id: str) -> dict[str, str]:
    """Cookie header for a session id. avoids the httpx per-request cookies= deprecation."""
    return {"Cookie": f"{_SESSION_COOKIE}={session_id}"}


async def _seed_user(db: AsyncSession, anilist_id: int) -> tuple[uuid.UUID, str]:
    """insert user + valid session; return (user_id, session_cookie_value).

    sets Session.id explicitly so we can return it without a DB round-trip.
    commits so the route handler's separate session can see the rows.
    """
    user = User(
        anilist_id=anilist_id,
        username=f"user_{anilist_id}",
        access_token_enc="enc",
    )
    db.add(user)
    await db.flush()  # populates server-generated user.id via RETURNING

    session_id = uuid.uuid4()
    db.add(Session(id=session_id, user_id=user.id, expires_at=_FAR_FUTURE))
    await db.commit()

    return user.id, str(session_id)


async def _seed_conversation(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    """insert a conversation owned by user_id; return its id."""
    conv = Conversation(user_id=user_id)
    db.add(conv)
    await db.flush()
    conv_id = conv.id
    await db.commit()
    return conv_id


# ---------------------------------------------------------------------------
# unauthenticated
# ---------------------------------------------------------------------------

async def test_unauth_returns_401(client):
    r = await client.get("/conversations")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# cross-user read isolation
# ---------------------------------------------------------------------------

async def test_cannot_read_other_users_conversation(client, db):
    user_a_id, _cookie_a = await _seed_user(db, anilist_id=2001)
    _user_b_id, cookie_b = await _seed_user(db, anilist_id=2002)

    conv_id = await _seed_conversation(db, user_a_id)

    r = await client.get(f"/conversations/{conv_id}", headers=_auth(cookie_b))
    assert r.status_code == 404


async def test_list_sees_only_own_conversations(client, db):
    user_a_id, cookie_a = await _seed_user(db, anilist_id=2005)
    user_b_id, cookie_b = await _seed_user(db, anilist_id=2006)

    await _seed_conversation(db, user_a_id)
    await _seed_conversation(db, user_b_id)

    r_a = await client.get("/conversations", headers=_auth(cookie_a))
    assert r_a.status_code == 200
    assert len(r_a.json()["items"]) == 1

    r_b = await client.get("/conversations", headers=_auth(cookie_b))
    assert r_b.status_code == 200
    assert len(r_b.json()["items"]) == 1


# ---------------------------------------------------------------------------
# cross-user delete isolation
# ---------------------------------------------------------------------------

async def test_cannot_delete_other_users_conversation(client, db):
    user_a_id, _cookie_a = await _seed_user(db, anilist_id=2003)
    _user_b_id, cookie_b = await _seed_user(db, anilist_id=2004)

    conv_id = await _seed_conversation(db, user_a_id)

    r = await client.delete(f"/conversations/{conv_id}", headers=_auth(cookie_b))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# positive: owner can access their own resources
# ---------------------------------------------------------------------------

async def test_owner_can_read_own_conversation(client, db):
    user_id, cookie = await _seed_user(db, anilist_id=2007)
    conv_id = await _seed_conversation(db, user_id)

    r = await client.get(f"/conversations/{conv_id}", headers=_auth(cookie))
    assert r.status_code == 200
    assert r.json()["id"] == str(conv_id)


async def test_owner_can_delete_own_conversation(client, db):
    user_id, cookie = await _seed_user(db, anilist_id=2008)
    conv_id = await _seed_conversation(db, user_id)

    r = await client.delete(f"/conversations/{conv_id}", headers=_auth(cookie))
    assert r.status_code == 204
