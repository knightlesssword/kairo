"""conversations routes: CRUD + SSE chat endpoint.

POST   /conversations                   -> {id, title, created_at}
GET    /conversations?limit=&cursor=    -> {items, next_cursor}
GET    /conversations/{id}              -> conversation + last 50 messages
DELETE /conversations/{id}              -> 204
POST   /conversations/{id}/messages     -> SSE stream (text/event-stream)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.dependencies import get_current_user
from app.models.db.conversation import Conversation, Message
from app.models.db.user import User
from app.services import conversation_service
from app.services.chat_service import stream_chat

router = APIRouter(prefix="/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# response schemas
# ---------------------------------------------------------------------------

class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class ConversationDetailResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    next_cursor: str | None  # ISO datetime string; None if no more pages


class SendMessageRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _conv_response(conv: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


def _msg_response(msg: Message) -> MessageResponse:
    return MessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        created_at=msg.created_at,
    )


async def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------

@router.post("", status_code=201, response_model=ConversationResponse)
async def create_conversation(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationResponse:
    conv = await conversation_service.create_conversation(user.id, db)
    await db.commit()
    return _conv_response(conv)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationListResponse:
    parsed_cursor: datetime | None = None
    if cursor:
        try:
            parsed_cursor = datetime.fromisoformat(cursor)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid cursor format")

    items = await conversation_service.list_conversations(
        user.id, db, limit=limit + 1, cursor=parsed_cursor
    )

    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    next_cursor = items[-1].updated_at.isoformat() if has_more and items else None

    return ConversationListResponse(
        items=[_conv_response(c) for c in items],
        next_cursor=next_cursor,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> ConversationDetailResponse:
    conv = await conversation_service.get_conversation(user.id, conversation_id, db)
    history = await conversation_service.get_history(conversation_id, db, limit=50)
    return ConversationDetailResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_msg_response(m) for m in history],
    )


@router.delete("/{conversation_id}", status_code=204, response_class=Response)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Response:
    await conversation_service.delete_conversation(user.id, conversation_id, db)
    await db.commit()
    return Response(status_code=204)


@router.post("/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    settings = get_settings()

    # validate ownership before streaming
    await conversation_service.get_conversation(user.id, conversation_id, db)

    # cap message length
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="message content is empty")
    if len(content) > settings.max_user_message_chars:
        raise HTTPException(
            status_code=400,
            detail=f"message exceeds {settings.max_user_message_chars} character limit",
        )

    async def event_stream() -> AsyncIterator[str]:
        assistant_chunks: list[str] = []
        had_error = False

        async for event in stream_chat(user, db, conversation_id, content):
            yield await _sse_event(event)

            if event["type"] == "delta":
                assistant_chunks.append(event["content"])
            elif event["type"] == "error":
                had_error = True

        # persist messages after stream completes
        if not had_error:
            assistant_content = "".join(assistant_chunks)
            try:
                await conversation_service.append_message(
                    conversation_id=conversation_id,
                    role="user",
                    content=content,
                    db=db,
                )
                await conversation_service.append_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=assistant_content,
                    db=db,
                )
                # set title from first user message if not yet set
                await conversation_service.set_title(conversation_id, content[:80], db)
                await db.commit()
            except Exception:
                # persistence failure must not break the already-sent stream
                import logging
                logging.getLogger(__name__).exception(
                    "failed to persist messages for conversation %s", conversation_id
                )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
        },
    )
