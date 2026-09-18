"""Integration tests for streamed runs endpoint (SSE).

Following TDD:
- Asserts that POST /api/v1/investigations/{id}/runs opens text/event-stream.
- Asserts that SSE event frames parse correctly and validate against analysisStreamEventSchema.
"""

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from jsonschema import Draft202012Validator

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.main import app

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
ANALYSIS_MODULE = "features/investigation/schemas/analysis.schema.ts"


def validator_for(module_key: str, schema_name: str) -> Draft202012Validator:
    return Draft202012Validator(
        CONTRACTS[module_key][schema_name],
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


@pytest.mark.asyncio
async def test_investigation_runs_stream():
    """POST /api/v1/investigations/{id}/runs streams events via SSE matching analysisStreamEventSchema."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create investigation
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        scene_id = scenes_resp.json()["items"][0]["id"]

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_id], "seedQuery": "runs stream test"},
        )
        inv_id = create_resp.json()["investigationId"]

        run_request = {
            "investigationId": inv_id,
            "query": "Is there vegetation change or flood evidence in this region?",
            "regionBounds": None,
            "planId": None,
            "operationId": None,
        }

        events_received = []
        async with client.stream(
            "POST",
            f"/api/v1/investigations/{inv_id}/runs",
            json=run_request,
            headers={"Accept": "text/event-stream"},
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n\n" in buffer:
                    frame, buffer = buffer.split("\n\n", 1)
                    lines = frame.strip().split("\n")
                    for line in lines:
                        if line.startswith("data:"):
                            payload_str = line[len("data:"):].strip()
                            if payload_str:
                                event = json.loads(payload_str)
                                events_received.append(event)
                                # Validate every frame against analysisStreamEventSchema!
                                validator_for(ANALYSIS_MODULE, "analysisStreamEventSchema").validate(event)

        assert len(events_received) >= 2
        types = [e["type"] for e in events_received]
        assert "run-start" in types
        assert "run-complete" in types or "run-error" in types
