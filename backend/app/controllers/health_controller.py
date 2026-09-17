"""Controller for health, readiness, and dependency diagnostics.

Adheres to bcontext/folder-archtecture.md:
- Controllers validate, invoke services/libs, and shape the response.
- Pure async def methods.
"""

import asyncio
from typing import Any

from app.lib import database, redis, storage


async def get_health_status() -> dict[str, Any]:
    """Concurrent health probe of core infrastructure dependencies."""
    db_health_task = asyncio.create_task(database.check_health())
    redis_health_task = asyncio.create_task(redis.check_health())
    storage_health_task = asyncio.create_task(storage.check_health())

    db_health, redis_health, storage_health = await asyncio.gather(
        db_health_task,
        redis_health_task,
        storage_health_task,
        return_exceptions=True,
    )

    dependencies: list[dict[str, Any]] = []

    # Database
    if isinstance(db_health, Exception):
        dependencies.append({
            "name": "Database",
            "healthy": False,
            "error": str(db_health),
        })
    else:
        dependencies.append({
            "name": "Database",
            "healthy": db_health.is_reachable,
            "latencyMs": db_health.latency_ms,
            "error": db_health.failure_reason,
        })

    # Redis
    if isinstance(redis_health, Exception):
        dependencies.append({
            "name": "Redis",
            "healthy": False,
            "error": str(redis_health),
        })
    else:
        dependencies.append({
            "name": "Redis",
            "healthy": redis_health.is_reachable,
            "latencyMs": redis_health.latency_ms,
            "error": redis_health.failure_reason,
        })

    # Storage
    if isinstance(storage_health, Exception):
        dependencies.append({
            "name": "Storage",
            "healthy": False,
            "error": str(storage_health),
        })
    else:
        dependencies.append({
            "name": "Storage",
            "healthy": storage_health.is_reachable,
            "latencyMs": storage_health.latency_ms,
            "error": storage_health.failure_reason,
        })

    all_healthy = all(d.get("healthy", False) for d in dependencies)

    return {
        "status": "healthy" if all_healthy else "degraded",
        "dependencies": dependencies,
    }


async def get_ready_status() -> dict[str, str]:
    """Readiness probe confirming the application server is up and responsive."""
    return {"status": "ready"}
