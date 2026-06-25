"""Ollama LLM provider (local, self-host).

docs: https://github.com/ollama/ollama/blob/main/docs/api.md
endpoint: {ollama_base_url}/api/chat

differences from the OpenAI-compatible providers:
- no api key (local server)
- streaming is the default; chat() must set stream=false to get a single JSON body
- streaming responses are newline-delimited JSON (NDJSON), not SSE "data: " frames
- assistant deltas live in message.content (not choices[].delta.content)
- token counts are prompt_eval_count / eval_count
- structured output uses the `format` field set to a JSON schema

raises LLMError on non-2xx or malformed bodies, same contract as the other providers.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

from app.llm.base import ChatResponse, LLMError, LLMProvider, Message

log = logging.getLogger(__name__)

# local model load (load_duration) can be slow on a cold first call, so the read
# budget is more generous than the cloud providers.
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str) -> None:
        if not base_url:
            raise LLMError("OLLAMA_BASE_URL is not set")
        if not model:
            raise LLMError("LLM_MODEL is not set")
        self._base_url = base_url.rstrip("/")
        self._model = model

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
            "stream": False,
        }
        if response_schema is not None:
            # ollama structured outputs: pass the JSON schema directly in `format`.
            payload["format"] = response_schema

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )

        if resp.status_code != 200:
            log.error("ollama error %d: %s", resp.status_code, resp.text[:500])
            raise LLMError(
                f"ollama returned {resp.status_code}", status_code=resp.status_code
            )

        try:
            data = resp.json()
            content = data["message"]["content"]
            return ChatResponse(
                content=content,
                input_tokens=data.get("prompt_eval_count", 0),
                output_tokens=data.get("eval_count", 0),
            )
        except (KeyError, ValueError) as exc:
            raise LLMError(f"unexpected ollama response shape: {exc}") from exc

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
                f"{self._base_url}/api/chat",
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    log.error("ollama stream error %d: %s", resp.status_code, body[:500])
                    raise LLMError(
                        f"ollama returned {resp.status_code}",
                        status_code=resp.status_code,
                    )

                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        delta = chunk.get("message", {}).get("content")
                        if delta:
                            yield delta
                        if chunk.get("done"):
                            return
                    except json.JSONDecodeError:
                        # malformed line - skip, don't abort the stream
                        continue
