"""Controller for 3D globe visualization feeds (markers, satellite tracks).

Returns unpaginated collections optimized for instanced WebGL/Cesium draw calls.
"""

from datetime import UTC, datetime

from geoalchemy2.shape import to_shape
from sqlalchemy import select

from app.db.models.investigation import Investigation
from app.db.models.mission import Mission as DbMission
from app.lib import database
from app.schemas.geo import GeoPoint
from app.schemas.missions import (
    GlobeMarker,
    GlobeMarkerCollection,
    SatelliteTrack,
    SatelliteTrackCollection,
)
from app.services.globe.math.orbit import SENTINEL_CONSTELLATION, propagate_track


async def get_globe_markers() -> GlobeMarkerCollection:
    """Retrieve active globe markers from database investigations and missions."""
    markers: list[GlobeMarker] = []
    now = datetime.now(UTC)

    try:
        async with database.get_session() as session:
            inv_stmt = (
                select(Investigation)
                .where(Investigation.centroid.is_not(None))
                .order_by(Investigation.updated_at.desc())
                .limit(50)
            )
            inv_result = await session.execute(inv_stmt)
            investigations = inv_result.scalars().all()

            for inv in investigations:
                centroid_geom = to_shape(inv.centroid)
                markers.append(
                    GlobeMarker(
                        id=f"mrk_{inv.id}",
                        project_id=inv.project_id,
                        mission_id=None,
                        label=inv.name,
                        position=GeoPoint(latitude=centroid_geom.y, longitude=centroid_geom.x),
                        status="active",
                        magnitude=0.0,
                    )
                )

            msn_stmt = (
                select(DbMission)
                .where(DbMission.centroid.is_not(None))
                .order_by(DbMission.updated_at.desc())
                .limit(50)
            )
            msn_result = await session.execute(msn_stmt)
            missions = msn_result.scalars().all()

            for msn in missions:
                centroid_geom = to_shape(msn.centroid)
                status = msn.status.value if hasattr(msn.status, "value") else str(msn.status)
                markers.append(
                    GlobeMarker(
                        id=f"mrk_{msn.id}",
                        project_id=msn.project_id,
                        mission_id=msn.id,
                        label=msn.name,
                        position=GeoPoint(latitude=centroid_geom.y, longitude=centroid_geom.x),
                        status=status,
                        magnitude=0.0,
                    )
                )
    except Exception:
        markers = []

    return GlobeMarkerCollection(
        markers=markers,
        generated_at=now,
    )


async def get_satellite_tracks() -> SatelliteTrackCollection:
    """Retrieve active ambient satellite orbital tracks computed from physical Keplerian elements."""
    now = datetime.now(UTC)
    tracks: list[SatelliteTrack] = []

    for params in SENTINEL_CONSTELLATION:
        origin, destination, phase = propagate_track(params, now)
        tracks.append(
            SatelliteTrack(
                id=f"trk_{params.platform.lower().replace('-', '')}",
                platform=params.platform,
                origin=GeoPoint(latitude=origin[0], longitude=origin[1]),
                destination=GeoPoint(latitude=destination[0], longitude=destination[1]),
                phase=phase,
            )
        )

    return SatelliteTrackCollection(
        tracks=tracks,
        generated_at=now,
    )

