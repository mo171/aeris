"""Integration tests for FastAPI shell, health endpoints, and global exception handling.

Following TDD:
- Tests fail first before main.py, controllers, and routes exist.
- Tests assert exact HTTP status, wire structure (ApiErrorPayload on error, clean JSON on health).
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.lib.exceptions import ResourceNotFoundError


@pytest.mark.asyncio
async def test_health_endpoint_returns_200_and_dependency_status():
    """GET /health must return 200 with service status and dependencies."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "dependencies" in data
        assert isinstance(data["dependencies"], list)


@pytest.mark.asyncio
async def test_ready_endpoint_returns_200():
    """GET /ready must return 200 indicating server readiness."""
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ready"


@pytest.mark.asyncio
async def test_aeris_error_exception_handler_returns_api_error_payload():
    """AerisError subclasses must be rendered as ApiErrorPayload matching the frontend contract."""
    from fastapi import APIRouter
    from app.main import app

    test_router = APIRouter()

    @test_router.get("/test-error-endpoint")
    async def trigger_error():
        raise ResourceNotFoundError("Scene 's2_nonexistent' does not exist.", details={"sceneId": "s2_nonexistent"})

    app.include_router(test_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test-error-endpoint")
        assert response.status_code == 404
        payload = response.json()
        assert payload["message"] == "Scene 's2_nonexistent' does not exist."
        assert payload["code"] == "RESOURCE_NOT_FOUND"
        assert payload["status"] == 404
        assert payload["details"] == {"sceneId": "s2_nonexistent"}
