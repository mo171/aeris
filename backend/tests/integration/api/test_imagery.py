"""Integration tests for imagery listing, scene details, and catalogue search endpoints.

Following TDD:
- Tests fail first before routes/imagery.py, routes/catalogue.py, and controllers exist.
- Tests validate against the frontend vendored JSON schema contract.
"""

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.main import app

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
IMAGERY_MODULE = "features/missionCommand/schemas/imagery.schema.ts"
CATALOGUE_MODULE = "features/investigation/schemas/catalogue.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.asyncio
async def test_get_imagery_list_returns_cursor_page_matching_schema():
    """GET /api/v1/imagery returns a cursor page matching imageryCatalogPageSchema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/imagery?limit=10")
        assert response.status_code == 200
        payload = response.json()
        assert "items" in payload
        assert "nextCursor" in payload
        assert "totalCount" in payload
        validator_for(IMAGERY_MODULE, "imageryCatalogPageSchema").validate(payload)


@pytest.mark.asyncio
async def test_get_imagery_by_id_not_found_returns_404():
    """GET /api/v1/imagery/{scene_id} returns 404 ApiErrorPayload when scene does not exist."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/imagery/scn_01nonexistent9999999999")
        assert response.status_code == 404
        payload = response.json()
        assert payload["code"] == "RESOURCE_NOT_FOUND"
        assert payload["status"] == 404


@pytest.mark.asyncio
async def test_catalogue_search_returns_valid_contract():
    """POST /api/v1/catalogue/search returns a CatalogueSearchResponse matching catalogueSearchResponseSchema."""
    query = {
        "areaOfInterest": {
            "west": 72.8,
            "south": 18.9,
            "east": 73.0,
            "north": 19.1,
        },
        "from": "2026-01-01T00:00:00Z",
        "to": "2026-03-01T00:00:00Z",
        "modalities": ["optical", "sar"],
        "maximumCloudPercentage": 20,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/catalogue/search", json=query)
        assert response.status_code == 200
        payload = response.json()
        validator_for(CATALOGUE_MODULE, "catalogueSearchResponseSchema").validate(payload)
