"""Integration tests for missions, globe markers, satellite tracks, and models status.

Following TDD:
- Tests fail first before routes/missions.py, routes/globe.py, routes/models.py exist.
- Validates all responses against vendored contracts in bcontext/contracts/schemas.json.
"""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.main import app

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
MISSION_MODULE = "features/missionCommand/schemas/mission.schema.ts"
MODEL_MODULE = "features/missionCommand/schemas/model.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.asyncio
async def test_get_missions_returns_cursor_page_matching_schema():
    """GET /api/v1/missions returns cursor page validating against missionPageSchema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/missions")
        assert response.status_code == 200
        payload = response.json()
        assert "items" in payload
        assert "nextCursor" in payload
        assert "totalCount" in payload
        validator_for(MISSION_MODULE, "missionPageSchema").validate(payload)


@pytest.mark.asyncio
async def test_get_globe_markers_returns_collection_matching_schema():
    """GET /api/v1/globe/markers returns globeMarkerCollectionSchema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/globe/markers")
        assert response.status_code == 200
        payload = response.json()
        validator_for(MISSION_MODULE, "globeMarkerCollectionSchema").validate(payload)


@pytest.mark.asyncio
async def test_get_satellite_tracks_returns_collection_matching_schema():
    """GET /api/v1/globe/satellite-tracks returns satelliteTrackCollectionSchema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/globe/satellite-tracks")
        assert response.status_code == 200
        payload = response.json()
        validator_for(MISSION_MODULE, "satelliteTrackCollectionSchema").validate(payload)


@pytest.mark.asyncio
async def test_get_models_status_returns_collection_matching_schema():
    """GET /api/v1/models/status returns modelStatusCollectionSchema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/models/status")
        assert response.status_code == 200
        payload = response.json()
        validator_for(MODEL_MODULE, "modelStatusCollectionSchema").validate(payload)
