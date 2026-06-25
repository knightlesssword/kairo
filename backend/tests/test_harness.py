"""smoke tests proving the harness itself: migrated schema, per-test isolation, asgi app.

these are not feature tests; they exist so a green run means the fixtures actually give
an isolated, migrated database and a working ASGI client.
"""

from __future__ import annotations

from sqlalchemy import func, select, text

from app.models.db.user import User


async def _add_user(db, anilist_id: int) -> None:
    db.add(User(anilist_id=anilist_id, username="tester", access_token_enc="enc"))
    await db.commit()


async def test_schema_migrated(db):
    # alembic stamped its version table -> migrations ran
    assert await db.scalar(text("SELECT count(*) FROM alembic_version")) == 1
    # a known app table exists and is empty at start
    assert await db.scalar(select(func.count()).select_from(User)) == 0


async def test_isolation_first(db):
    # empty at start; if truncation leaked from another test this would fail
    assert await db.scalar(select(func.count()).select_from(User)) == 0
    await _add_user(db, anilist_id=1001)
    assert await db.scalar(select(func.count()).select_from(User)) == 1


async def test_isolation_second(db):
    # the committed user from the previous test must have been truncated away
    assert await db.scalar(select(func.count()).select_from(User)) == 0


async def test_asgi_health_and_request_id(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    # observability middleware is in the served app path
    assert len(r.headers["x-request-id"]) == 32
