"""Wire models for investigations, scene slots, plans, and regions.

Conforms strictly to frontend Zod schemas in:
- features/investigation/schemas/investigation.schema.ts
- features/investigation/schemas/analysis.schema.ts
- features/investigation/schemas/evidence.schema.ts
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.lib.responses import CamelCaseModel
from app.schemas.events.claim import Claim
from app.schemas.events.layer import EvidenceItem, EvidenceLayer
from app.schemas.geo import GeoBoundingBox, GeoPoint


class CameraTarget(CamelCaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    altitude_meters: float = Field(gt=0.0)


class CameraBookmark(CamelCaseModel):
    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    altitude_meters: float = Field(gt=0.0)
    heading_degrees: float
    pitch_degrees: float


class InvestigationCreateRequest(CamelCaseModel):
    project_id: str = Field(min_length=1)
    scene_ids: list[str] = Field(min_length=1)
    seed_query: str | None = None
    mission_id: str | None = None


class InvestigationCreateResponse(CamelCaseModel):
    investigation_id: str = Field(min_length=1)
    area_of_interest_name: str = Field(min_length=1)
    area_of_interest: GeoBoundingBox
    camera_target: CameraTarget


class InvestigationSummary(CamelCaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    area_of_interest_name: str = Field(min_length=1)
    status: Literal["draft", "running", "ready", "failed"]
    mode: Literal["temporal", "crossModal"]
    updated_at: datetime
    trace_id: str = Field(min_length=1)


class InvestigationList(CamelCaseModel):
    items: list[InvestigationSummary]


class InvestigationSceneSlot(CamelCaseModel):
    role: Literal["t0", "t1", "sar", "aux"]
    scene_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    captured_at: datetime
    modality: Literal["optical", "sar", "multispectral", "hyperspectral"]
    sensor_platform: str = Field(min_length=1)
    ground_sample_distance_meters: float = Field(gt=0.0)
    cloud_cover_percentage: float | None = Field(default=None, ge=0.0, le=100.0)
    coordinate_reference_system: str = Field(min_length=1)
    layer_id: str = Field(min_length=1)


class AcquisitionTiles(CamelCaseModel):
    url_template: str = Field(min_length=1)
    attribution: str | None = None
    minimum_zoom: int = Field(ge=0)
    maximum_zoom: int = Field(ge=0)


class Acquisition(CamelCaseModel):
    id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    captured_at: datetime
    modality: Literal["optical", "sar", "multispectral", "hyperspectral"]
    sensor_platform: str = Field(min_length=1)
    ground_sample_distance_meters: float = Field(gt=0.0)
    cloud_cover_percentage: float | None = Field(default=None, ge=0.0, le=100.0)
    quicklook_url: str | None = None
    tiles: AcquisitionTiles | None = None
    is_available: bool = True


class TimelineEventAnnotation(CamelCaseModel):
    id: str = Field(min_length=1)
    date: datetime
    label: str = Field(min_length=1)
    description: str | None = None
    kind: Literal["construction", "natural-event", "policy", "conflict", "observation", "custom"]


class Investigation(CamelCaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    area_of_interest_name: str = Field(min_length=1)
    area_of_interest: GeoBoundingBox
    centroid: GeoPoint
    status: Literal["draft", "running", "ready", "failed"]
    mode: Literal["temporal", "crossModal"]
    created_at: datetime
    updated_at: datetime
    scene_slots: list[InvestigationSceneSlot]
    acquisitions: list[Acquisition]
    camera_bookmark: CameraBookmark | None = None
    seed_query: str | None = None
    mission_id: str | None = None
    project_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    events: list[TimelineEventAnnotation] = Field(default_factory=list)
    layer_notes: dict[str, str] = Field(default_factory=dict)


class AttachSceneRequest(CamelCaseModel):
    scene_id: str = Field(min_length=1)
    role: Literal["t0", "t1", "sar", "aux"]


class SaveCameraBookmarkRequest(CamelCaseModel):
    camera_bookmark: CameraBookmark


class PatchInvestigationRequest(CamelCaseModel):
    name: str | None = None
    status: Literal["draft", "running", "ready", "failed"] | None = None
    mode: Literal["temporal", "crossModal"] | None = None
    layer_notes: dict[str, str] | None = None
    camera_bookmark: CameraBookmark | None = None


class AnalysisRunRequest(CamelCaseModel):
    investigation_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    region_bounds: GeoBoundingBox | None = None
    plan_id: str | None = None
    operation_id: str | None = None
    parameter_overrides: dict[str, Any] | None = None
    rerun_from_step_id: str | None = None
    parent_run_id: str | None = None


class AnalysisPlanStep(CamelCaseModel):
    id: str = Field(min_length=1)
    operation_id: str | None = None
    stage_code: str = Field(min_length=1)
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    model: dict[str, Any] | None = None
    rationale: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    is_enabled: bool = True


class AnalysisPlan(CamelCaseModel):
    id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    steps: list[AnalysisPlanStep]


class RegionSuggestion(CamelCaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    prompt: str = Field(min_length=1)


class RegionSuggestionCollection(CamelCaseModel):
    suggestions: list[RegionSuggestion]


class EvidenceGraphResponse(CamelCaseModel):
    claims: list[Claim]
    evidence: list[EvidenceItem]
    layers: list[EvidenceLayer]
    generated_at: datetime
