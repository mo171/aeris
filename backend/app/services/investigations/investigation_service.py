"""Domain and persistence service for investigations, scene bindings, and plans.

Handles:
- Investigation creation, centroid/AOI resolution, and camera target calculation.
- Scene slot bindings with singular role constraints.
- Investigation retrieval with full scene slots and acquisitions.
- Camera bookmark persistence and workspace patch operations.
- Preview plan generation and evidence graph extraction.
"""

from datetime import UTC, datetime
import logging
import math
from typing import Any

from geoalchemy2.shape import from_shape, to_shape
from pydantic import BaseModel, Field
from shapely.geometry import Point, Polygon, box
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.agents.legacy_planner import build_plan
from app.agents.router import SceneFacts, route_plan, routing_arbiter, routing_resources
from app.agents.state import describe_step
from app.constants.color_ramps import ColorRampId
from app.constants.evidence import EvidenceKind
from app.constants.geo import STORAGE_SRID
from app.constants.investigations import WorkspaceMode
from app.constants.layers import ComparatorSide, LayerKind, LayerRenderMode
from app.constants.routing import Modality
from app.constants.scenes import SceneRole
from app.constants.statuses import InvestigationStatus, RunStatus
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.db.models.investigation import Investigation as DbInvestigation, InvestigationScene as DbInvestigationScene
from app.db.models.project import Project
from app.db.models.run import Run as DbRun
from app.db.models.scene import Scene as DbScene
from app.lib import database
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError
from app.lib.llm.chat_model import build_chat_model
from app.prompts.investigations import (
    REGION_SUGGESTION_SYSTEM_PROMPT,
    REGION_SUGGESTION_USER_TEMPLATE,
)
from app.schemas.events.claim import Claim, ClaimMetric
from app.services.sessions.journal_writer import read_journal
from app.schemas.events.layer import (
    BoundingBoxGeometry,
    EvidenceFeature,
    EvidenceItem,
    EvidenceLayer,
    LayerProvenance,
    PolygonGeometry,
)
from app.schemas.geo import GeoBoundingBox, GeoPoint
from app.schemas.investigations import (
    Acquisition,
    AcquisitionTiles,
    AnalysisPlan,
    AnalysisPlanStep,
    CameraBookmark,
    CameraTarget,
    EvidenceGraphResponse,
    Investigation,
    InvestigationCreateRequest,
    InvestigationCreateResponse,
    InvestigationList,
    InvestigationSceneSlot,
    InvestigationSummary,
    RegionSuggestion,
    RegionSuggestionCollection,
)

logger = logging.getLogger(__name__)


def _poly_to_bbox(poly: Polygon) -> GeoBoundingBox:
    minx, miny, maxx, maxy = poly.bounds
    return GeoBoundingBox(west=minx, south=miny, east=maxx, north=maxy)


