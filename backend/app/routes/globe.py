"""Globe visualization route declarations.

Adheres to bcontext/folder-archtecture.md:
- Routes declare HTTP verbs and paths only. No business logic.
"""

from fastapi import APIRouter

from app.controllers import globe_controller
from app.schemas.missions import GlobeMarkerCollection, SatelliteTrackCollection

router = APIRouter(prefix="/globe", tags=["globe"])


@router.get("/markers", response_model=GlobeMarkerCollection)
async def get_globe_markers() -> GlobeMarkerCollection:
    """Retrieve unpaginated collection of all globe markers."""
    return await globe_controller.get_globe_markers()


@router.get("/satellite-tracks", response_model=SatelliteTrackCollection)
async def get_satellite_tracks() -> SatelliteTrackCollection:
    """Retrieve ambient orbital satellite tracks."""
    return await globe_controller.get_satellite_tracks()
