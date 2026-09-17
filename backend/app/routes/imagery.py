"""Imagery routes declaration.

Adheres to bcontext/folder-archtecture.md:
- Pure route declarations. No database queries, no models.
"""

from fastapi import APIRouter, Query

from app.controllers import imagery_controller
from app.lib.responses import CursorPage
from app.schemas.imagery import ImageryScene

router = APIRouter(prefix="/imagery", tags=["imagery"])


@router.get("", response_model=CursorPage[ImageryScene])
async def list_imagery(
    cursor: str | None = Query(None, description="Next page cursor"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search filter"),
) -> CursorPage[ImageryScene]:
    """Retrieve cursor-paginated imagery scenes."""
    return await imagery_controller.list_imagery(cursor=cursor, limit=limit, search=search)


@router.get("/{scene_id}", response_model=ImageryScene)
async def get_imagery_scene(scene_id: str) -> ImageryScene:
    """Retrieve metadata for a specific imagery scene."""
    return await imagery_controller.get_imagery_by_id(scene_id)
