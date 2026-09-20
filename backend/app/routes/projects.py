from fastapi import APIRouter, Query
from app.controllers import project_controller
from app.lib.responses import CursorPage
from app.schemas.projects import ProjectResponse, ProjectCreateRequest

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("", response_model=CursorPage[ProjectResponse])
async def list_projects(
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> CursorPage[ProjectResponse]:
    return await project_controller.list_projects(cursor=cursor, limit=limit)

@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str) -> ProjectResponse:
    return await project_controller.get_project_by_id(project_id)

@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(request: ProjectCreateRequest) -> ProjectResponse:
    return await project_controller.create_project(request)
