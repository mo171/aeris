"""Background ingestion task for uploaded satellite scenes.

Handles S1-S6 quality inspection, Cloud-Optimized GeoTIFF (COG) transformation,
and database status progression from QUEUED/PROCESSING to READY or FAILED.
"""

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from geoalchemy2.shape import from_shape
from shapely.geometry import Point, box
from sqlalchemy import select

from app.config import settings
from app.constants.geo import STORAGE_SRID
from app.constants.statuses import SceneProcessingState
from app.constants.storage import Bucket
from app.db.models.scene import Scene
from app.lib import database, storage
from app.lib.exceptions import ConflictError, InvalidRequestError
from app.services.imagery.cog import convert_to_cog, upload_cog
from app.services.imagery.metadata import inspect_raster
from app.services.imagery.validation import require_analysable

logger = logging.getLogger(__name__)


async def run_scene_ingest(
    scene_id: str,
    raw_object_key: str,
    *,
    raise_on_failure: bool = False,
) -> dict[str, Any]:
    """Execute background ingestion for a confirmed uploaded scene."""
    import inngest

    logger.info("starting background ingest for scene", extra={"scene_id": scene_id, "key": raw_object_key})

    temp_dir = Path(settings.cog_working_directory)
    await asyncio.to_thread(temp_dir.mkdir, parents=True, exist_ok=True)
    local_raw_path = temp_dir / f"{scene_id}_raw.tif"
    local_cog_path = temp_dir / f"{scene_id}_cog.tif"

    try:
        # 1. Download raw bytes from storage
        raw_bytes = await storage.get_object(Bucket.RAW, raw_object_key)
        await asyncio.to_thread(local_raw_path.write_bytes, raw_bytes)

        # 2. Inspect raster metadata (S1-S3)
        metadata = await inspect_raster(local_raw_path)
        report = await require_analysable(metadata)

        if not report.is_analysable:
            problems = [p.reason for p in report.problems]
            logger.warning("uploaded raster failed analysis requirements", extra={"problems": len(problems)})
            await _update_scene_state(scene_id, SceneProcessingState.FAILED)
            if raise_on_failure:
                raise inngest.NonRetriableError(
                    f"Uploaded raster failed analysis requirements: {problems}"
                )
            return {"scene_id": scene_id, "status": SceneProcessingState.FAILED.value, "problems": problems}

        # 3. Convert to COG (S4-S5)
        await convert_to_cog(metadata, local_cog_path)

        # 4. Upload COG to browser-facing Bucket.COG
        cog_key = f"cogs/{scene_id}.tif"
        await upload_cog(local_cog_path, object_key=cog_key, bucket=Bucket.COG)

        # 5. Extract geometry & update database record (always in STORAGE_SRID 4326)
        minx, miny, maxx, maxy = metadata.bounds
        if metadata.crs and metadata.crs != "EPSG:4326":
            from rasterio.warp import transform_bounds
            minx, miny, maxx, maxy = transform_bounds(metadata.crs, "EPSG:4326", minx, miny, maxx, maxy)

        geom_box = box(minx, miny, maxx, maxy)
        geom_point = Point((minx + maxx) / 2.0, (miny + maxy) / 2.0)

        async with database.get_session() as session:
            result = await session.execute(select(Scene).where(Scene.id == scene_id))
            scene = result.scalar_one_or_none()
            if scene:
                scene.processing_state = SceneProcessingState.READY
                scene.cog_object_key = cog_key
                scene.band_count = metadata.band_count
                scene.ground_sample_distance_meters = metadata.resolution[0]
                scene.coordinate_reference_system = metadata.crs or "EPSG:4326"
                scene.footprint = from_shape(geom_box, srid=STORAGE_SRID)
                scene.centroid = from_shape(geom_point, srid=STORAGE_SRID)
                await session.commit()
                logger.info("scene successfully ingested and ready", extra={"scene_id": scene_id})

        return {
            "scene_id": scene_id,
            "status": SceneProcessingState.READY.value,
            "cog_object_key": cog_key,
        }

    except (InvalidRequestError, ConflictError) as exc:
        logger.warning("invalid raster for scene ingest", extra={"scene_id": scene_id, "error": str(exc)})
        await _update_scene_state(scene_id, SceneProcessingState.FAILED)
        if raise_on_failure:
            raise inngest.NonRetriableError(str(exc)) from exc
        return {"scene_id": scene_id, "status": SceneProcessingState.FAILED.value, "error": str(exc)}
    except Exception as exc:
        logger.warning("ingest failed for scene", extra={"scene_id": scene_id, "error": str(exc)})
        await _update_scene_state(scene_id, SceneProcessingState.FAILED)
        if raise_on_failure:
            raise
        return {"scene_id": scene_id, "status": SceneProcessingState.FAILED.value, "error": str(exc)}
    finally:
        # Cleanup temporary files
        if await asyncio.to_thread(local_raw_path.exists):
            await asyncio.to_thread(local_raw_path.unlink, missing_ok=True)
        if await asyncio.to_thread(local_cog_path.exists):
            await asyncio.to_thread(local_cog_path.unlink, missing_ok=True)


async def _update_scene_state(scene_id: str, state: SceneProcessingState) -> None:
    """Helper to update scene processing state in the database."""
    async with database.get_session() as session:
        result = await session.execute(select(Scene).where(Scene.id == scene_id))
        scene = result.scalar_one_or_none()
        if scene:
            scene.processing_state = state
            await session.commit()

