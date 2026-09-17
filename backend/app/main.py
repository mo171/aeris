"""The FastAPI application factory for AERIS serving.

what  : FastAPI instance, lifespan management (DB engine disposal, Redis closure),
        CORS middleware configuration from settings, global exception handlers,
        and mounting of all route modules.
where : The entry point for Phase 2 HTTP serving. Sibling to cli/main.py.
how   : Conforms to bcontext/folder-archtecture.md and bcontext/code-standards.md.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.lib import database, redis
from app.lib.error_handler import register_exception_handlers
from app.lib.logger import configure_logging
from app.routes import health

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Process-wide lifespan managing connection pools and startup/shutdown lifecycle."""
    await configure_logging()
    logger.info("Initializing AERIS API application", extra={"version": settings.version})
    yield
    logger.info("Shutting down AERIS API application")
    await database.dispose_engine()
    await redis.close()


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

    return app


app = create_app()
