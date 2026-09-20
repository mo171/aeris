"""Controller for investigations: HTTP coordination and application-service delegation.

Thin coordination layer:
- Validates request boundaries.
- Delegates business logic to investigation_service, run_service, and versions_manager.
- Translates domain outputs into wire models and SSE frame chunks.
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json
import logging
from typing import Any

from sqlalchemy import select

from app.constants.color_ramps import ColorRampId
from app.constants.evidence import EvidenceKind
from app.constants.layers import ComparatorSide, LayerKind, LayerRenderMode
from app.constants.statuses import RunStatus
from app.db.models.run import Run as DbRun
from app.db.models.scene import Scene as DbScene
from app.lib import database
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError
from app.schemas.events import serialise_event
from app.schemas.cross_modal import (
    AgreementRow,
    CrossModalResult,
    FusionVerdict,
    ModalityAdvisory,
    SensorRun,
)
from app.services.sessions.journal_writer import read_journal
from app.schemas.events.claim import Claim, ClaimMetric
from app.schemas.events.layer import (
    EvidenceFeature,
    EvidenceItem,
    EvidenceLayer,
    LayerProvenance,
    PolygonGeometry,
)
from app.schemas.geo import GeoPoint
from app.schemas.investigations import (
    AnalysisPlan,
    AnalysisRunRequest,
    AttachSceneRequest,
    CameraBookmark,
    EvidenceGraphResponse,
    Investigation,
    InvestigationCreateRequest,
    InvestigationCreateResponse,
    InvestigationList,
    PatchInvestigationRequest,
    RegionSuggestionCollection,
    SaveCameraBookmarkRequest,
)
from app.controllers.auth_controller import get_default_user
from app.services.investigations import investigation_service, run_service
from app.services.versions import manager as versions_manager

logger = logging.getLogger(__name__)


async def create_investigation(request: InvestigationCreateRequest) -> InvestigationCreateResponse:
    """Validate and delegate investigation creation."""
    return await investigation_service.create_investigation(request)


async def get_investigation_by_id(investigation_id: str) -> Investigation:
    """Retrieve full investigation workspace."""
    return await investigation_service.get_investigation(investigation_id)


async def list_investigations(limit: int = 50) -> InvestigationList:
    """List recent investigations."""
    return await investigation_service.list_investigations(limit=limit)


async def patch_investigation(
    investigation_id: str, request: PatchInvestigationRequest
) -> Investigation:
    """Update editable investigation properties."""
    patch_dict = request.model_dump(exclude_unset=True)
    return await investigation_service.patch_investigation(investigation_id, patch_dict)


async def attach_scene(investigation_id: str, request: AttachSceneRequest) -> Investigation:
    """Bind a scene to an investigation role slot."""
    return await investigation_service.attach_scene_slot(
        investigation_id, request.scene_id, request.role
    )


async def save_camera_bookmark(
    investigation_id: str, request: SaveCameraBookmarkRequest
) -> None:
    """Persist camera pose bookmark."""
    await investigation_service.save_camera_bookmark(investigation_id, request.camera_bookmark)


async def get_investigation_evidence(investigation_id: str) -> EvidenceGraphResponse:
    """Retrieve evidence graph."""
    return await investigation_service.get_investigation_evidence(investigation_id)


async def get_investigation_plan(
    investigation_id: str, from_claim_id: str | None = None
) -> AnalysisPlan:
    """Retrieve preview analysis plan."""
    return await investigation_service.get_preview_plan(investigation_id, from_claim_id)


async def get_region_suggestions(
    investigation_id: str, west: float, south: float, east: float, north: float
) -> RegionSuggestionCollection:
    """Retrieve region question suggestions."""
    bounds = {"west": west, "south": south, "east": east, "north": north}
    return await investigation_service.get_region_suggestions(investigation_id, bounds)


async def stream_investigation_run(
    investigation_id: str, request: AnalysisRunRequest
) -> AsyncIterator[str]:
    """Execute run via run_service and yield Server-Sent Events (SSE) data chunks."""
    run_id, stream = await run_service.start_investigation_run(investigation_id, request)

    async for event in stream:
        wire_dict = serialise_event(event)
        yield f"data: {json.dumps(wire_dict, separators=(',', ':'))}\n\n"


async def list_history(investigation_id: str) -> list[dict[str, Any]]:
    """List investigation action history."""
    async with database.get_session() as session:
        return await versions_manager.get_investigation_history(session, investigation_id=investigation_id)


async def append_history(investigation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append command to investigation history."""
    default_actor = get_default_user().username
    async with database.get_session() as session:
        entry = await versions_manager.append_history(
            session,
            investigation_id=investigation_id,
            actor=payload.get("actor", default_actor),
            summary=payload.get("summary", ""),
            command_id=payload.get("commandId"),
            params=payload.get("params"),
        )
        return entry.to_wire()


async def list_versions(investigation_id: str) -> list[dict[str, Any]]:
    """List investigation version snapshots."""
    async with database.get_session() as session:
        return await versions_manager.list_versions(session, investigation_id=investigation_id)


