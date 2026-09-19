"""Integration tests for tiles_controller and TiTiler proxy operations (Phase 2.6)."""

import io
import math
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
import rasterio
from rasterio.transform import from_origin

from app.constants.presets import BandPreset
from app.constants.scenes import SceneModality, TemporalRole
from app.constants.statuses import SceneProcessingState
from app.constants.storage import Bucket
from app.controllers import tiles_controller
from app.db.models.scene import Scene
from app.lib import database, storage
from app.lib.exceptions import ResourceNotFoundError

pytestmark = pytest.mark.integration


def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    """Convert WGS84 lat/lon to Slippy map tile X/Y."""
    lat_rad = math.radians(lat_deg)
    n = 1 << zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def _create_geotiff_bytes() -> bytes:
    """Generate a minimal valid 64x64 uint16 GeoTIFF in memory."""
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


@pytest_asyncio.fixture(loop_scope="session")
async def sample_scene():
    """Provision a real test scene with a GeoTIFF in MinIO."""
    await storage.ensure_buckets()
    scene_id = f"scn_tiletest_{uuid4().hex[:8]}"
    cog_key = f"cogs/{scene_id}.tif"
    tif_bytes = _create_geotiff_bytes()

    await storage.put_object(Bucket.COG, cog_key, tif_bytes, content_type="image/tiff")

    from geoalchemy2.shape import from_shape
    from shapely.geometry import Point, box
    from app.constants.geo import STORAGE_SRID

    geom_box = box(77.051, 28.906, 77.058, 28.912)
    geom_point = Point(77.054, 28.909)

    async with database.get_session() as session:
        scene = Scene(
            id=scene_id,
            name=f"{scene_id}.tif",
            captured_at=datetime.now(UTC),
            ingested_at=datetime.now(UTC),
            modality=SceneModality.OPTICAL,
            sensor_platform="Sentinel-2",
            band_count=1,
            ground_sample_distance_meters=10.0,
            cloud_cover_percentage=0.0,
            coordinate_reference_system="EPSG:32643",
            footprint=from_shape(geom_box, srid=STORAGE_SRID),
            centroid=from_shape(geom_point, srid=STORAGE_SRID),
            file_size_bytes=len(tif_bytes),
            processing_state=SceneProcessingState.READY,
            temporal_role=TemporalRole.SINGLE,
            raw_object_key=None,
            cog_object_key=cog_key,
        )
        session.add(scene)
        await session.commit()

    yield scene_id

    # Cleanup
    try:
        await storage.delete_object(Bucket.COG, cog_key)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_get_scene_tilejson_for_existing_scene(sample_scene: str):
    """Verify get_scene_tilejson retrieves TileJSON and rewrites tiles array to /api/v1/tiles/..."""
    scene_id = sample_scene
    tilejson = await tiles_controller.get_scene_tilejson(scene_id)

    assert "tilejson" in tilejson
    assert "tiles" in tilejson
    assert len(tilejson["tiles"]) > 0
    assert f"/api/v1/tiles/{scene_id}/{{z}}/{{x}}/{{y}}.png" in tilejson["tiles"][0]
    assert "bounds" in tilejson
    assert "minzoom" in tilejson and "maxzoom" in tilejson


@pytest.mark.asyncio
async def test_get_scene_tilejson_with_preset(sample_scene: str):
    """Verify preset query parameter is included in the rewritten tile template."""
    scene_id = sample_scene
    tilejson = await tiles_controller.get_scene_tilejson(scene_id, preset="grayscale")

    assert "tiles" in tilejson
    assert f"/api/v1/tiles/{scene_id}/{{z}}/{{x}}/{{y}}.png?preset=grayscale" in tilejson["tiles"][0]


@pytest.mark.asyncio
async def test_get_scene_tilejson_missing_scene():
    """Verify non-existent scene raises ResourceNotFoundError."""
    with pytest.raises(ResourceNotFoundError):
        await tiles_controller.get_scene_tilejson("scn_non_existent_id")


@pytest.mark.asyncio
async def test_render_scene_tile_png_with_alpha(sample_scene: str):
    """Verify render_scene_tile returns valid PNG bytes with alpha transparency."""
    scene_id = sample_scene
    tilejson = await tiles_controller.get_scene_tilejson(scene_id)
    minzoom = tilejson["minzoom"]

    west, south, east, north = tilejson["bounds"]
    center_lon = (west + east) / 2.0
    center_lat = (south + north) / 2.0

    x, y = deg2num(center_lat, center_lon, minzoom)

    tile_bytes, media_type = await tiles_controller.render_scene_tile(scene_id, minzoom, x, y)
    assert media_type == "image/png"
    assert len(tile_bytes) > 0
    # Magic bytes for PNG: \x89PNG\r\n\x1a\n
    assert tile_bytes.startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_render_scene_tile_missing_coord(sample_scene: str):
    """Verify requesting an out-of-bounds tile raises ResourceNotFoundError."""
    scene_id = sample_scene
    with pytest.raises(ResourceNotFoundError):
        await tiles_controller.render_scene_tile(scene_id, 0, 999, 999)


@pytest.mark.asyncio
async def test_get_scene_preview(sample_scene: str):
    """Verify get_scene_preview returns valid PNG image bytes."""
    scene_id = sample_scene
    img_bytes, media_type = await tiles_controller.get_scene_preview(scene_id, max_size=256)
    assert media_type == "image/png"
    assert len(img_bytes) > 0
    assert img_bytes.startswith(b"\x89PNG")