async def create_investigation(request: InvestigationCreateRequest) -> InvestigationCreateResponse:
    """Create a new investigation, computing AOI footprint and camera target from attached scenes."""
    async with database.get_session() as session:
        # 1. Fetch scenes from DB
        scene_stmt = select(DbScene).where(DbScene.id.in_(request.scene_ids))
        result = await session.execute(scene_stmt)
        scenes = list(result.scalars().all())
        if not scenes:
            raise ResourceNotFoundError(
                f"None of the specified sceneIds exist in the catalogue: {request.scene_ids}",
                details={"sceneIds": request.scene_ids},
            )

        ready_scenes = [s for s in scenes if s.footprint is not None]
        if not ready_scenes:
            raise InvalidRequestError(
                f"Specified scenes {request.scene_ids} have no geographic footprint in the catalogue.",
                details={"sceneIds": request.scene_ids},
            )

        geoms = [to_shape(s.footprint) for s in ready_scenes]
        # Union of footprints
        union_poly = geoms[0]
        for g in geoms[1:]:
            union_poly = union_poly.union(g)
        if not isinstance(union_poly, Polygon):
            union_poly = union_poly.convex_hull
        centroid = union_poly.centroid
        if hasattr(ready_scenes[0], "tile_id") and ready_scenes[0].tile_id:
            aoi_name = f"Region {ready_scenes[0].tile_id}"
        else:
            aoi_name = f"Investigation AOI ({ready_scenes[0].id[:12]})"

        bbox = _poly_to_bbox(union_poly)
        span_deg = max(bbox.east - bbox.west, bbox.north - bbox.south, 0.05)
        altitude = max(10000.0, min(span_deg * 111000.0 * 1.5, 300000.0))

        inv_id = new_identifier(IdentifierPrefix.INVESTIGATION)
        trace_id = new_identifier(IdentifierPrefix.TRACE)

        # Ensure project exists if referenced
        if request.project_id:
            proj_stmt = select(Project).where(Project.id == request.project_id)
            proj_res = await session.execute(proj_stmt)
            if proj_res.scalar_one_or_none() is None:
                session.add(
                    Project(
                        id=request.project_id,
                        name="Default Project" if request.project_id == "prj_default" else f"Project {request.project_id}",
                        description="Auto-initialized project workspace",
                    )
                )
                await session.flush()

        db_inv = DbInvestigation(
            id=inv_id,
            name=aoi_name,
            area_of_interest_name=aoi_name,
            area_of_interest=from_shape(union_poly, srid=STORAGE_SRID),
            centroid=from_shape(centroid, srid=STORAGE_SRID),
            status=InvestigationStatus.DRAFT,
            mode=WorkspaceMode.TEMPORAL,
            seed_query=request.seed_query,
            mission_id=request.mission_id,
            project_id=request.project_id,
            trace_id=trace_id,
            camera_bookmark=None,
        )
        session.add(db_inv)
        await session.flush()

        # Bind initial scenes to slots
        for idx, sc_id in enumerate(request.scene_ids):
            role = SceneRole.T0 if idx == 0 else (SceneRole.T1 if idx == 1 else SceneRole.AUX)
            slot = DbInvestigationScene(
                investigation_id=inv_id,
                scene_id=sc_id,
                role=role,
            )
            session.add(slot)

        await session.commit()

        return InvestigationCreateResponse(
            investigation_id=inv_id,
            area_of_interest_name=aoi_name,
            area_of_interest=bbox,
            camera_target=CameraTarget(
                latitude=centroid.y,
                longitude=centroid.x,
                altitude_meters=altitude,
            ),
        )


async def get_investigation(investigation_id: str) -> Investigation:
    """Retrieve full investigation record with scene slots and historical acquisitions."""
    async with database.get_session() as session:
        stmt = select(DbInvestigation).where(DbInvestigation.id == investigation_id)
        result = await session.execute(stmt)
        db_inv = result.scalar_one_or_none()

        if db_inv is None:
            raise ResourceNotFoundError(
                f"Investigation {investigation_id} not found",
                details={"investigationId": investigation_id},
            )

        # Fetch scene bindings
        slots_stmt = select(DbInvestigationScene).where(DbInvestigationScene.investigation_id == investigation_id)
        slots_res = await session.execute(slots_stmt)
        db_slots = list(slots_res.scalars().all())

        # Fetch scene details
        scene_ids = [s.scene_id for s in db_slots]
        scenes_map: dict[str, DbScene] = {}
        if scene_ids:
            sc_stmt = select(DbScene).where(DbScene.id.in_(scene_ids))
            sc_res = await session.execute(sc_stmt)
            for sc in sc_res.scalars().all():
                scenes_map[sc.id] = sc

        scene_slots: list[InvestigationSceneSlot] = []
        for s in db_slots:
            sc = scenes_map.get(s.scene_id)
            if sc:
                sc_platform = sc.sensor_platform.value if hasattr(sc.sensor_platform, "value") else str(sc.sensor_platform)
                sc_modality = sc.modality.value if hasattr(sc.modality, "value") else str(sc.modality)
                scene_slots.append(
                    InvestigationSceneSlot(
                        role=s.role.value if hasattr(s.role, "value") else str(s.role),
                        scene_id=sc.id,
                        name=f"{sc_platform.upper()} {sc.captured_at.strftime('%Y-%m-%d')}",
                        captured_at=sc.captured_at,
                        modality=sc_modality,
                        sensor_platform=sc_platform,
                        ground_sample_distance_meters=sc.ground_sample_distance_meters,
                        cloud_cover_percentage=sc.cloud_cover_percentage,
                        coordinate_reference_system=sc.coordinate_reference_system or "EPSG:4326",
                        layer_id=f"lay_{sc.id}",
                    )
                )

        # Fetch acquisitions (all scenes in catalogue or overlapping)
        acq_stmt = select(DbScene).order_by(DbScene.captured_at.asc()).limit(30)
        acq_res = await session.execute(acq_stmt)
        all_scenes = list(acq_res.scalars().all())

        acquisitions: list[Acquisition] = []
        for sc in all_scenes:
            sc_platform = sc.sensor_platform.value if hasattr(sc.sensor_platform, "value") else str(sc.sensor_platform)
            sc_modality = sc.modality.value if hasattr(sc.modality, "value") else str(sc.modality)
            acquisitions.append(
                Acquisition(
                    id=f"acq_{sc.id}",
                    scene_id=sc.id,
                    captured_at=sc.captured_at,
                    modality=sc_modality,
                    sensor_platform=sc_platform,
                    ground_sample_distance_meters=sc.ground_sample_distance_meters,
                    cloud_cover_percentage=sc.cloud_cover_percentage,
                    quicklook_url=sc.thumbnail_url,
                    tiles=AcquisitionTiles(
                        url_template=f"/api/v1/tiles/{sc.id}/{{z}}/{{x}}/{{y}}.png",
                        attribution="Copernicus Sentinel data",
                        minimum_zoom=8,
                        maximum_zoom=14,
                    ),
                    is_available=True,
                )
            )

        poly = to_shape(db_inv.area_of_interest)
        centroid = to_shape(db_inv.centroid)
        bbox = _poly_to_bbox(poly)

        camera_bm = None
        if db_inv.camera_bookmark:
            camera_bm = CameraBookmark(
                latitude=db_inv.camera_bookmark.get("latitude", centroid.y),
                longitude=db_inv.camera_bookmark.get("longitude", centroid.x),
                altitude_meters=db_inv.camera_bookmark.get("altitudeMeters", 50000.0),
                heading_degrees=db_inv.camera_bookmark.get("headingDegrees", 0.0),
                pitch_degrees=db_inv.camera_bookmark.get("pitchDegrees", -45.0),
            )

        return Investigation(
            id=db_inv.id,
            name=db_inv.name,
            area_of_interest_name=db_inv.area_of_interest_name,
            area_of_interest=bbox,
            centroid=GeoPoint(latitude=centroid.y, longitude=centroid.x),
            status=db_inv.status.value if hasattr(db_inv.status, "value") else str(db_inv.status),
            mode=db_inv.mode.value if hasattr(db_inv.mode, "value") else str(db_inv.mode),
            created_at=db_inv.created_at,
            updated_at=db_inv.updated_at,
            scene_slots=scene_slots,
            acquisitions=acquisitions,
            camera_bookmark=camera_bm,
            seed_query=db_inv.seed_query,
            mission_id=db_inv.mission_id,
            project_id=db_inv.project_id or "prj_default",
            trace_id=db_inv.trace_id,
            events=[],
            layer_notes={},
        )


