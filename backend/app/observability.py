"""structured logging + request correlation.

three pieces:
  - JsonFormatter: every log record -> single-line JSON (ts, level, logger, msg,
    request_id, optional exc + any extra=... fields). makes logs grep/ingest-friendly.
  - RequestIdFilter: injects the current request id (a contextvar) into every record
    so all log lines emitted while handling a request carry the same correlation id.
  - RequestContextMiddleware: pure-ASGI (NOT BaseHTTPMiddleware) middleware that mints
    a request id per request, binds it to the contextvar, and echoes it on the response
    via the X-Request-ID header.

why pure ASGI: BaseHTTPMiddleware runs the downstream app in a separate anyio task, so a
contextvar set there is not reliably visible in the endpoint / exception handlers. a pure
ASGI middleware sets the contextvar in the same task that runs the app, so correlation
holds end-to-end (endpoint logs + the global 500 handler all see the same id).

the request id is server-minted only (uuid4 hex); inbound X-Request-ID headers are not
trusted, so there is no external-input path into the logs here.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_REQUEST_ID_HEADER = b"x-request-id"

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """current request's correlation id, or '-' outside a request scope."""
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """attach the active request id to each record (so the formatter can emit it)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


# standard LogRecord attributes, so the formatter can detect caller-supplied extras
# (logger.info("x", extra={"user_id": ...})) and surface them without hardcoding names.
_RESERVED_RECORD_KEYS = set(vars(logging.makeLogRecord({}))) | {"request_id", "taskName"}


class JsonFormatter(logging.Formatter):
    """minimal JSON log formatter with request correlation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # surface explicit extra=... fields (structured context), skipping stdlib keys
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_KEYS and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """install the JSON handler + request-id filter on the root logger.

    idempotent: clears existing root handlers first so re-import / test reconfigure
    doesn't double-log. uvicorn's own loggers keep their handlers (propagate=False),
    so this governs application logs without fighting the server's access log.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


class RequestContextMiddleware:
    """pure-ASGI middleware: per-request id, bound to the logging contextvar and
    echoed on the response as X-Request-ID."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex
        token = _request_id.set(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.append((_REQUEST_ID_HEADER, request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            _request_id.reset(token)
