"""Controller for 3D globe visualization feeds (markers, satellite tracks).

Returns unpaginated collections optimized for instanced WebGL/Cesium draw calls.
"""

from datetime import UTC, datetime

from app.schemas.geo import GeoPoint
from app.schemas.missions import (
    GlobeMarker,
    GlobeMarkerCollection,
    SatelliteTrack,
    SatelliteTrackCollection,
)


async def get_globe_markers() -> GlobeMarkerCollection:
    """Retrieve all active globe markers."""
    markers = [
        GlobeMarker(
            id="mrk_01mumbai",
            project_id="prj_default",
            mission_id="msn_01sentinel_monitoring",
            label="Mumbai Harbor AOI",
            position=GeoPoint(latitude=18.95, longitude=72.85),
            status="active",
            magnitude=0.75,
        ),
        GlobeMarker(
            id="mrk_02delhi",
            project_id="prj_default",
            mission_id=None,
            label="NCR Urban Observatory",
            position=GeoPoint(latitude=28.61, longitude=77.23),
            status="monitoring",
            magnitude=0.45,
        ),
    ]
    return GlobeMarkerCollection(
        markers=markers,
        generated_at=datetime.now(UTC),
    )


async def get_satellite_tracks() -> SatelliteTrackCollection:
    """Retrieve active ambient satellite orbital tracks."""
    tracks = [
        SatelliteTrack(
            id="trk_s2a",
            platform="Sentinel-2A",
            origin=GeoPoint(latitude=12.0, longitude=65.0),
            destination=GeoPoint(latitude=35.0, longitude=85.0),
            phase=0.42,
        ),
        SatelliteTrack(
            id="trk_s1b",
            platform="Sentinel-1B",
            origin=GeoPoint(latitude=-5.0, longitude=70.0),
            destination=GeoPoint(latitude=25.0, longitude=90.0),
            phase=0.78,
        ),
    ]
    return SatelliteTrackCollection(
        tracks=tracks,
        generated_at=datetime.now(UTC),
    )