async def list_investigations(limit: int = 50) -> InvestigationList:
    """List investigations ordered by recency."""
    async with database.get_session() as session:
        stmt = select(DbInvestigation).order_by(DbInvestigation.updated_at.desc()).limit(limit)
        result = await session.execute(stmt)
        rows = list(result.scalars().all())

        items = [
            InvestigationSummary(
                id=r.id,
                name=r.name,
                area_of_interest_name=r.area_of_interest_name,
                status=r.status.value if hasattr(r.status, "value") else str(r.status),
                mode=r.mode.value if hasattr(r.mode, "value") else str(r.mode),
                updated_at=r.updated_at,
                trace_id=r.trace_id,
            )
            for r in rows
        ]
        return InvestigationList(items=items)


async def patch_investigation(investigation_id: str, patch_data: dict[str, Any]) -> Investigation:
    """Update editable investigation properties."""
    async with database.get_session() as session:
        stmt = select(DbInvestigation).where(DbInvestigation.id == investigation_id)
        result = await session.execute(stmt)
        db_inv = result.scalar_one_or_none()
        if db_inv is None:
            raise ResourceNotFoundError(f"Investigation {investigation_id} not found")

        if "name" in patch_data and patch_data["name"] is not None:
            db_inv.name = patch_data["name"]
        if "status" in patch_data and patch_data["status"] is not None:
            db_inv.status = InvestigationStatus(patch_data["status"])
        if "mode" in patch_data and patch_data["mode"] is not None:
            db_inv.mode = WorkspaceMode(patch_data["mode"])
        if "camera_bookmark" in patch_data and patch_data["camera_bookmark"] is not None:
            bm = patch_data["camera_bookmark"]
            db_inv.camera_bookmark = bm if isinstance(bm, dict) else bm.model_dump(by_alias=True)

        db_inv.updated_at = datetime.now(UTC)
        await session.commit()

    return await get_investigation(investigation_id)


