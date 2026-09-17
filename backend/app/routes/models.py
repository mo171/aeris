"""Model fleet health and status route declarations.

Adheres to bcontext/folder-archtecture.md:
- Routes declare HTTP verbs and paths only. No business logic.
"""

from fastapi import APIRouter

from app.controllers import model_controller
from app.schemas.responses.model_status import ModelStatusCollection

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/status", response_model=ModelStatusCollection)
async def get_model_statuses() -> ModelStatusCollection:
    """Retrieve runtime health and latency metrics for all specialist models."""
    return await model_controller.get_model_statuses()
