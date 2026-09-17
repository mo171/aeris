"""Health and readiness route declarations.

Adheres to bcontext/folder-archtecture.md:
- Routes declare HTTP verbs and paths only.
- No business logic, no direct database queries, no model loading.
"""

from typing import Any

from fastapi import APIRouter

from app.controllers import health_controller

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Infrastructure health check."""
    return await health_controller.get_health_status()


@router.get("/ready")
async def readiness_check() -> dict[str, str]:
    """Server readiness probe."""
    return await health_controller.get_ready_status()