async def attach_scene_slot(investigation_id: str, scene_id: str, role_str: str) -> Investigation:
    """Bind a scene to an investigation slot with singular role index enforcement."""
    role = SceneRole(role_str)
    async with database.get_session() as session:
        # Check investigation exists
        inv = await session.get(DbInvestigation, investigation_id)
        if inv is None:
            raise ResourceNotFoundError(f"Investigation {investigation_id} not found")

        # Check scene exists
        sc = await session.get(DbScene, scene_id)
        if sc is None:
            raise ResourceNotFoundError(f"Scene {scene_id} not found")

        if role != SceneRole.AUX:
            # Delete existing binding for singular role
            del_stmt = delete(DbInvestigationScene).where(
                DbInvestigationScene.investigation_id == investigation_id,
                DbInvestigationScene.role == role,
            )
            await session.execute(del_stmt)

        # Also remove if this scene is already bound to this role
        del_same = delete(DbInvestigationScene).where(
            DbInvestigationScene.investigation_id == investigation_id,
            DbInvestigationScene.scene_id == scene_id,
            DbInvestigationScene.role == role,
        )
        await session.execute(del_same)

        new_slot = DbInvestigationScene(
            investigation_id=investigation_id,
            scene_id=scene_id,
            role=role,
        )
        session.add(new_slot)
        inv.updated_at = datetime.now(UTC)
        await session.commit()

    return await get_investigation(investigation_id)


async def save_camera_bookmark(investigation_id: str, bookmark: CameraBookmark) -> None:
    """Save camera pose bookmark."""
    async with database.get_session() as session:
        inv = await session.get(DbInvestigation, investigation_id)
        if inv is None:
            raise ResourceNotFoundError(f"Investigation {investigation_id} not found")
        inv.camera_bookmark = bookmark.model_dump(by_alias=True)
        inv.updated_at = datetime.now(UTC)
        await session.commit()


async def get_preview_plan(investigation_id: str, from_claim_id: str | None = None) -> AnalysisPlan:
    """Generate an autonomous analysis plan using the router and LLM planner.

    Routes the request dynamically using `route_plan()`, maps routing decisions to steps,
    and constructs validated plan prose via `build_plan()` and the configured chat model.
    Falls back to router template prose if no model is configured or LLM check fails.
    """
    inv = await get_investigation(investigation_id)

    # Resolve scene facts from attached slots
    modalities = tuple(
        Modality.SAR if slot.modality.lower() == "sar" else Modality.OPTICAL
        for slot in inv.scene_slots
    ) or (Modality.OPTICAL,)
    acquisitions = 2 if any(s.role == "t1" for s in inv.scene_slots) else max(len(inv.scene_slots), 1)
    gsds = [s.ground_sample_distance_meters for s in inv.scene_slots if s.ground_sample_distance_meters is not None]
    resolution = min(gsds) if gsds else 10.0
    facts = SceneFacts(resolution, acquisitions, modalities)

    query = inv.seed_query or "Evaluate surface condition and canopy vitality across the observation area."
    if from_claim_id:
        query = f"Verify and evaluate evidence behind claim {from_claim_id}: {query}"

    encoder, bank = await routing_resources()
    arbiter = routing_arbiter()
    routing_plan = await route_plan(query, encoder=encoder, bank=bank, facts=facts, arbiter=arbiter)
    steps = [describe_step(i, d) for i, d in enumerate(routing_plan.steps, start=1)]

    model = build_chat_model()
    agent_plan, _ = await build_plan(query, steps, model=model)

    plan_steps = [
        AnalysisPlanStep(
            id=s.id,
            operation_id=s.operation_id,
            stage_code=s.stage_code.value if hasattr(s.stage_code, "value") else str(s.stage_code),
            inputs=s.inputs,
            parameters=s.parameters,
            outputs=s.outputs,
            model=s.model,
            rationale=s.rationale,
            depends_on=s.depends_on,
            title=s.title,
            description=s.description,
            is_enabled=s.is_enabled,
        )
        for s in agent_plan.steps
    ]
    return AnalysisPlan(
        id=agent_plan.id,
        summary=agent_plan.summary,
        steps=plan_steps,
    )


