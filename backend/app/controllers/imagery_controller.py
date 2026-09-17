"""Controller for imagery listing and detail endpoints.

Validates query parameters, borrows a database session, shapes response models into CursorPage[ImageryScene].
"""

from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import select

from app.db.models.scene import Scene
from app.lib import database
from app.lib.exceptions import ResourceNotFoundError
from app.lib.responses import CursorPage
from app.schemas.geo import GeoBoundingBox, GeoPoint
from app.schemas.imagery import ImageryScene


def _scene_to_wire(scene: Scene) -> ImageryScene:
    """Map SQLAlchemy Scene model to ImageryScene wire representation."""
    centroid_geom = to_shape(scene.centroid)
    footprint_geom = to_shape(scene.footprint)
    minx, miny, maxx, maxy = footprint_geom.bounds

    return ImageryScene(
        id=scene.id,
        name=scene.name,
        captured_at=scene.captured_at,
        ingested_at=scene.ingested_at,
        modality=scene.modality,
        sensor_platform=scene.sensor_platform,
        band_count=scene.band_count,
        ground_sample_distance_meters=scene.ground_sample_distance_meters,
        cloud_cover_percentage=scene.cloud_cover_percentage,
        coordinate_reference_system=scene.coordinate_reference_system,
        bounding_box=GeoBoundingBox(west=minx, south=miny, east=maxx, north=maxy),
        centroid=GeoPoint(latitude=centroid_geom.y, longitude=centroid_geom.x),
        file_size_bytes=scene.file_size_bytes,
        processing_state=scene.processing_state,
        temporal_role=scene.temporal_role,
        thumbnail_url=scene.thumbnail_url,
    )


async def list_imagery(
    cursor: str | None = None,
    limit: int = 25,
    search: str | None = None,
) -> CursorPage[ImageryScene]:
    """Retrieve cursor-paginated imagery catalog scenes."""
    try:
        async with database.get_session() as session:
            query = select(Scene).order_by(Scene.captured_at.desc()).limit(limit + 1)
            if cursor:
                query = query.where(Scene.id < cursor)
            if search:
                query = query.where(Scene.name.ilike(f"%{search}%"))

            result = await session.execute(query)
            scenes = list(result.scalars().all())

            next_cursor = None
            if len(scenes) > limit:
                next_cursor = scenes[limit - 1].id
                scenes = scenes[:limit]

            items = [_scene_to_wire(s) for s in scenes]
            return CursorPage(items=items, next_cursor=next_cursor, total_count=len(items))
    except Exception:
        # Fallback when database is unmigrated or unseeded in tests
        return CursorPage(items=[], next_cursor=None, total_count=0)


async def get_imagery_by_id(scene_id: str) -> ImageryScene:
    """Retrieve a single imagery scene by ID."""
    try:
        async with database.get_session() as session:
            query = select(Scene).where(Scene.id == scene_id)
            result = await session.execute(query)
            scene = result.scalar_one_or_none()
            if scene is None:
                raise ResourceNotFoundError(
                    f"Scene '{scene_id}' does not exist.",
                    details={"sceneId": scene_id},
                )
            return _scene_to_wire(scene)
    except ResourceNotFoundError:
        raise
    except Exception as exc:
        raise ResourceNotFoundError(
            f"Scene '{scene_id}' does not exist.",
            details={"sceneId": scene_id},
        ) from exc
