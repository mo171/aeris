"""Imagery routes declaration.

Adheres to bcontext/folder-archtecture.md:
- Pure route declarations. No database queries, no business logic.
"""

from fastapi import APIRouter, BackgroundTasks, Query

from app.constants.statuses import SceneProcessingState
from app.controllers import imagery_controller
from app.lib.responses import CursorPage
from app.schemas.imagery import (
    ImageryConfirmResponse,
    ImageryScene,
    ImageryUploadTicket,
    ImageryUploadTicketRequest,
)

router = APIRouter(prefix="/imagery", tags=["imagery"])


@router.get("", response_model=CursorPage[ImageryScene])
async def list_imagery(
    cursor: str | None = Query(None, description="Next page cursor"),
    limit: int = Query(25, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search filter"),
    state: SceneProcessingState | None = Query(SceneProcessingState.READY, description="Filter by processing state"),
) -> CursorPage[ImageryScene]:
    """Retrieve cursor-paginated imagery scenes."""
    return await imagery_controller.list_imagery(cursor=cursor, limit=limit, search=search, state=state)


@router.post("/upload-ticket", response_model=ImageryUploadTicket)
async def create_imagery_upload_ticket(
    payload: ImageryUploadTicketRequest,
) -> ImageryUploadTicket:
    """Request a presigned URL ticket for direct-to-storage imagery upload."""
    return await imagery_controller.create_upload_ticket(payload)


@router.get("/{scene_id}", response_model=ImageryScene)
async def get_imagery_scene(scene_id: str) -> ImageryScene:
    """Retrieve metadata for a specific imagery scene."""
    return await imagery_controller.get_imagery_by_id(scene_id)


@router.post("/{scene_id}/confirm", response_model=ImageryConfirmResponse)
async def confirm_imagery_upload(
    scene_id: str,
    background_tasks: BackgroundTasks,
) -> ImageryConfirmResponse:
    """Confirm direct upload has landed in storage and trigger background ingest."""
    return await imagery_controller.confirm_upload(scene_id, background_tasks)
