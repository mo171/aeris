"""Validated wire models for one optical/SAR late-fusion result."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.lib.responses import CamelCaseModel
from app.schemas.events.claim import Claim
from app.schemas.events.layer import EvidenceItem, EvidenceLayer

type SensorId = Literal["optical", "radar"]
type AgreementState = Literal["conflict", "corroborated", "optical-only", "radar-only"]
type FusionRefusalId = Literal[
    "poor-co-registration", "purely-spectral", "purely-structural", "auditability"
]


class SensorRun(CamelCaseModel):
    sensor: SensorId
    scene_id: str = Field(min_length=1)
    captured_at: datetime
    platform: str = Field(min_length=1)
    polarisation: Literal["VV", "VH", "ratio"] | None
    look_azimuth_degrees: float | None = Field(default=None, ge=0.0, le=360.0)
    incidence_angle_degrees: float | None = Field(default=None, ge=0.0, le=90.0)
    layers: list[EvidenceLayer]
    evidence: list[EvidenceItem]
    claims: list[Claim]
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    obscured_fraction: float = Field(ge=0.0, le=1.0)


class AgreementRow(CamelCaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    state: AgreementState
    reason: str = Field(min_length=1)
    optical_feature_ids: list[str]
    radar_feature_ids: list[str]
    optical_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    radar_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    area_hectares: float | None = Field(default=None, ge=0.0)


class ModalityAdvisory(CamelCaseModel):
    verdict: Literal["fair", "offset", "unusable"]
    offset_days: int = Field(ge=0)
    co_registration_pixels: float | None = Field(default=None, ge=0.0)
    notes: list[str]


class FusionVerdict(CamelCaseModel):
    headline: str | None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    refused_because: FusionRefusalId | None
    blocked_by_conflict: str | None
    rows: list[AgreementRow]


class CrossModalResult(CamelCaseModel):
    investigation_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    optical: SensorRun
    radar: SensorRun | None
    advisory: ModalityAdvisory
    verdict: FusionVerdict | None
    generated_at: datetime
