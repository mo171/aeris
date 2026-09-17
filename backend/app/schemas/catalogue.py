"""Pydantic schemas for temporal catalogue search.

Mirrors frontend/features/investigation/schemas/catalogue.schema.ts exactly.
"""

from datetime import datetime

from pydantic import Field, model_validator

from app.constants.scenes import SceneModality
from app.lib.responses import CamelCaseModel
from app.schemas.geo import GeoBoundingBox


class TemporalQueryRequest(CamelCaseModel):
    """The search window and spatial bounds sent to the catalogue."""

    area_of_interest: GeoBoundingBox
    from_: datetime = Field(alias="from")
    to: datetime
    modalities: list[SceneModality] = Field(min_length=1)
    maximum_cloud_percentage: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_window(self) -> "TemporalQueryRequest":
        if self.from_ >= self.to:
            raise ValueError("The start of the window must fall before its end.")
        return self


class CoverageGap(CamelCaseModel):
    """A stretch of the requested window with no usable acquisition."""

    from_: datetime = Field(alias="from")
    to: datetime
    days: int = Field(ge=0)
    reason: str = Field(min_length=1)


class PairRecommendation(CamelCaseModel):
    """The recommended before/after pair for temporal comparison."""

    t0_scene_id: str = Field(min_length=1)
    t1_scene_id: str = Field(min_length=1)
    separation_days: int = Field(ge=0)
    reason: str = Field(min_length=1)


class AcquisitionTiles(CamelCaseModel):
    """Where the tiles for this acquisition live."""

    url_template: str = Field(min_length=1)
    attribution: str | None = None
    minimum_zoom: int = Field(ge=0)
    maximum_zoom: int = Field(ge=0)


class Acquisition(CamelCaseModel):
    """One catalogued acquisition matching the search window."""

    id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    captured_at: datetime
    modality: SceneModality
    sensor_platform: str = Field(min_length=1)
    ground_sample_distance_meters: float = Field(gt=0)
    cloud_cover_percentage: float | None = None
    quicklook_url: str | None = None
    tiles: AcquisitionTiles | None = None
    is_available: bool = True


class CatalogueSearchResponse(CamelCaseModel):
    """The complete response matching the temporal query."""

    query: TemporalQueryRequest
    acquisitions: list[Acquisition]
    coverage_gaps: list[CoverageGap]
    recommended_pair: PairRecommendation | None = None
    advisory: str | None = None
