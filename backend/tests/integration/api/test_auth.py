"""Integration tests for Phase 2.8: operator auth and session endpoints.

Validates that GET /api/v1/auth/me returns the hardcoded user from default_user.json
and GET /api/v1/auth/session returns an authenticated operator session.
"""

import json
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_get_auth_me_returns_default_user():
    """GET /api/v1/auth/me returns 200 with the operator profile."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == "usr_01aeris_operator_default"
        assert payload["username"] == "operator"
        assert payload["email"] == "operator@aeris.internal"
        assert payload["name"] == "AERIS Lead Analyst"
        assert payload["role"] == "lead_analyst"
        assert payload["organization"] == "National Remote Sensing Agency"
        assert "investigations:create" in payload["permissions"]
        assert "avatarUrl" in payload


@pytest.mark.asyncio
async def test_get_auth_session_returns_active_session():
    """GET /api/v1/auth/session returns 200 with active session and embedded user."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/session")
        assert response.status_code == 200
        payload = response.json()
        assert payload["isAuthenticated"] is True
        assert "sessionId" in payload
        assert payload["user"]["id"] == "usr_01aeris_operator_default"
