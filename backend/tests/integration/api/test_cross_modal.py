"""Integration tests for cross-modal analysis endpoint.

Following TDD:
- Asserts that GET /api/v1/investigations/{id}/cross-modal?baseline=...&comparison=... returns valid contract payload.
"""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.main import app

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
CROSS_MODAL_MODULE = "features/crossModal/schemas/cross-modal.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.asyncio
async def test_get_cross_modal_endpoint():
    """GET /api/v1/investigations/{id}/cross-modal returns CrossModalResult matching schema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scenes_resp = await client.get("/api/v1/imagery?limit=2")
        items = scenes_resp.json()["items"]
        scene_0 = items[0]["id"]
        scene_1 = items[1]["id"] if len(items) > 1 else scene_0

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_0], "seedQuery": "cross modal test"},
        )
        inv_id = create_resp.json()["investigationId"]

        # Request cross modal
        cm_resp = await client.get(
            f"/api/v1/investigations/{inv_id}/cross-modal?baseline={scene_0}&comparison={scene_1}"
        )
        assert cm_resp.status_code == 200
        payload = cm_resp.json()
        assert "optical" in payload
        assert "advisory" in payload
        assert "investigationId" in payload
        assert payload["investigationId"] == inv_id
        validator_for(CROSS_MODAL_MODULE, "crossModalResultSchema").validate(payload)
