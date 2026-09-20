"""Integration tests for investigation CRUD, scene attachment, preview plan, and history/versioning.

Following TDD:
- Written to fail first before investigation routes, controllers, and services exist.
- Validates wire payloads directly against frontend vendored JSON schema contracts.
"""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.main import app

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
INVESTIGATION_MODULE = "features/investigation/schemas/investigation.schema.ts"
EVIDENCE_MODULE = "features/investigation/schemas/evidence.schema.ts"
ANALYSIS_MODULE = "features/investigation/schemas/analysis.schema.ts"
VERSION_MODULE = "features/investigation/schemas/version.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.asyncio
async def test_create_and_get_investigation_lifecycle():
    """POST /api/v1/investigations creates an investigation fast and GET returns full workspace."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Fetch an existing scene id from catalogue
        scenes_resp = await client.get("/api/v1/imagery?limit=2")
        assert scenes_resp.status_code == 200
        scene_items = scenes_resp.json()["items"]
        assert len(scene_items) > 0
        scene_id = scene_items[0]["id"]

        # 2. Create investigation
        create_req = {
            "projectId": "prj_default",
            "sceneIds": [scene_id],
            "seedQuery": "Assess vegetation vitality and recent land changes.",
            "missionId": None,
        }
        create_resp = await client.post("/api/v1/investigations", json=create_req)
        assert create_resp.status_code in (200, 201)
        created = create_resp.json()
        assert "investigationId" in created
        assert "cameraTarget" in created
        validator_for(INVESTIGATION_MODULE, "investigationCreateResponseSchema").validate(created)

        inv_id = created["investigationId"]

        # 3. Get full investigation
        get_resp = await client.get(f"/api/v1/investigations/{inv_id}")
        assert get_resp.status_code == 200
        inv = get_resp.json()
        assert inv["id"] == inv_id
        assert inv["projectId"] == "prj_default"
        assert len(inv["sceneSlots"]) >= 1
        validator_for(INVESTIGATION_MODULE, "investigationSchema").validate(inv)

        # 4. List investigations
        list_resp = await client.get("/api/v1/investigations")
        assert list_resp.status_code == 200
        inv_list = list_resp.json()
        assert "items" in inv_list
        assert any(i["id"] == inv_id for i in inv_list["items"])
        validator_for(INVESTIGATION_MODULE, "investigationListSchema").validate(inv_list)

        # 5. Patch investigation
        patch_resp = await client.patch(
            f"/api/v1/investigations/{inv_id}",
            json={"name": "Vellore Vegetation Study Updated"},
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()
        assert patched["name"] == "Vellore Vegetation Study Updated"
        validator_for(INVESTIGATION_MODULE, "investigationSchema").validate(patched)


@pytest.mark.asyncio
async def test_attach_scene_to_slot():
    """POST /api/v1/investigations/{id}/scenes binds a scene to a role slot and returns updated record."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create an investigation
        scenes_resp = await client.get("/api/v1/imagery?limit=2")
        scene_items = scenes_resp.json()["items"]
        scene_id_0 = scene_items[0]["id"]
        scene_id_1 = scene_items[1]["id"] if len(scene_items) > 1 else scene_id_0

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_id_0], "seedQuery": None},
        )
        inv_id = create_resp.json()["investigationId"]

        # Attach scene_id_1 to slot "t1"
        attach_resp = await client.post(
            f"/api/v1/investigations/{inv_id}/scenes",
            json={"sceneId": scene_id_1, "role": "t1"},
        )
        assert attach_resp.status_code == 200
        updated = attach_resp.json()
        assert any(slot["role"] == "t1" and slot["sceneId"] == scene_id_1 for slot in updated["sceneSlots"])
        validator_for(INVESTIGATION_MODULE, "investigationSchema").validate(updated)


