"""Missions route declarations.

Adheres to bcontext/folder-archtecture.md:
- Routes declare HTTP verbs and paths only. No business logic.
"""

from fastapi import APIRouter, Query

from app.controllers import mission_controller
from app.lib.responses import CursorPage
from app.schemas.missions import Mission, MissionCreateRequest

router = APIRouter(prefix="/missions", tags=["missions"])
    
@router.post("", response_model=Mission, status_code=201)
async def create_mission(request: MissionCreateRequest) -> Mission:
    """Create a new mission."""
    return await mission_controller.create_mission(request)


@router.get("", response_model=CursorPage[Mission])
async def list_missions(
    cursor: str | None = Query(None, description="Next page cursor"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    project_id: str | None = Query(None, alias="projectId", description="Filter by project ID"),
) -> CursorPage[Mission]:
    """Retrieve cursor-paginated standing missions."""
    return await mission_controller.list_missions(cursor=cursor, limit=limit, project_id=project_id)


@router.get("/{mission_id}", response_model=Mission)
async def get_mission(mission_id: str) -> Mission:
    """Retrieve a single mission by ID."""
    return await mission_controller.get_mission_by_id(mission_id)
