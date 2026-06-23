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
from app.database import dispose_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("kairo")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info("kairo backend starting (env=%s)", settings.environment)
    # phase 2: sync-job stale reaper hook goes here
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
        # fail loud in logs, generic to client (no internal leakage)
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # phase 1+: app.include_router(auth.router) etc.

    return app


app = create_app()
