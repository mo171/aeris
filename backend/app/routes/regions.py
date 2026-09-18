"""Declaration of region routes.

Follows bcontext/folder-archtecture.md:
Declaration only. No business logic, no database queries, no model definitions.
All requests are routed directly to controllers/investigations_controller.py.
"""

from fastapi import APIRouter, Query

from app.controllers import investigations_controller
from app.schemas.investigations import RegionSuggestionCollection

router = APIRouter(prefix="/regions", tags=["regions"])


@router.get("/suggestions", response_model=RegionSuggestionCollection)
async def get_region_suggestions(
    investigation_id: str = Query(..., alias="investigationId"),
    west: float = Query(...),
    south: float = Query(...),
    east: float = Query(...),
    north: float = Query(...),
) -> RegionSuggestionCollection:
    """Return contextual query suggestions for a spatial polygon selection within an investigation."""
    return await investigations_controller.get_region_suggestions(
        investigation_id=investigation_id,
        west=west,
        south=south,
        east=east,
        north=north,
    )
