from datetime import datetime
from pydantic import Field
from app.lib.responses import CamelCaseModel
from app.schemas.geo import GeoBoundingBox, GeoPoint

class ProjectResponse(CamelCaseModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    area_of_interest_name: str = Field(default="Global AOI")
    area_of_interest: GeoBoundingBox | None = None
    centroid: GeoPoint | None = None
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime | None = None

class ProjectCreateRequest(CamelCaseModel):
    name: str = Field(min_length=1)
    area_of_interest_name: str = Field(min_length=1)
    area_of_interest: GeoBoundingBox
