"""Integration tests for real database-backed mission listing and retrieval."""

from datetime import UTC, datetime

import pytest
from geoalchemy2.shape import from_shape
from httpx import ASGITransport, AsyncClient
from shapely.geometry import Point, box

from app.constants.geo import STORAGE_SRID
from app.constants.statuses import MissionStatus
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.db.models.mission import Mission as DbMission
from app.lib import database
from app.main import app


@pytest.mark.asyncio
async def test_missions_real_crud_and_not_found():
    """Verify missions endpoints query real DB rows and return 404 for unknown IDs without mock fallbacks."""
    mission_id = new_identifier(IdentifierPrefix.MISSION)
    now = datetime.now(UTC)

    test_box = box(72.8, 18.9, 73.0, 19.1)
    test_pt = Point(72.9, 19.0)

    # Insert test mission into database
    async with database.get_session() as session:
        m = DbMission(
            id=mission_id,
            name="Real Operational Coastal Survey",
            status=MissionStatus.ACTIVE,
            status_rank=2,
            area_of_interest=from_shape(test_box, srid=STORAGE_SRID),
            centroid=from_shape(test_pt, srid=STORAGE_SRID),
            last_run_at=now,
            project_id="prj_default",
        )
        session.add(m)
        await session.commit()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. List missions - must contain the created mission
            list_res = await client.get("/api/v1/missions")
            assert list_res.status_code == 200
            data = list_res.json()
            assert any(item["id"] == mission_id for item in data["items"])

            # 2. Get by ID - must return the real mission
            get_res = await client.get(f"/api/v1/missions/{mission_id}")
            assert get_res.status_code == 200
            item = get_res.json()
            assert item["id"] == mission_id
            assert item["name"] == "Real Operational Coastal Survey"
            assert item["status"] == "active"
            assert item["centroid"]["latitude"] == 19.0
            assert item["centroid"]["longitude"] == 72.9

            # 3. Get nonexistent mission -> must return 404 RESOURCE_NOT_FOUND (not a sample mission!)
            bad_res = await client.get("/api/v1/missions/msn_nonexistent999999")
            assert bad_res.status_code == 404
            assert bad_res.json()["code"] == "RESOURCE_NOT_FOUND"

            # 4. Specifically verify the old sample mission id returns 404 if not in DB
            sample_res = await client.get("/api/v1/missions/msn_01sentinel_monitoring")
            assert sample_res.status_code == 404
            assert sample_res.json()["code"] == "RESOURCE_NOT_FOUND"

    finally:
        async with database.get_session() as session:
            db_m = await session.get(DbMission, mission_id)
            if db_m:
                await session.delete(db_m)
            await session.commit()
