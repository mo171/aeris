"""Integration tests for Inngest FastAPI webhook serving (Phase 2.5).

Verifies that:
1. `/api/inngest` is mounted and answers Inngest registration/introspection queries.
2. Both `aeris-run-investigation` and `aeris-ingest-scene` functions are registered (function_count = 2).
3. The PUT sync successfully registers with the Inngest server.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.inngest import INNGEST_FUNCTIONS
from app.main import app

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_inngest_introspection_serves_functions() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/inngest returns health & function schema introspection
        response = await client.get("/api/inngest")
        assert response.status_code == 200

        data = response.json()
        assert data.get("function_count") == 2
        assert "schema_version" in data

        # Verify function IDs in registered functions list
        fn_ids = [fn.name for fn in INNGEST_FUNCTIONS]
        assert "Run AERIS Investigation" in fn_ids or any("investigation" in id.lower() for id in fn_ids)
        assert any("scene" in id.lower() for id in fn_ids)


@pytest.mark.asyncio
async def test_inngest_sync_registers_with_server() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Inngest dev server syncs via PUT /api/inngest
        response = await client.put("/api/inngest")
        assert response.status_code == 200

        data = response.json()
        assert data.get("ok") is True
        assert "sync_id" in data
