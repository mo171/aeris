"""The two geographic primitives every wire payload shares, so a latitude means the same thing on every surface.

what  : `GeoPoint` and `GeoBoundingBox` - WGS 84 degrees, bounded, camelCase.
where : Composed by the layer and evidence event models, and by every Phase 2 payload that carries a
        place. Mirrors `frontend/lib/schemas/geo.schema.ts` exactly.
how   : Degrees in EPSG:4326 and nothing else. Every geometry on the wire is latitude/longitude
        (`constants/geo.py`, `STORAGE_SRID`); a projected coordinate that reached here would validate as a
        latitude of 2,113,350 and fail loudly, which is the point of the bounds.
"""

from pydantic import Field

from app.lib.responses import CamelCaseModel


class GeoPoint(CamelCaseModel):
    """One position, WGS 84."""

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)


class GeoBoundingBox(CamelCaseModel):
    """An axis-aligned extent, WGS 84."""

    west: float = Field(ge=-180.0, le=180.0)
    south: float = Field(ge=-90.0, le=90.0)
    east: float = Field(ge=-180.0, le=180.0)
    north: float = Field(ge=-90.0, le=90.0)
