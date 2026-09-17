"""Pydantic schemas for satellite imagery acquisitions and catalogue entries.

Mirrors frontend/features/missionCommand/schemas/imagery.schema.ts exactly:
- camelCase on the wire via CamelCaseModel
- nullable cloud_cover_percentage for SAR
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.constants.scenes import SceneModality, TemporalRole
from app.constants.statuses import SceneProcessingState
from app.lib.responses import CamelCaseModel
from app.schemas.geo import GeoBoundingBox, GeoPoint


class ImageryScene(CamelCaseModel):
    """One scene in the catalogue, with its acquisition and spatial metadata."""

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    captured_at: datetime
    ingested_at: datetime
    modality: SceneModality
    sensor_platform: str = Field(min_length=1)
    band_count: int = Field(gt=0)
    ground_sample_distance_meters: float = Field(gt=0)
    cloud_cover_percentage: float | None = Field(default=None, ge=0.0, le=100.0)
    coordinate_reference_system: str = Field(min_length=1)
    bounding_box: GeoBoundingBox
    centroid: GeoPoint
    file_size_bytes: int = Field(ge=0)
    processing_state: SceneProcessingState
    temporal_role: TemporalRole
    thumbnail_url: str | None = None
