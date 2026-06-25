"""pytest harness: isolated test database, alembic-migrated, truncated per test.

targeting
  set TEST_DATABASE_URL to a DEDICATED throwaway postgres (NOT the dev compose db on
  port 5433). this conftest copies it into DATABASE_URL for the test process BEFORE any
  app module imports, so the single app engine, the session factory, alembic, and any
  background task all use the test db. fail-loud if unset.

schema
  applied once per session via `alembic upgrade head` in a subprocess (alembic/env.py
  calls asyncio.run, which cannot be nested inside pytest's event loop).

isolation
  each test is isolated by TRUNCATE ... RESTART IDENTITY CASCADE over all app tables in
  teardown. truncate (not a wrapping transaction we roll back) is used deliberately:
  routes and services commit their own sessions, so rolling back an outer transaction
  would fight those commits and give false greens.

pooling
  the app engine is rebound to NullPool for tests so no asyncpg connection is cached
  across pytest's per-test event loops (avoids "attached to a different loop" errors).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[1]

# --- target the dedicated test db BEFORE importing any app module ------------------
_TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
if not _TEST_DB_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is not set. point it at a DEDICATED throwaway postgres "
        "(NOT the dev compose db on 5433), e.g. "
        "postgresql+asyncpg://test:test@localhost:5434/kairo_test"
    )
if ":5433/" in _TEST_DB_URL:
    raise RuntimeError("refusing to run tests against the dev compose db on port 5433")

os.environ["DATABASE_URL"] = _TEST_DB_URL

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()  # drop any cached dev settings; re-read with the test url

# rebind the app engine + session factory to NullPool against the test db. must run
# before app.main is imported (done lazily in the client fixture) so routes use this.
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.database as appdb  # noqa: E402
import app.models.db  # noqa: E402,F401  (populate Base.metadata for truncation)

appdb.engine = create_async_engine(get_settings().database_url_str, poolclass=NullPool)
appdb.SessionFactory = async_sessionmaker(
    bind=appdb.engine, expire_on_commit=False, autoflush=False
)


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    """apply alembic migrations once for the whole test session."""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_BACKEND_DIR,
        env=os.environ,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head failed:\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


_truncate_sql: str | None = None


async def _truncate_all() -> None:
    global _truncate_sql
    if _truncate_sql is None:
        names = ", ".join(f'"{t.name}"' for t in appdb.Base.metadata.sorted_tables)
        _truncate_sql = f"TRUNCATE {names} RESTART IDENTITY CASCADE"
    async with appdb.engine.begin() as conn:
        await conn.execute(text(_truncate_sql))


@pytest.fixture(autouse=True)
async def _clean_tables():
    """truncate every app table after each test for isolation."""
    yield
    await _truncate_all()


@pytest.fixture
async def db():
    """async session bound to the test db, for arrange/assert directly against the db.

    commit inside the test when a route under test must observe the data; the autouse
    truncation cleans up afterward.
    """
    async with appdb.SessionFactory() as session:
        yield session


@pytest.fixture
async def client():
    """httpx async client over the real ASGI app (request-id middleware included).

    lifespan is not run (no startup reaper); services that need it are called directly.
    """
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
