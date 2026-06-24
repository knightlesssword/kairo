"""response schemas for auth endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class MeResponse(BaseModel):
    id: uuid.UUID
    username: str
    anilist_id: int
    anilist_connected: bool
    # last sync time; always null in phase 1 (sync lands in phase 2).
    last_synced_at: datetime | None = None
