"""Controller for specialist model fleet health telemetry.

Returns ModelStatusCollection driving the frontend Model Status strip and Model Observatory.
"""

from app.models.manager import get_manager
from app.schemas.responses.model_status import ModelStatusCollection


async def get_model_statuses() -> ModelStatusCollection:
    """Retrieve runtime status, health, and latency of all specialist models."""
    manager = await get_manager()
    return await manager.status()
