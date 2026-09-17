"""Pydantic schemas for missions, globe markers, and satellite tracks.

Mirrors frontend/features/missionCommand/schemas/mission.schema.ts exactly.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.lib.responses import CamelCaseModel
from app.schemas.geo import GeoPoint

MissionStatus = Literal["active", "monitoring", "alert", "archived"]
MissionAnalysisKind = Literal[
    "change-detection",
    "vegetation-health",
    "urban-growth",
    "flood-mapping",
    "cross-modal",
]


class Mission(CamelCaseModel):
    """One mission record."""

    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    template_version_id: str | None = None
    name: str = Field(min_length=1)
    status: MissionStatus
    analysis_kind: MissionAnalysisKind
    area_of_interest_name: str = Field(min_length=1)
    centroid: GeoPoint
    created_at: datetime
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    scene_count: int = Field(ge=0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    open_alert_count: int = Field(ge=0)
    summary: str
    cadence: str
    alert_rule: str | None = None


class GlobeMarker(CamelCaseModel):
    """A lightweight marker for the 3D globe display."""

    id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    mission_id: str | None = None
    label: str = Field(min_length=1)
    position: GeoPoint
    status: MissionStatus
    magnitude: float = Field(ge=0.0, le=1.0)


class GlobeMarkerCollection(CamelCaseModel):
    """Unpaginated collection of all globe markers for instanced rendering."""

    markers: list[GlobeMarker]
    generated_at: datetime


class SatelliteTrack(CamelCaseModel):
    """An ambient satellite track showing orbital arc position."""

    id: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    origin: GeoPoint
    destination: GeoPoint
    phase: float = Field(ge=0.0, le=1.0)


class SatelliteTrackCollection(CamelCaseModel):
    """Collection of satellite tracks for the 3D orbital visualization."""

    tracks: list[SatelliteTrack]
    generated_at: datetime
