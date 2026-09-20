"""Declaration of investigation routes.

Follows bcontext/folder-archtecture.md:
Declaration only. No business logic, no database queries, no model definitions.
All requests are routed directly to controllers/investigations_controller.py and controllers/figures_controller.py.
"""

from typing import Any

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse

from app.controllers import figures_controller, investigations_controller
from app.schemas.cross_modal import CrossModalResult
from app.schemas.events.figure import FigureReadyEvent
from app.schemas.investigations import (
    AnalysisPlan,
    AnalysisRunRequest,
    AttachSceneRequest,
    EvidenceGraphResponse,
    Investigation,
    InvestigationCreateRequest,
    InvestigationCreateResponse,
    InvestigationList,
    PatchInvestigationRequest,
    SaveCameraBookmarkRequest,
)

router = APIRouter(prefix="/investigations", tags=["investigations"])


@router.post("", response_model=InvestigationCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_investigation(request: InvestigationCreateRequest) -> InvestigationCreateResponse:
    """Create a new investigation and return AOI boundary and camera target."""
    return await investigations_controller.create_investigation(request)


@router.get("", response_model=InvestigationList)
async def list_investigations(
    limit: int = Query(default=50, ge=1, le=100),
    project_id: str | None = Query(default=None, alias="projectId"),
) -> InvestigationList:
    """List recent investigations, optionally filtered by project."""
    return await investigations_controller.list_investigations(limit=limit, project_id=project_id)


@router.get("/{investigation_id}", response_model=Investigation)
async def get_investigation(investigation_id: str) -> Investigation:
    """Get complete investigation details."""
    return await investigations_controller.get_investigation_by_id(investigation_id)


@router.patch("/{investigation_id}", response_model=Investigation)
async def patch_investigation(
    investigation_id: str, request: PatchInvestigationRequest
) -> Investigation:
    """Update editable investigation attributes."""
    return await investigations_controller.patch_investigation(investigation_id, request)


@router.post("/{investigation_id}")
async def save_camera_bookmark(
    investigation_id: str, request: SaveCameraBookmarkRequest
) -> dict[str, str]:
    """Persist camera pose bookmark."""
    await investigations_controller.save_camera_bookmark(investigation_id, request)
    return {"status": "saved"}


@router.post("/{investigation_id}/scenes", response_model=Investigation)
async def attach_scene(
    investigation_id: str, request: AttachSceneRequest
) -> Investigation:
    """Bind a scene to an investigation role slot."""
    return await investigations_controller.attach_scene(investigation_id, request)


@router.post("/{investigation_id}/runs")
async def run_investigation_stream(
    investigation_id: str, request: AnalysisRunRequest
) -> StreamingResponse:
    """Stream execution trace, claims, ready layers, and answer tokens via Server-Sent Events (SSE)."""
    generator = investigations_controller.stream_investigation_run(investigation_id, request)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{investigation_id}/evidence", response_model=EvidenceGraphResponse)
async def get_investigation_evidence(investigation_id: str) -> EvidenceGraphResponse:
    """Get flat claim and evidence graph."""
    return await investigations_controller.get_investigation_evidence(investigation_id)


@router.get("/{investigation_id}/plan", response_model=AnalysisPlan)
async def get_investigation_plan(
    investigation_id: str, from_claim_id: str | None = Query(default=None, alias="from")
) -> AnalysisPlan:
    """Get initial preview analysis plan before execution."""
    return await investigations_controller.get_investigation_plan(investigation_id, from_claim_id)


@router.get("/{investigation_id}/figures", response_model=list[FigureReadyEvent])
async def list_investigation_figures(investigation_id: str) -> list[FigureReadyEvent]:
    """Get metadata for all figures produced for this investigation."""
    return await figures_controller.list_investigation_figures(investigation_id)


@router.get("/{investigation_id}/cross-modal", response_model=CrossModalResult)
async def get_cross_modal(
    investigation_id: str,
    baseline: str | None = Query(default=None),
    comparison: str | None = Query(default=None),
) -> CrossModalResult:
    """Get optical/SAR cross-modal comparison verdict and advisory."""
    return await investigations_controller.get_cross_modal_result(
        investigation_id, baseline=baseline, comparison=comparison
    )


@router.get("/{investigation_id}/history")
async def list_history(investigation_id: str) -> list[dict[str, Any]]:
    """List action history."""
    return await investigations_controller.list_history(investigation_id)


@router.post("/{investigation_id}/history", status_code=status.HTTP_201_CREATED)
async def append_history(investigation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append action to history."""
    return await investigations_controller.append_history(investigation_id, payload)


@router.get("/{investigation_id}/versions")
async def list_versions(investigation_id: str) -> list[dict[str, Any]]:
    """List saved version snapshots."""
    return await investigations_controller.list_versions(investigation_id)


@router.post("/{investigation_id}/versions", status_code=status.HTTP_201_CREATED)
async def create_version(investigation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Save immutable version snapshot."""
    return await investigations_controller.create_version(investigation_id, payload)


@router.get("/{investigation_id}/versions/compare")
async def compare_versions(
    investigation_id: str,
    from_version_id: str = Query(..., alias="from"),
    to_version_id: str = Query(..., alias="to"),
) -> dict[str, Any]:
    """Compare two version snapshots and compute parameter & metric deltas."""
    return await investigations_controller.compare_versions(
        investigation_id, from_version_id=from_version_id, to_version_id=to_version_id
    )

@router.post("/{investigation_id}/report")
async def generate_report_stream(investigation_id: str) -> StreamingResponse:
    """Stream report generation events via SSE."""
    generator = investigations_controller.stream_report_generation(investigation_id)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/{investigation_id}/report.{format}")
async def export_report(investigation_id: str, format: str) -> Any:
    """Download investigation report in specific format."""
    return await investigations_controller.export_report(investigation_id, format)
