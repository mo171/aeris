"""The FastAPI application factory for AERIS serving.

what  : FastAPI instance, lifespan management (DB engine disposal, Redis closure),
        CORS middleware configuration from settings, global exception handlers,
        and mounting of all route modules.
where : The entry point for Phase 2 HTTP serving. Sibling to cli/main.py.
how   : Conforms to bcontext/folder-archtecture.md and bcontext/code-standards.md.
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

if sys.platform == "win32":
    import asyncio
    try:
        from asyncio import WindowsSelectorEventLoopPolicy
        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    try:
        import uvicorn.loops.asyncio
        uvicorn.loops.asyncio.asyncio_loop_factory = lambda use_subprocess=False: asyncio.SelectorEventLoop
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.lib import database, redis
from app.lib.error_handler import register_exception_handlers
from app.lib.logger import configure_logging
from app.routes import (
    assistant,
    catalogue,
    figures,
    globe,
    health,
    imagery,
    investigations,
    missions,
    models,
    regions,
    speech,
    tiles,
    voice,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Process-wide lifespan managing connection pools and startup/shutdown lifecycle."""
    await configure_logging()
    logger.info("Initializing AERIS API application", extra={"version": settings.version})
    yield
    logger.info("Shutting down AERIS API application")
    await database.dispose_engine()
    await redis.close_client()


def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    app = FastAPI(
        title=settings.project_name,
        version=settings.version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Health & readiness probes at root and under /api/v1
    app.include_router(health.router)
    app.include_router(health.router, prefix="/api/v1")

    # API v1 routes
    app.include_router(imagery.router, prefix="/api/v1")
    app.include_router(catalogue.router, prefix="/api/v1")
    app.include_router(missions.router, prefix="/api/v1")
    app.include_router(globe.router, prefix="/api/v1")
    app.include_router(models.router, prefix="/api/v1")
    app.include_router(investigations.router, prefix="/api/v1")
    app.include_router(figures.router, prefix="/api/v1")
    app.include_router(regions.router, prefix="/api/v1")
    app.include_router(tiles.router, prefix="/api/v1")
    app.include_router(speech.router, prefix="/api/v1")
    app.include_router(assistant.router, prefix="/api/v1")
    app.include_router(voice.router, prefix="/api/v1/voice")

    # Inngest webhook serving for durable background functions (Phase 2.5)
    import inngest.fast_api
    from app.inngest import INNGEST_FUNCTIONS, get_inngest_client

    inngest.fast_api.serve(
        app,
        client=get_inngest_client(),
        functions=INNGEST_FUNCTIONS,
        serve_path="/api/inngest",
        serve_origin=settings.inngest_serve_origin,
    )

    return app


app = create_app()
