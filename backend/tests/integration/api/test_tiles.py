"""Integration tests for FastAPI tiles routes (Phase 2.6).

what  : HTTP route tests for `/api/v1/tiles/{scene_id}/tilejson.json`,
        `/api/v1/tiles/{scene_id}/{z}/{x}/{y}.png`, and `/api/v1/tiles/{scene_id}/preview`.
where : Tests `app/routes/tiles.py` end-to-end through FastAPI `app`.
how   : Conforms to `api-contract.md` §8:
        - Tiles are in WebMercatorQuad PNG format with alpha channel.
        - Internal S3 URIs are never leaked in responses.
        - TileJSON bounds and zoom levels guide the map client.
"""

import io
import math
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import pytest
import pytest_asyncio
import rasterio
from geoalchemy2.shape import from_shape
from httpx import ASGITransport, AsyncClient
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from app.constants.geo import STORAGE_SRID
from app.constants.presets import BandPreset
from app.constants.scenes import SceneModality, TemporalRole
from app.constants.statuses import SceneProcessingState
from app.constants.storage import Bucket
from app.db.models.scene import Scene
from app.lib import database, storage
from app.main import app

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
    """Provision a real test scene with a GeoTIFF in MinIO and record in PostGIS."""
    await storage.ensure_buckets()
    scene_id = f"scn_tileapi_{uuid4().hex[:8]}"
    cog_key = f"cogs/{scene_id}.tif"
    tif_bytes = _create_geotiff_bytes()

    await storage.put_object(Bucket.COG, cog_key, tif_bytes, content_type="image/tiff")

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
async def test_route_get_scene_tilejson(sample_scene: str):
    """GET /api/v1/tiles/{scene_id}/tilejson.json returns valid TileJSON with rewritten URLs."""
    scene_id = sample_scene
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/tiles/{scene_id}/tilejson.json")
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["tilejson"] == "2.2.0"
        assert len(data["tiles"]) > 0
        tile_template = data["tiles"][0]
        assert f"/api/v1/tiles/{scene_id}/{{z}}/{{x}}/{{y}}.png" in tile_template
        # Security invariant: internal s3:// bucket URIs must NEVER be leaked in TileJSON
        assert "s3://" not in tile_template
        assert "bounds" in data
        assert "minzoom" in data and "maxzoom" in data


@pytest.mark.asyncio
async def test_route_get_scene_tilejson_with_preset(sample_scene: str):
    """GET /api/v1/tiles/{scene_id}/tilejson.json?preset=ndvi propagates preset in tile template."""
    scene_id = sample_scene
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/tiles/{scene_id}/tilejson.json?preset=ndvi")
        assert res.status_code == 200, res.text
        data = res.json()
        tile_template = data["tiles"][0]
        assert "preset=ndvi" in tile_template


@pytest.mark.asyncio
async def test_route_get_scene_tile_png(sample_scene: str):
    """GET /api/v1/tiles/{scene_id}/{z}/{x}/{y}.png returns PNG tile bytes with alpha channel."""
    scene_id = sample_scene
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tilejson_res = await client.get(f"/api/v1/tiles/{scene_id}/tilejson.json")
        assert tilejson_res.status_code == 200
        tilejson = tilejson_res.json()

        minzoom = tilejson["minzoom"]
        west, south, east, north = tilejson["bounds"]
        center_lon = (west + east) / 2.0
        center_lat = (south + north) / 2.0
        x, y = deg2num(center_lat, center_lon, minzoom)

        res = await client.get(f"/api/v1/tiles/{scene_id}/{minzoom}/{x}/{y}.png")
        assert res.status_code == 200, res.text
        assert "image/png" in res.headers.get("content-type", "")
        assert "public, max-age=" in res.headers.get("cache-control", "")
        # PNG magic signature
        assert res.content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_route_get_scene_preview(sample_scene: str):
    """GET /api/v1/tiles/{scene_id}/preview returns fast raster preview."""
    scene_id = sample_scene
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(f"/api/v1/tiles/{scene_id}/preview?max_size=256")
        assert res.status_code == 200, res.text
        assert "image/png" in res.headers.get("content-type", "")
        assert len(res.content) > 0
        assert res.content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_route_scene_not_found():
    """Non-existent scene ID returns 404 with structured error envelope."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/tiles/scn_000nonexistent999/tilejson.json")
        assert res.status_code == 404
        error_json = res.json()
        assert "code" in error_json or "error" in error_json or "status" in error_json

        res_tile = await client.get("/api/v1/tiles/scn_000nonexistent999/0/0/0.png")
        assert res_tile.status_code == 404


@pytest.mark.asyncio
async def test_route_get_scene_aliases(sample_scene: str):
    """Verify /scenes/{scene_id}/ alias routes work identically."""
    scene_id = sample_scene
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_json = await client.get(f"/api/v1/tiles/scenes/{scene_id}/tilejson.json")
        assert res_json.status_code == 200

        res_preview = await client.get(f"/api/v1/tiles/scenes/{scene_id}/preview")
        assert res_preview.status_code == 200
        assert res_preview.content.startswith(b"\x89PNG\r\n\x1a\n")

        res_quicklook = await client.get(f"/api/v1/tiles/scenes/{scene_id}/quicklook.webp")
        assert res_quicklook.status_code == 200

