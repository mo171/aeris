"""Integration tests for Inngest scene ingestion (fn_ingest_scene) in AERIS (Phase 2.5).

Verifies:
1. fn_ingest_scene executes S1-S6 quality inspection and COG generation durably via Inngest step runner.
2. Scene processing state in PostgreSQL transitions to READY upon successful ingestion.
3. COG artifact is uploaded to Bucket.COG and verifiable in storage.
4. Non-retriable failure (unanalysable / corrupt raster) raises inngest.NonRetriableError and marks scene FAILED.
5. Retriable failure (e.g. transient storage failure) raises exception to trigger Inngest retry policy.
6. confirm_upload in imagery_controller dispatches EventName.SCENE_INGEST_REQUESTED to Inngest when serving is active.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import inngest
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.constants.scenes import SceneModality, TemporalRole
from app.constants.statuses import SceneProcessingState
from app.constants.storage import Bucket
from app.constants.tasks import EventName
from app.controllers.imagery_controller import confirm_upload
from app.db.models.scene import Scene
from app.inngest.functions.ingest_scene import fn_ingest_scene
from app.lib import database, storage

pytestmark = pytest.mark.integration


class MockStep:
    """Mock Inngest Step runner that executes handlers asynchronously."""

    async def run(self, step_id: str, handler: Any, *args: Any) -> Any:
        import inspect

        if inspect.iscoroutinefunction(handler):
            return await handler(*args)
        res = handler(*args)
        if inspect.isawaitable(res):
            return await res
        return res


def _create_test_geotiff_bytes() -> bytes:
    """Generate a minimal valid 64x64 uint16 GeoTIFF in memory."""
    import io

    data = (np.arange(64 * 64, dtype=np.uint16) % 3000 + 500).reshape(64, 64)
    buffer = io.BytesIO()
    with rasterio.open(
        buffer,
        "w",
        driver="GTiff",
        height=64,
        width=64,
        count=1,
        dtype="uint16",
        crs="EPSG:32643",
        transform=from_origin(700000, 3200000, 10, 10),
        nodata=0,
    ) as dst:
        dst.write(data, 1)

    return buffer.getvalue()


@pytest.mark.asyncio
async def test_fn_ingest_scene_successful_execution() -> None:
    """Verify fn_ingest_scene inspects raster, builds COG, and updates DB to READY."""
    await storage.ensure_buckets()

    scene_id = f"scn_ingest_{uuid4().hex[:8]}"
    raw_object_key = f"raw/{scene_id}/test_scene.tif"
    tif_bytes = _create_test_geotiff_bytes()

    # 1. Upload valid raw GeoTIFF to Bucket.RAW
    await storage.put_object(Bucket.RAW, raw_object_key, tif_bytes, content_type="image/tiff")

    # 2. Pre-create Scene record in Postgres
    async with database.get_session() as session:
        scene = Scene(
            id=scene_id,
            name="test_scene.tif",
            captured_at=datetime.now(UTC),
            ingested_at=datetime.now(UTC),
            modality=SceneModality.OPTICAL,
            sensor_platform="Sentinel-2",
            band_count=1,
            ground_sample_distance_meters=10.0,
            cloud_cover_percentage=None,
            coordinate_reference_system="EPSG:32643",
            footprint=None,
            centroid=None,
            file_size_bytes=len(tif_bytes),
            processing_state=SceneProcessingState.PROCESSING,
            temporal_role=TemporalRole.SINGLE,
            raw_object_key=raw_object_key,
            cog_object_key=None,
        )
        session.add(scene)
        await session.commit()

    # 3. Simulate Inngest execution of fn_ingest_scene
    ctx = MagicMock()
    ctx.event = inngest.Event(
        name=EventName.SCENE_INGEST_REQUESTED.value,
        data={
            "scene_id": scene_id,
            "raw_object_key": raw_object_key,
        },
    )
    ctx.attempt = 1
    step = MockStep()

    try:
        result = await fn_ingest_scene._handler(ctx, step)

        assert result["scene_id"] == scene_id
        assert result["status"] == SceneProcessingState.READY.value
        assert "cogs/" in result["cog_object_key"]

        # 4. Verify Scene record in DB is READY
        async with database.get_session() as session:
            db_scene = await session.get(Scene, scene_id)
            assert db_scene is not None
            assert db_scene.processing_state == SceneProcessingState.READY
            assert db_scene.cog_object_key == result["cog_object_key"]

        # 5. Verify COG was uploaded to Bucket.COG
        assert await storage.object_exists(Bucket.COG, result["cog_object_key"])
    finally:
        async with database.get_session() as session:
            db_scene = await session.get(Scene, scene_id)
            if db_scene:
                await session.delete(db_scene)
                await session.commit()


@pytest.mark.asyncio
async def test_fn_ingest_scene_retriable_error_raises_for_inngest_retry() -> None:
    """Verify a missing/transient storage failure re-raises so Inngest retries."""
    scene_id = f"scn_err_{uuid4().hex[:8]}"
    missing_key = f"raw/{scene_id}/non_existent.tif"

    ctx = MagicMock()
    ctx.event = inngest.Event(
        name=EventName.SCENE_INGEST_REQUESTED.value,
        data={
            "scene_id": scene_id,
            "raw_object_key": missing_key,
        },
    )
    ctx.attempt = 1
    step = MockStep()

    with pytest.raises(Exception):
        await fn_ingest_scene._handler(ctx, step)


@pytest.mark.asyncio
async def test_fn_ingest_scene_non_retriable_error_on_corrupt_raster() -> None:
    """Verify corrupt/unanalysable raster raises inngest.NonRetriableError and marks scene FAILED."""
    await storage.ensure_buckets()

    scene_id = f"scn_corrupt_{uuid4().hex[:8]}"
    raw_object_key = f"raw/{scene_id}/corrupt.tif"
    corrupt_bytes = b"NOT_A_VALID_TIFF_FILE_HEADER_CORRUPT_BYTES"

    await storage.put_object(Bucket.RAW, raw_object_key, corrupt_bytes, content_type="image/tiff")

    async with database.get_session() as session:
        scene = Scene(
            id=scene_id,
            name="corrupt.tif",
            captured_at=datetime.now(UTC),
            ingested_at=datetime.now(UTC),
            modality=SceneModality.OPTICAL,
            sensor_platform="Uploaded Scene",
            band_count=1,
            ground_sample_distance_meters=10.0,
            cloud_cover_percentage=None,
            coordinate_reference_system="EPSG:4326",
            footprint=None,
            centroid=None,
            file_size_bytes=len(corrupt_bytes),
            processing_state=SceneProcessingState.PROCESSING,
            temporal_role=TemporalRole.SINGLE,
            raw_object_key=raw_object_key,
            cog_object_key=None,
        )
        session.add(scene)
        await session.commit()

    ctx = MagicMock()
    ctx.event = inngest.Event(
        name=EventName.SCENE_INGEST_REQUESTED.value,
        data={
            "scene_id": scene_id,
            "raw_object_key": raw_object_key,
        },
    )
    ctx.attempt = 1
    step = MockStep()

    try:
        # Corrupt raster inspect/validation fails and must raise NonRetriableError
        with pytest.raises(inngest.NonRetriableError):
            await fn_ingest_scene._handler(ctx, step)

        # Verify scene is marked FAILED in Postgres
        async with database.get_session() as session:
            db_scene = await session.get(Scene, scene_id)
            assert db_scene is not None
            assert db_scene.processing_state == SceneProcessingState.FAILED
    finally:
        async with database.get_session() as session:
            db_scene = await session.get(Scene, scene_id)
            if db_scene:
                await session.delete(db_scene)
                await session.commit()


@pytest.mark.asyncio
async def test_confirm_upload_dispatches_inngest_event() -> None:
    """Verify confirm_upload dispatches EventName.SCENE_INGEST_REQUESTED when Inngest is active."""
    await storage.ensure_buckets()

    scene_id = f"scn_confirm_{uuid4().hex[:8]}"
    raw_object_key = f"raw/{scene_id}/sample.tif"
    tif_bytes = _create_test_geotiff_bytes()

    await storage.put_object(Bucket.RAW, raw_object_key, tif_bytes, content_type="image/tiff")

    with (
        patch("app.controllers.imagery_controller.is_inngest_serving_available", new=AsyncMock(return_value=True)),
        patch("app.controllers.imagery_controller.send_event", new=AsyncMock(return_value=["evt_test_123"])) as mock_send,
    ):
        response = await confirm_upload(scene_id)
        assert response.scene_id == scene_id
        assert response.processing_state == SceneProcessingState.PROCESSING

        mock_send.assert_awaited_once_with(
            EventName.SCENE_INGEST_REQUESTED,
            {
                "scene_id": scene_id,
                "raw_object_key": raw_object_key,
            },
        )
