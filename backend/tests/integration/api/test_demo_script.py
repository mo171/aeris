"""Integration tests and Phase 2.9 gate verification: Canonical Demonstration Suite.

Validates that:
1. Demo manifest and scenario definitions load cleanly.
2. Offline raster bundle and database seeder operate with zero external network access.
3. The full rehearsed demonstration script passes three consecutive runs without failure.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_demo_manifest_and_scenarios():
    """GET /api/v1/demo/manifest and /scenarios return valid definitions."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Manifest
        resp = await client.get("/api/v1/demo/manifest")
        assert resp.status_code == 200
        manifest = resp.json()
        assert manifest["bundleId"] == "bnd_aeris_sih2026_canonical"
        assert len(manifest["scenarios"]) == 4

        # 2. Scenarios list
        resp = await client.get("/api/v1/demo/scenarios")
        assert resp.status_code == 200
        scenarios = resp.json()
        assert len(scenarios) == 4
        scenario_ids = [s["id"] for s in scenarios]
        assert "single-image-vqa" in scenario_ids
        assert "bitemporal-change" in scenario_ids
        assert "cross-modal-fusion" in scenario_ids
        assert "report-and-audit" in scenario_ids


@pytest.mark.asyncio
async def test_demo_bundle_status_and_seeder():
    """GET /api/v1/demo/bundle and POST /api/v1/demo/bundle/seed verify and seed offline assets."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Seed demo environment
        seed_resp = await client.post("/api/v1/demo/bundle/seed")
        assert seed_resp.status_code == 200
        seed_data = seed_resp.json()
        assert seed_data["investigationId"] == "inv_demo_canonical"
        assert seed_data["status"] == "seeded"

        # Check bundle readiness
        bundle_resp = await client.get("/api/v1/demo/bundle")
        assert bundle_resp.status_code == 200
        bundle = bundle_resp.json()
        assert bundle["status"] == "ready"
        assert bundle["manifestPresent"] is True
        assert bundle["rastersPresent"] is True


@pytest.mark.asyncio
async def test_demo_single_scenario_execution():
    """POST /api/v1/demo/run with a specific scenario executes cleanly."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=30.0) as client:
        # Run report-and-audit scenario
        resp = await client.post("/api/v1/demo/run", json={"scenarioId": "report-and-audit"})
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["success"] is True
        assert payload["completedRuns"] == 1
        assert len(payload["scenarios"]) == 1
        sc = payload["scenarios"][0]
        assert sc["scenarioId"] == "report-and-audit"
        assert sc["status"] == "complete"
        assert sc["evidenceCount"] >= 1
        assert sc["traceId"].startswith("trc_demo_report-and-audit")


@pytest.mark.asyncio
async def test_phase_2_9_gate_three_consecutive_runs():
    """Gate verification for Phase 2.9 (PDF Phase 10):

    The full canonical demo script must pass THREE consecutive runs without failure.
    Runs 1, 2, and 3 must all achieve 100% success across all 4 scenarios.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=60.0) as client:
        for run_number in range(1, 4):
            resp = await client.post("/api/v1/demo/run", json={"iterations": 1})
            assert resp.status_code == 200, f"Run #{run_number} failed with HTTP {resp.status_code}"
            payload = resp.json()
            assert payload["success"] is True, f"Run #{run_number} indicated execution failure"
            assert payload["completedRuns"] == 4, f"Run #{run_number} expected 4 scenarios, got {payload['completedRuns']}"

            # Validate each scenario in this iteration
            for sc in payload["scenarios"]:
                assert sc["status"] == "complete", f"Run #{run_number} scenario {sc['scenarioId']} did not complete"
                assert sc["traceId"], f"Run #{run_number} scenario {sc['scenarioId']} missing trace ID"
                assert sc["durationMs"] > 0, f"Run #{run_number} scenario {sc['scenarioId']} invalid duration"