async def get_investigation_evidence(investigation_id: str) -> EvidenceGraphResponse:
    """Retrieve the flat evidence graph aggregated from real executed runs.

    If no runs have executed yet, returns an empty graph (truth in evidence; zero fake claims).
    """
    async with database.get_session() as session:
        stmt = (
            select(DbRun)
            .where(DbRun.investigation_id == investigation_id)
            .order_by(DbRun.started_at.desc())
        )
        result = await session.execute(stmt)
        runs = list(result.scalars().all())

    if not runs:
        return EvidenceGraphResponse(
            claims=[],
            evidence=[],
            layers=[],
            generated_at=datetime.now(UTC),
        )

    claims_map: dict[str, Claim] = {}
    layers_map: dict[str, EvidenceLayer] = {}
    evidence_map: dict[str, EvidenceItem] = {}

    for run in runs:
        try:
            for event in read_journal(run.id):
                if event.event == "claim" and hasattr(event, "data"):
                    claims_map[event.data.id] = event.data
                elif event.event == "layer-ready" and hasattr(event, "data") and hasattr(event.data, "layer"):
                    layers_map[event.data.layer.id] = event.data.layer
        except Exception as err:
            logger.debug("Failed reading run journal for evidence aggregation", extra={"run_id": run.id, "error": str(err)})
            continue

    # Assemble evidence items referenced by claims
    for claim in claims_map.values():
        for evi_id in claim.evidence_ids:
            if evi_id not in evidence_map:
                evidence_map[evi_id] = EvidenceItem(
                    id=evi_id,
                    kind=EvidenceKind.SPECTRAL_INDEX,
                    title=f"Evidence for {claim.id}",
                    layer_id=claim.model_id,
                    feature_ids=[],
                    area_hectares=next((m.value for m in claim.metrics if m.unit == "ha"), None),
                    magnitude=None,
                    confidence=claim.confidence,
                    source_scene_ids=[],
                )

    return EvidenceGraphResponse(
        claims=list(claims_map.values()),
        evidence=list(evidence_map.values()),
        layers=list(layers_map.values()),
        generated_at=datetime.now(UTC),
    )


class _LLMSuggestionItem(BaseModel):
    label: str = Field(description="Short 2-3 word topic name, e.g. Surface Disturbance, Canopy Vigor, Water Inundation")
    prompt: str = Field(description="Precise analytical question for an EO specialist regarding this sub-region")


class _LLMSuggestionResult(BaseModel):
    suggestions: list[_LLMSuggestionItem] = Field(min_length=3, max_length=4)


async def get_region_suggestions(investigation_id: str, bounds: dict[str, float]) -> RegionSuggestionCollection:
    """Generate dynamic, contextual prompt suggestions for a drawn bounding box."""
    north = bounds["north"]
    south = bounds["south"]
    east = bounds["east"]
    west = bounds["west"]

    centroid_lat = (north + south) / 2.0
    centroid_lon = (east + west) / 2.0
    width_m = abs(east - west) * math.cos(math.radians(centroid_lat)) * 111320.0
    height_m = abs(north - south) * 110540.0
    area_ha = max(round((width_m * height_m) / 10000.0, 1), 0.1)

    inv = await get_investigation(investigation_id)
    sensors = [f"{s.sensor_platform} ({s.modality})" for s in inv.scene_slots]
    sensors_str = ", ".join(sensors) if sensors else "Multispectral optical (10m GSD)"
    has_sar = any(s.modality.lower() == "sar" for s in inv.scene_slots)
    has_optical = any(s.modality.lower() == "optical" for s in inv.scene_slots) or not inv.scene_slots
    has_pair = len(inv.scene_slots) >= 2 or any(s.role == "t1" for s in inv.scene_slots)
    dates = sorted([s.captured_at for s in inv.scene_slots if s.captured_at])
    time_span_str = (
        f"from {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}"
        if len(dates) >= 2
        else "single acquisition"
    )

    model = build_chat_model()
    if model is None:
        raise UpstreamUnavailableError("Language model is unavailable for dynamic region suggestions.")

    user_prompt = REGION_SUGGESTION_USER_TEMPLATE.format(
        west=west,
        south=south,
        east=east,
        north=north,
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
        area_ha=area_ha,
        inv_name=inv.name,
        aoi_name=inv.area_of_interest_name,
        sensors=sensors_str,
        time_span=time_span_str,
        seed_query=inv.seed_query or "General environmental and land monitoring",
    )
    try:
        structured_llm = model.with_structured_output(_LLMSuggestionResult)
        result = await structured_llm.ainvoke([
            ("system", REGION_SUGGESTION_SYSTEM_PROMPT),
            ("human", user_prompt),
        ])
    except Exception as err:
        logger.error("Dynamic LLM region suggestion generation failed", extra={"error": str(err)})
        raise UpstreamUnavailableError(f"Dynamic LLM region suggestion generation failed: {err}") from err

    if result and result.suggestions:
        return RegionSuggestionCollection(
            suggestions=[
                RegionSuggestion(
                    id=new_identifier(IdentifierPrefix.SUGGESTION),
                    label=s.label.strip(),
                    prompt=s.prompt.strip(),
                )
                for s in result.suggestions
            ]
        )
    raise UpstreamUnavailableError("Language model returned no suggestions for the selected region.")

