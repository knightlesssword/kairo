"""LLM provider abstraction.

LLMProvider is the single interface all provider implementations must satisfy.
- chat()   -> structured or unstructured single-turn call (taste gen, entity extraction)
- stream() -> async generator of string deltas (user-facing answer)

LLMError is raised by all implementations on non-2xx responses or parse failures.
The caller decides whether to retry or surface to the user.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator

from pydantic import BaseModel


class Message(BaseModel):
    role: str  # 'system' | 'user' | 'assistant'
    content: str


class ChatResponse(BaseModel):
    content: str
    input_tokens: int
    output_tokens: int


class LLMError(Exception):
    """raised on non-2xx responses, timeouts, or unrecoverable parse failures."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        response_schema: dict | None = None,
    ) -> ChatResponse:
        """single-turn call.

        if response_schema is provided, the implementation must request structured JSON
        output (via response_format, tool-use, or equivalent). the caller validates the
        returned content against a pydantic schema and may retry on mismatch.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """streaming call. implementations must be async generators (use yield).

        callers: `async for delta in llm.stream(messages): ...` — no await.
        """
        ...
