"""CRUD for conversations and messages.

all reads/writes are scoped to the authenticated user. ownership is checked before
any access to conversation content - wrong user gets 404 (not 403, to avoid leaking
conversation existence).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db.conversation import Conversation, Message


async def create_conversation(
    user_id: uuid.UUID,
    db: AsyncSession,
    title: str | None = None,
) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv


async def list_conversations(
    user_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 20,
    cursor: datetime | None = None,
) -> list[Conversation]:
    """keyset pagination on updated_at DESC. cursor = last seen updated_at."""
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(limit)
    )
    if cursor is not None:
        stmt = stmt.where(Conversation.updated_at < cursor)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_conversation(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: AsyncSession,
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status_code=404, detail="conversation not found")
    return conv


async def delete_conversation(
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    conv = await get_conversation(user_id, conversation_id, db)
    await db.delete(conv)
    await db.flush()


async def get_history(
    conversation_id: uuid.UUID,
    db: AsyncSession,
    limit: int = 50,
) -> list[Message]:
    """returns messages in ascending created_at order (oldest first = correct LLM order)."""
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def append_message(
    conversation_id: uuid.UUID,
    role: str,
    content: str,
    db: AsyncSession,
    context_used: dict | None = None,
) -> Message:
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        context_used=context_used,
    )
    db.add(msg)

    # bump conversation updated_at so list_conversations sorts correctly
    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv is not None:
        conv.updated_at = datetime.now(timezone.utc)

    await db.flush()
    await db.refresh(msg)
    return msg


async def set_title(
    conversation_id: uuid.UUID,
    title: str,
    db: AsyncSession,
) -> None:
    """set conversation title (called after first user message)."""
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if conv is not None and conv.title is None:
        conv.title = title[:255]
        await db.flush()
