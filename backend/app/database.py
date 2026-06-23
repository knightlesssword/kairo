"""async sqlalchemy engine, session factory, and declarative base.

single engine per process. sessions are request-scoped via the `get_session` dependency.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings


class Base(DeclarativeBase):
    """declarative base for all ORM models."""


def _create_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.database_url_str,
        echo=False,
        pool_pre_ping=True,  # drop dead connections instead of failing a request
        pool_size=10,
        max_overflow=5,
    )


engine: AsyncEngine = _create_engine()

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """fastapi dependency yielding a request-scoped session.

    commits on success, rolls back on exception, always closes.
    """
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
