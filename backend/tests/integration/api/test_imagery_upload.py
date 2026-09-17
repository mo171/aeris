"""Integration tests for imagery upload ticket and upload confirmation endpoints.

TDD Phase:
- Verifies contract compliance against frontend JSON schema (imageryUploadTicketSchema).
- Tests direct PUT upload using presigned URL with no credentials.
- Tests confirmation gating, background ingest triggering, and catalogue availability.
"""

import json
from typing import Any
from uuid import uuid4

import pytest
from aiohttp import ClientSession
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.storage import Bucket
from app.lib import storage
from app.main import app

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
IMAGERY_MODULE = "features/missionCommand/schemas/imagery.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.asyncio
async def test_create_upload_ticket_returns_valid_contract():
    """POST /api/v1/imagery/upload-ticket generates a valid signed ticket matching frontend schema."""
    payload = {
        "fileName": "sample_scene.tif",
        "fileSizeBytes": 1048576,
        "contentType": "image/tiff",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/imagery/upload-ticket", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["sceneId"].startswith("scn_")
        assert "uploadUrl" in data
        assert "expiresAt" in data
        assert data["requiredHeaders"] == {"Content-Type": "image/tiff"}
        validator_for(IMAGERY_MODULE, "imageryUploadTicketSchema").validate(data)


@pytest.mark.asyncio
async def test_create_upload_ticket_rejects_unsupported_content_type():
    """POST /api/v1/imagery/upload-ticket rejects content types not ingestible by the pipeline."""
    payload = {
        "fileName": "malicious.exe",
        "fileSizeBytes": 1024,
        "contentType": "application/x-msdownload",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/imagery/upload-ticket", json=payload)
        assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_create_upload_ticket_rejects_oversized_file():
    """POST /api/v1/imagery/upload-ticket rejects files exceeding 8 GB."""
    payload = {
        "fileName": "huge_raster.tif",
        "fileSizeBytes": 9 * 1024 * 1024 * 1024,
        "contentType": "image/tiff",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/imagery/upload-ticket", json=payload)
        assert response.status_code in (400, 422)


@pytest.mark.asyncio
async def test_confirm_upload_fails_when_file_not_uploaded():
    """POST /api/v1/imagery/{scene_id}/confirm returns 404/400 when file is missing in storage."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/imagery/scn_01nonexistent9999999999/confirm")
        assert response.status_code in (400, 404)
        payload = response.json()
        assert "code" in payload
        assert "status" in payload


@pytest.mark.asyncio
async def test_upload_flow_round_trip():
    """Complete round trip: ticket -> direct S3 PUT -> confirm -> catalogue inclusion."""
    await storage.ensure_buckets()
    test_bytes = b"II*\x00" + b"simulated_raster_payload_" + uuid4().bytes

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Request upload ticket
        ticket_res = await client.post(
            "/api/v1/imagery/upload-ticket",
            json={
                "fileName": f"test_scene_{uuid4().hex[:8]}.tif",
                "fileSizeBytes": len(test_bytes),
                "contentType": "image/tiff",
            },
        )
        assert ticket_res.status_code == 200, ticket_res.text
        ticket = ticket_res.json()
        scene_id = ticket["sceneId"]
        upload_url = ticket["uploadUrl"]
        headers = ticket["requiredHeaders"]

        # Step 2: Direct PUT to storage provider with no app credentials
        async with ClientSession() as http_session:
            async with http_session.put(upload_url, data=test_bytes, headers=headers) as put_res:
                assert put_res.status == 200, await put_res.text()

        # Step 3: Confirm upload
        confirm_res = await client.post(f"/api/v1/imagery/{scene_id}/confirm")
        assert confirm_res.status_code == 200, confirm_res.text
        confirm_data = confirm_res.json()
        assert confirm_data["sceneId"] == scene_id

        # Step 4: Verify scene is in catalogue
        cat_res = await client.get(f"/api/v1/imagery/{scene_id}")
        assert cat_res.status_code == 200
        scene_data = cat_res.json()
        assert scene_data["id"] == scene_id
