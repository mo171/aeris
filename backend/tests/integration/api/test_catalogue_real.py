"""Integration tests for real PostGIS-backed temporal catalogue search."""

from datetime import UTC, datetime, timedelta

import pytest
from geoalchemy2.shape import from_shape
from httpx import ASGITransport, AsyncClient
from shapely.geometry import Point, box

from app.constants.geo import STORAGE_SRID
from app.constants.scenes import SceneModality, TemporalRole
from app.constants.statuses import SceneProcessingState
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.db.models.scene import Scene
from app.lib import database
from app.main import app


@pytest.mark.asyncio
async def test_catalogue_search_with_real_scenes():
    """Verify catalogue search queries real PostGIS scenes and returns honest results."""
    now = datetime.now(UTC)
    t0_date = now - timedelta(days=20)
    t1_date = now - timedelta(days=5)

    # Insert two test scenes into PostGIS
    scene_id_1 = new_identifier(IdentifierPrefix.SCENE)
    scene_id_2 = new_identifier(IdentifierPrefix.SCENE)

    mumbai_box = box(72.80, 18.90, 72.90, 19.00)
    mumbai_point = Point(72.85, 18.95)

    async with database.get_session() as session:
        s1 = Scene(
            id=scene_id_1,
            name="Mumbai Sentinel-2 Baseline",
            captured_at=t0_date,
            ingested_at=now,
            modality=SceneModality.OPTICAL,
            sensor_platform="Sentinel-2A",
            band_count=12,
            ground_sample_distance_meters=10.0,
            cloud_cover_percentage=4.5,
            coordinate_reference_system="EPSG:4326",
            footprint=from_shape(mumbai_box, srid=STORAGE_SRID),
            centroid=from_shape(mumbai_point, srid=STORAGE_SRID),
            file_size_bytes=1024 * 1024 * 100,
            processing_state=SceneProcessingState.READY,
            temporal_role=TemporalRole.T0,
            cog_object_key=f"cogs/{scene_id_1}.tif",
        )
        s2 = Scene(
            id=scene_id_2,
            name="Mumbai Sentinel-2 Comparison",
            captured_at=t1_date,
            ingested_at=now,
            modality=SceneModality.OPTICAL,
            sensor_platform="Sentinel-2B",
            band_count=12,
            ground_sample_distance_meters=10.0,
            cloud_cover_percentage=8.2,
            coordinate_reference_system="EPSG:4326",
            footprint=from_shape(mumbai_box, srid=STORAGE_SRID),
            centroid=from_shape(mumbai_point, srid=STORAGE_SRID),
            file_size_bytes=1024 * 1024 * 100,
            processing_state=SceneProcessingState.READY,
            temporal_role=TemporalRole.T1,
            cog_object_key=f"cogs/{scene_id_2}.tif",
        )
        session.add_all([s1, s2])
        await session.commit()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Search intersecting Mumbai area
            query = {
                "areaOfInterest": {
                    "west": 72.75,
                    "south": 18.85,
                    "east": 72.95,
                    "north": 19.05,
                },
                "from": (now - timedelta(days=30)).isoformat(),
                "to": now.isoformat(),
                "modalities": ["optical"],
                "maximumCloudPercentage": 20,
            }
            res = await client.post("/api/v1/catalogue/search", json=query)
            assert res.status_code == 200
            data = res.json()
            acq_scene_ids = [a["sceneId"] for a in data["acquisitions"]]
            assert scene_id_1 in acq_scene_ids
            assert scene_id_2 in acq_scene_ids
            assert data["recommendedPair"] is not None
            assert data["recommendedPair"]["t0SceneId"] == scene_id_1
            assert data["recommendedPair"]["t1SceneId"] == scene_id_2

            # 2. Search a completely disjoint region (e.g. Iceland) -> Must be empty!
            empty_query = {
                "areaOfInterest": {
                    "west": -20.0,
                    "south": 64.0,
                    "east": -18.0,
                    "north": 65.0,
                },
                "from": (now - timedelta(days=30)).isoformat(),
                "to": now.isoformat(),
                "modalities": ["optical"],
                "maximumCloudPercentage": 20,
            }
            res_empty = await client.post("/api/v1/catalogue/search", json=empty_query)
            assert res_empty.status_code == 200
            empty_data = res_empty.json()
            assert empty_data["acquisitions"] == []
            assert empty_data["recommendedPair"] is None
            assert len(empty_data["coverageGaps"]) > 0

    finally:
        # Cleanup test scenes
        async with database.get_session() as session:
            db_s1 = await session.get(Scene, scene_id_1)
            if db_s1:
                await session.delete(db_s1)
            db_s2 = await session.get(Scene, scene_id_2)
            if db_s2:
                await session.delete(db_s2)
            await session.commit()
