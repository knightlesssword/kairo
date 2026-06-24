"""OpenRouter LLM provider.

docs: https://openrouter.ai/docs
base url: https://openrouter.ai/api/v1 (OpenAI-compatible)

uses httpx for both regular and streaming calls.
raises LLMError on non-2xx or when the response body is malformed.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, AsyncIterator

import httpx

from app.llm.base import ChatResponse, LLMError, LLMProvider, Message

log = logging.getLogger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class OpenRouterProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LLMError("LLM_API_KEY is not set")
        if not model:
            raise LLMError("LLM_MODEL is not set")
        self._api_key = api_key
        self._model = model
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/kairo",
            "X-Title": "Kairo",
        }

    def _build_messages(
        self, messages: list[Message], system: str | None
    ) -> list[dict]:
        result: list[dict] = []
        if system:
            result.append({"role": "system", "content": system})
        result.extend({"role": m.role, "content": m.content} for m in messages)
        return result

    async def chat(
        self,
        messages: list[Message],
        system: str | None = None,
        response_schema: dict | None = None,
    ) -> ChatResponse:
        payload: dict = {
            "model": self._model,
            "messages": self._build_messages(messages, system),
        }
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "strict": True,
                    "schema": response_schema,
                },
            }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{_BASE_URL}/chat/completions",
                headers=self._headers,
                json=payload,
            )

        if resp.status_code != 200:
            log.error("openrouter error %d: %s", resp.status_code, resp.text[:500])
            raise LLMError(
                f"openrouter returned {resp.status_code}", status_code=resp.status_code
            )

        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return ChatResponse(
                content=content,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            )
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"unexpected openrouter response shape: {exc}") from exc

    async def stream(
        self,
        messages: list[Message],
        system: str | None = None,
    ) -> AsyncGenerator[str, None]:
        payload = {
            "model": self._model,
            "messages": self._build_messages(messages, system),
            "stream": True,
        }

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{_BASE_URL}/chat/completions",
                headers=self._headers,
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    log.error(
                        "openrouter stream error %d: %s",
                        resp.status_code,
                        body[:500],
                    )
                    raise LLMError(
                        f"openrouter returned {resp.status_code}",
                        status_code=resp.status_code,
                    )

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw == "[DONE]":
                        return
                    try:
                        chunk = json.loads(raw)
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except (KeyError, IndexError, json.JSONDecodeError):
                        # malformed chunk - skip, don't abort the stream
                        continue