@pytest.mark.asyncio
async def test_camera_bookmark_and_plan_and_evidence():
    """Tests camera bookmark saving, preview plan, and evidence graph endpoint."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        scene_id = scenes_resp.json()["items"][0]["id"]

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_id], "seedQuery": "test"},
        )
        inv_id = create_resp.json()["investigationId"]

        # Save camera bookmark
        bookmark = {
            "latitude": 12.92,
            "longitude": 79.13,
            "altitudeMeters": 50000.0,
            "headingDegrees": 0.0,
            "pitchDegrees": -45.0,
        }
        bm_resp = await client.post(
            f"/api/v1/investigations/{inv_id}",
            json={"cameraBookmark": bookmark},
        )
        assert bm_resp.status_code == 200

        # Verify bookmark persisted
        get_resp = await client.get(f"/api/v1/investigations/{inv_id}")
        assert get_resp.json()["cameraBookmark"] is not None
        assert get_resp.json()["cameraBookmark"]["latitude"] == 12.92

        # Get preview plan
        plan_resp = await client.get(f"/api/v1/investigations/{inv_id}/plan")
        assert plan_resp.status_code == 200
        plan = plan_resp.json()
        assert "steps" in plan
        validator_for(ANALYSIS_MODULE, "analysisPlanSchema").validate(plan)

        # Get evidence graph
        ev_resp = await client.get(f"/api/v1/investigations/{inv_id}/evidence")
        assert ev_resp.status_code == 200
        ev_graph = ev_resp.json()
        assert "claims" in ev_graph
        assert "evidence" in ev_graph
        assert "layers" in ev_graph
        validator_for(EVIDENCE_MODULE, "evidenceGraphSchema").validate(ev_graph)


@pytest.mark.asyncio
async def test_investigation_history_and_versions():
    """Tests investigation history logging and version snapshot management."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        scene_id = scenes_resp.json()["items"][0]["id"]

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_id], "seedQuery": "history test"},
        )
        inv_id = create_resp.json()["investigationId"]

        # 1. Post history
        hist_req = {
            "actor": "operator",
            "commandId": "investigation.focusEvidence",
            "params": {"evidenceId": "ev_01test"},
            "summary": "Operator inspected vegetation change anomaly.",
        }
        hist_post = await client.post(f"/api/v1/investigations/{inv_id}/history", json=hist_req)
        assert hist_post.status_code in (200, 201)

        # 2. Get history
        hist_get = await client.get(f"/api/v1/investigations/{inv_id}/history")
        assert hist_get.status_code == 200
        entries = hist_get.json()
        assert isinstance(entries, list)
        assert any(e["summary"] == "Operator inspected vegetation change anomaly." for e in entries)

        # 3. Post version snapshot
        ver_req = {
            "label": "Baseline State v1",
            "snapshot": {"zoom": 12, "activeLayers": ["lay_ndvi"]},
            "actor": "operator",
        }
        ver_post = await client.post(f"/api/v1/investigations/{inv_id}/versions", json=ver_req)
        assert ver_post.status_code in (200, 201)
        created_ver = ver_post.json()
        assert created_ver["label"] == "Baseline State v1"
        validator_for(VERSION_MODULE, "investigationVersionSchema").validate(created_ver)

        # 4. Get versions
        ver_get = await client.get(f"/api/v1/investigations/{inv_id}/versions")
        assert ver_get.status_code == 200
        vers = ver_get.json()
        assert isinstance(vers, list)
        assert len(vers) >= 1

        # 5. Post second version with threshold parameter change
        ver_req2 = {
            "label": "Threshold 0.7 State v2",
            "snapshot": {
                "steps": [{"operationId": "change-detection", "parameters": {"threshold": 0.7}}],
                "resultSummary": {"claimMetrics": [{"label": "Area", "value": 8.5}], "confidence": 0.90},
                "layerIds": ["lay_ndvi", "lay_change_07"],
            },
            "parentVersionId": created_ver["id"],
            "actor": "operator",
        }
        ver_post2 = await client.post(f"/api/v1/investigations/{inv_id}/versions", json=ver_req2)
        assert ver_post2.status_code in (200, 201)
        created_ver2 = ver_post2.json()

        # 6. Compare versions via endpoint
        comp_resp = await client.get(
            f"/api/v1/investigations/{inv_id}/versions/compare?from={created_ver['id']}&to={created_ver2['id']}"
        )
        assert comp_resp.status_code == 200
        diff = comp_resp.json()
        assert diff["versionAId"] == created_ver["id"]
        assert diff["versionBId"] == created_ver2["id"]
        assert "change-detection" in diff["parameterDiffs"]
        assert diff["parameterDiffs"]["change-detection"]["threshold"] == [None, 0.7]


@pytest.mark.asyncio
async def test_region_suggestions_endpoint():
    """Tests GET /api/v1/regions/suggestions returns contextual suggestions matching schema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        scene_id = scenes_resp.json()["items"][0]["id"]

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_id], "seedQuery": "regions test"},
        )
        inv_id = create_resp.json()["investigationId"]

        sug_resp = await client.get(
            f"/api/v1/regions/suggestions?investigationId={inv_id}&west=79.1&south=12.9&east=79.2&north=13.0"
        )
        assert sug_resp.status_code == 200
        data = sug_resp.json()
        assert "suggestions" in data
        assert len(data["suggestions"]) >= 1
        validator_for(ANALYSIS_MODULE, "regionSuggestionCollectionSchema").validate(data)


@pytest.mark.asyncio
async def test_project_investigations_filtering_and_mission_promotion():
    """Verify investigations and missions can be filtered by projectId and promoted from an investigation."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Get a scene
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        scene_id = scenes_resp.json()["items"][0]["id"]

        test_project_id = "prj_test_custom_scope"

        # 2. Create investigation with specific project_id
        create_resp = await client.post(
            "/api/v1/investigations",
            json={
                "projectId": test_project_id,
                "sceneIds": [scene_id],
                "seedQuery": "Verify project scoping",
            },
        )
        assert create_resp.status_code in (200, 201)
        inv_id = create_resp.json()["investigationId"]

        # 3. Query investigations filtered by projectId
        list_resp = await client.get(f"/api/v1/investigations?projectId={test_project_id}")
        assert list_resp.status_code == 200
        inv_items = list_resp.json()["items"]
        assert len(inv_items) >= 1
        assert any(item["id"] == inv_id for item in inv_items)

        # 4. Promote investigation to a standing mission
        promo_resp = await client.post(
            "/api/v1/missions",
            json={
                "name": "Standing Watch Over Scoped Area",
                "cadence": "daily",
                "projectId": test_project_id,
                "investigationId": inv_id,
            },
        )
        assert promo_resp.status_code in (200, 201)
        mission_data = promo_resp.json()
        assert mission_data["projectId"] == test_project_id
        assert mission_data["name"] == "Standing Watch Over Scoped Area"
        mission_id = mission_data["id"]

        # 5. Query missions filtered by projectId
        msn_list_resp = await client.get(f"/api/v1/missions?projectId={test_project_id}")
        assert msn_list_resp.status_code == 200
        msn_items = msn_list_resp.json()["items"]
        assert any(m["id"] == mission_id for m in msn_items)