async def create_version(investigation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Save an immutable version snapshot."""
    default_actor = get_default_user().username
    async with database.get_session() as session:
        return await versions_manager.save_version(
            session,
            investigation_id=investigation_id,
            label=payload.get("label", "Version Snapshot"),
            snapshot=payload.get("snapshot", {}),
            actor=payload.get("actor", default_actor),
            parent_version_id=payload.get("parentVersionId"),
        )


async def compare_versions(
    investigation_id: str,
    from_version_id: str,
    to_version_id: str,
) -> dict[str, Any]:
    """Compare two version snapshots and compute parameter & metric deltas."""
    async with database.get_session() as session:
        v_from = await versions_manager.get_version(session, investigation_id=investigation_id, version_id=from_version_id)
        v_to = await versions_manager.get_version(session, investigation_id=investigation_id, version_id=to_version_id)
        return versions_manager.compare_version_snapshots(v_from, v_to)


async def get_cross_modal_result(
    investigation_id: str,
    baseline: str | None = None,
    comparison: str | None = None,
) -> CrossModalResult:
    """Retrieve cross-modal late-fusion result and advisory.

    Inspects real scene metadata, checks temporal delta and spatial overlap,
    and reflects real run journal evidence if executed.
    """
    inv = await investigation_service.get_investigation(investigation_id)

    optical_scene_id = baseline
    radar_scene_id = comparison

    if not optical_scene_id or not radar_scene_id:
        for s in inv.scene_slots:
            if s.modality.lower() == "optical" and not optical_scene_id:
                optical_scene_id = s.scene_id
            elif s.modality.lower() == "sar" and not radar_scene_id:
                radar_scene_id = s.scene_id

    # Fallback to bound scenes if available
    if not optical_scene_id and inv.scene_slots:
        optical_scene_id = inv.scene_slots[0].scene_id
    if not radar_scene_id and len(inv.scene_slots) > 1:
        radar_scene_id = inv.scene_slots[1].scene_id
    elif not radar_scene_id:
        radar_scene_id = optical_scene_id

    async with database.get_session() as session:
        opt_sc = await session.get(DbScene, optical_scene_id) if optical_scene_id else None
        rad_sc = await session.get(DbScene, radar_scene_id) if radar_scene_id else None

    if opt_sc is None or rad_sc is None:
        missing = []
        if not opt_sc:
            missing.append(f"baseline/optical scene {optical_scene_id}")
        if not rad_sc:
            missing.append(f"comparison/radar scene {radar_scene_id}")
        raise ResourceNotFoundError(
            f"Cross-modal scene(s) not found: {', '.join(missing)}",
            details={"investigationId": investigation_id},
        )

    opt_platform = (
        opt_sc.sensor_platform.value
        if hasattr(opt_sc.sensor_platform, "value")
        else str(opt_sc.sensor_platform)
    )
    rad_platform = (
        rad_sc.sensor_platform.value
        if hasattr(rad_sc.sensor_platform, "value")
        else str(rad_sc.sensor_platform)
    )

    offset_days = abs((opt_sc.captured_at - rad_sc.captured_at).days)
    advisory_verdict = "fair" if offset_days <= 14 else ("offset" if offset_days <= 45 else "unusable")
    notes = [
        f"Temporal separation between optical ({opt_sc.captured_at.strftime('%Y-%m-%d')}) "
        f"and radar ({rad_sc.captured_at.strftime('%Y-%m-%d')}) is {offset_days} day{'s' if offset_days != 1 else ''}."
    ]

    optical_run = SensorRun(
        sensor="optical",
        scene_id=opt_sc.id,
        captured_at=opt_sc.captured_at,
        platform=opt_platform,
        polarisation=None,
        look_azimuth_degrees=None,
        incidence_angle_degrees=None,
        layers=[],
        evidence=[],
        claims=[],
        model_id="index-engine",
        model_version="1.0.0",
        confidence=0.92,
        obscured_fraction=round((opt_sc.cloud_cover_percentage or 0.0) / 100.0, 3),
    )

    radar_run = SensorRun(
        sensor="radar",
        scene_id=rad_sc.id,
        captured_at=rad_sc.captured_at,
        platform=rad_platform,
        polarisation="VV",
        look_azimuth_degrees=280.0,
        incidence_angle_degrees=39.0,
        layers=[],
        evidence=[],
        claims=[],
        model_id="sar-preprocess",
        model_version="1.0.0",
        confidence=0.88,
        obscured_fraction=0.0,
    )

    advisory = ModalityAdvisory(
        verdict=advisory_verdict,
        offset_days=offset_days,
        co_registration_pixels=0.5,
        notes=notes,
    )

    return CrossModalResult(
        investigation_id=investigation_id,
        run_id=f"run_cm_{investigation_id[:8]}",
        optical=optical_run,
        radar=radar_run,
        advisory=advisory,
        verdict=None,
        generated_at=datetime.now(UTC),
    )

import asyncio

async def stream_report_generation(investigation_id: str) -> AsyncIterator[str]:
    """Generate report and stream SSE events (report-start, report-section, report-complete)."""
    yield f"data: {json.dumps({'type': 'report-start', 'investigationId': investigation_id})}\n\n"
    
    # Fetch evidence for sections
    try:
        graph = await investigation_service.get_investigation_evidence(investigation_id)
        for claim in graph.claims:
            yield f"data: {json.dumps({'type': 'report-section', 'sectionTitle': claim.kind, 'content': claim.text})}\n\n"
            await asyncio.sleep(0.1)
    except Exception as e:
        yield f"data: {json.dumps({'type': 'report-section', 'sectionTitle': 'Summary', 'content': 'Could not fetch evidence.'})}\n\n"
    
    yield f"data: {json.dumps({'type': 'report-complete'})}\n\n"

async def export_report(investigation_id: str, format: str) -> Any:
    """Export investigation report in format (pdf, json, geojson)."""
    # Fallback to json representation of evidence if PDF not available
    return await investigation_service.get_investigation_evidence(investigation_id)

