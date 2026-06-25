"""fastapi application factory.

routers are wired in here as phases land. phase 0 ships health + error scaffolding only.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.config import get_settings
from app.database import SessionFactory, dispose_engine
from app.observability import RequestContextMiddleware, configure_logging, get_request_id
from app.routers import auth, conversations, profile
from app.services import sync_service

configure_logging(get_settings().log_level)
logger = logging.getLogger("kairo")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("kairo backend starting (env=%s)", settings.environment)
    async with SessionFactory() as db:
        reaped = await sync_service.stale_job_reaper(db)
        await db.commit()
        if reaped:
            logger.info("startup: reaped %d stale sync job(s)", reaped)
    yield
    await dispose_engine()
    logger.info("kairo backend stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="kairo",
        version="0.1.0",
        lifespan=lifespan,
        # hide schema in prod
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.environment != "production" else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,  # required for session cookie
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # fail loud in logs (full stack via exc_info), generic to client (no internal
        # leakage). request_id lets the client report an id that maps to the log line.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error", "request_id": get_request_id()},
        )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(profile.router)
    app.include_router(conversations.router)

    return app


# wrap OUTSIDE the FastAPI app (and thus outside starlette's ServerErrorMiddleware,
# which runs the 500 handler): the request id must be bound before that handler runs
# and the X-Request-ID header must be attachable even to error responses. this is the
# ASGI app uvicorn serves and tests should exercise.
app = RequestContextMiddleware(create_app())
