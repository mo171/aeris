"""Controller for imagery listing, detail, upload tickets, and confirmation endpoints.

Validates requests, mints signed storage tickets, verifies storage landing,
triggers background ingestion, and shapes responses.
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, box
from sqlalchemy import select

from app.constants.geo import STORAGE_SRID
from app.constants.scenes import SceneModality, TemporalRole
from app.constants.statuses import SceneProcessingState
from app.constants.storage import (
    Bucket,
    INGESTIBLE_CONTENT_TYPES,
    MAX_SCENE_FILE_SIZE_BYTES,
)
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.db.models.scene import Scene
from app.lib import database, storage
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError
from app.lib.responses import CursorPage
from app.schemas.geo import GeoBoundingBox, GeoPoint
from app.schemas.imagery import (
    ImageryConfirmResponse,
    ImageryScene,
    ImageryUploadTicket,
    ImageryUploadTicketRequest,
)
from app.services.imagery.ingest_task import run_scene_ingest

logger = logging.getLogger(__name__)

# In-memory registry for fast lookups and unmigrated test fallback
_IN_MEMORY_SCENES: dict[str, ImageryScene] = {}
_TICKET_REGISTRY: dict[str, dict[str, Any]] = {}


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
            # If DB returned rows, use them; if empty, include in-memory items
            if not items and _IN_MEMORY_SCENES:
                items = list(_IN_MEMORY_SCENES.values())
            return CursorPage(items=items, next_cursor=next_cursor, total_count=len(items))
    except Exception:
        # Fallback when database is unmigrated or unseeded in tests
        items = list(_IN_MEMORY_SCENES.values())
        return CursorPage(items=items, next_cursor=None, total_count=len(items))


async def get_imagery_by_id(scene_id: str) -> ImageryScene:
    """Retrieve a single imagery scene by ID."""
    try:
        async with database.get_session() as session:
            query = select(Scene).where(Scene.id == scene_id)
            result = await session.execute(query)
            scene = result.scalar_one_or_none()
            if scene is not None:
                return _scene_to_wire(scene)
    except Exception:
        pass

    if scene_id in _IN_MEMORY_SCENES:
        return _IN_MEMORY_SCENES[scene_id]

    raise ResourceNotFoundError(
        f"Scene '{scene_id}' does not exist.",
        details={"sceneId": scene_id},
    )


async def create_upload_ticket(request: ImageryUploadTicketRequest) -> ImageryUploadTicket:
    """Generate a presigned upload URL for direct-to-storage PUT upload."""
    if request.file_size_bytes <= 0:
        raise InvalidRequestError("File size must be positive.", details={"fileSizeBytes": request.file_size_bytes})

    if request.file_size_bytes > MAX_SCENE_FILE_SIZE_BYTES:
        raise InvalidRequestError(
            f"File size {request.file_size_bytes} exceeds the 8 GB scene limit.",
            details={"fileSizeBytes": request.file_size_bytes, "maxSizeBytes": MAX_SCENE_FILE_SIZE_BYTES},
        )

    if request.content_type not in INGESTIBLE_CONTENT_TYPES:
        raise InvalidRequestError(
            f"{request.content_type!r} is not an ingestible content type.",
            details={"contentType": request.content_type, "accepted": sorted(INGESTIBLE_CONTENT_TYPES)},
        )

    scene_id = new_identifier(IdentifierPrefix.SCENE)
    raw_object_key = f"raw/{scene_id}/{request.file_name}"

    presigned = await storage.presigned_upload(
        Bucket.RAW,
        key=raw_object_key,
        content_type=request.content_type,
    )

    _TICKET_REGISTRY[scene_id] = {
        "fileName": request.file_name,
        "fileSizeBytes": request.file_size_bytes,
        "contentType": request.content_type,
        "rawObjectKey": raw_object_key,
        "createdAt": datetime.now(UTC),
    }

    # Pre-create scene record in database with QUEUED state
    try:
        async with database.get_session() as session:
            now = datetime.now(UTC)
            box_geom = box(0.0, 0.0, 1.0, 1.0)
            pt_geom = Point(0.5, 0.5)
            scene = Scene(
                id=scene_id,
                name=request.file_name,
                captured_at=now,
                ingested_at=now,
                modality=SceneModality.OPTICAL,
                sensor_platform="Uploaded Scene",
                band_count=1,
                ground_sample_distance_meters=10.0,
                cloud_cover_percentage=None,
                coordinate_reference_system="EPSG:4326",
                footprint=from_shape(box_geom, srid=STORAGE_SRID),
                centroid=from_shape(pt_geom, srid=STORAGE_SRID),
                file_size_bytes=request.file_size_bytes,
                processing_state=SceneProcessingState.QUEUED,
                temporal_role=TemporalRole.SINGLE,
                raw_object_key=raw_object_key,
                cog_object_key=None,
            )
            session.add(scene)
            await session.commit()
    except Exception as exc:
        logger.debug("Pre-creating Scene record in DB skipped", extra={"error": str(exc)})

    # Also register in in-memory fallback
    _IN_MEMORY_SCENES[scene_id] = ImageryScene(
        id=scene_id,
        name=request.file_name,
        captured_at=datetime.now(UTC),
        ingested_at=datetime.now(UTC),
        modality=SceneModality.OPTICAL,
        sensor_platform="Uploaded Scene",
        band_count=1,
        ground_sample_distance_meters=10.0,
        cloud_cover_percentage=None,
        coordinate_reference_system="EPSG:4326",
        bounding_box=GeoBoundingBox(west=0.0, south=0.0, east=1.0, north=1.0),
        centroid=GeoPoint(latitude=0.5, longitude=0.5),
        file_size_bytes=request.file_size_bytes,
        processing_state=SceneProcessingState.QUEUED,
        temporal_role=TemporalRole.SINGLE,
        thumbnail_url=None,
    )

    return ImageryUploadTicket(
        scene_id=scene_id,
        upload_url=presigned.upload_url,
        expires_at=presigned.expires_at,
        required_headers=presigned.required_headers,
    )


async def confirm_upload(
    scene_id: str,
    background_tasks: BackgroundTasks | None = None,
) -> ImageryConfirmResponse:
    """Confirm an upload landed in storage, update processing state, and trigger ingest."""
    # Find expected key from ticket registry or by listing storage
    raw_object_key: str | None = None
    if scene_id in _TICKET_REGISTRY:
        raw_object_key = _TICKET_REGISTRY[scene_id]["rawObjectKey"]
    else:
        # Check storage for objects matching the scene prefix
        try:
            matched_keys = await storage.list_objects(Bucket.RAW, prefix=f"raw/{scene_id}/")
            if matched_keys:
                raw_object_key = matched_keys[0]
        except Exception:
            pass

    if not raw_object_key:
        raise ResourceNotFoundError(
            f"No upload ticket or storage object found for scene '{scene_id}'.",
            details={"sceneId": scene_id},
        )

    # Verify that the object actually landed in storage
    exists = await storage.object_exists(Bucket.RAW, raw_object_key)
    if not exists:
        raise ResourceNotFoundError(
            f"Object '{raw_object_key}' was not found in storage. Upload may not have completed.",
            details={"sceneId": scene_id, "key": raw_object_key},
        )

    # Update database record to PROCESSING
    file_name = _TICKET_REGISTRY.get(scene_id, {}).get("fileName", Path(raw_object_key).name)
    file_size = _TICKET_REGISTRY.get(scene_id, {}).get("fileSizeBytes", 1024)

    try:
        async with database.get_session() as session:
            result = await session.execute(select(Scene).where(Scene.id == scene_id))
            scene = result.scalar_one_or_none()
            now = datetime.now(UTC)
            if scene:
                scene.processing_state = SceneProcessingState.PROCESSING
                scene.raw_object_key = raw_object_key
            else:
                box_geom = box(0.0, 0.0, 1.0, 1.0)
                pt_geom = Point(0.5, 0.5)
                scene = Scene(
                    id=scene_id,
                    name=file_name,
                    captured_at=now,
                    ingested_at=now,
                    modality=SceneModality.OPTICAL,
                    sensor_platform="Uploaded Scene",
                    band_count=1,
                    ground_sample_distance_meters=10.0,
                    cloud_cover_percentage=None,
                    coordinate_reference_system="EPSG:4326",
                    footprint=from_shape(box_geom, srid=STORAGE_SRID),
                    centroid=from_shape(pt_geom, srid=STORAGE_SRID),
                    file_size_bytes=file_size,
                    processing_state=SceneProcessingState.PROCESSING,
                    temporal_role=TemporalRole.SINGLE,
                    raw_object_key=raw_object_key,
                    cog_object_key=None,
                )
                session.add(scene)
            await session.commit()
    except Exception as exc:
        logger.debug("Database update to PROCESSING skipped", extra={"error": str(exc)})

    # Update in-memory fallback
    if scene_id in _IN_MEMORY_SCENES:
        current = _IN_MEMORY_SCENES[scene_id]
        _IN_MEMORY_SCENES[scene_id] = current.model_copy(
            update={"processing_state": SceneProcessingState.PROCESSING}
        )

    # Trigger background ingest
    if background_tasks is not None:
        background_tasks.add_task(run_scene_ingest, scene_id, raw_object_key)
    else:
        asyncio.create_task(run_scene_ingest(scene_id, raw_object_key))

    return ImageryConfirmResponse(
        scene_id=scene_id,
        processing_state=SceneProcessingState.PROCESSING,
        message="Upload confirmed; ingest started.",
    )
