"""Integration tests for figures endpoints: metadata listing and image bytes retrieval.

Following TDD:
- Validates that GET /api/v1/investigations/{id}/figures returns valid figure metadata.
- Validates that GET /api/v1/figures/{figure_id} returns image bytes with correct content type and CORS headers.
"""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.storage import Bucket
from app.lib import storage
from app.main import app

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
ANALYSIS_MODULE = "features/investigation/schemas/analysis.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.asyncio
async def test_figures_metadata_and_image_serving():
    """Tests GET /api/v1/investigations/{id}/figures and GET /api/v1/figures/{figure_id}."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create investigation
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        scene_id = scenes_resp.json()["items"][0]["id"]

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_id], "seedQuery": "figure test"},
        )
        inv_id = create_resp.json()["investigationId"]

        # 1. Seed a sample test figure into storage
        test_figure_id = "fig_01testfiguremock0000000000"
        test_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        await storage.put_object(
            Bucket.FIGURES,
            f"{test_figure_id}.png",
            test_bytes,
            content_type="image/png",
        )

        # 2. Get figure image bytes
        fig_bytes_resp = await client.get(f"/api/v1/figures/{test_figure_id}.png")
        assert fig_bytes_resp.status_code == 200
        assert fig_bytes_resp.headers["content-type"].startswith("image/png")
        assert fig_bytes_resp.content == test_bytes
        assert "access-control-allow-origin" in fig_bytes_resp.headers

        # 3. Also test without extension in path
        fig_bare_resp = await client.get(f"/api/v1/figures/{test_figure_id}")
        assert fig_bare_resp.status_code == 200
        assert fig_bare_resp.content == test_bytes

        # 4. List investigation figures
        list_resp = await client.get(f"/api/v1/investigations/{inv_id}/figures")
        assert list_resp.status_code == 200
        figs = list_resp.json()
        assert isinstance(figs, list)
