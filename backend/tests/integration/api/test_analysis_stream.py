"""Integration test verifying live emission of ui-command and speech events on the analysis stream.

Fulfills Phase 2.7 live emission requirements on /api/v1/investigations/{id}/runs:
- Verifies ui-command event presence in SSE stream.
- Verifies speech event presence in SSE stream with valid audioUrl.
- Verifies that audioUrl points to /api/v1/speech/{utterance_id}.opus and is immediately fetchable.
"""

import json
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_investigation_run_emits_ui_command_and_speech() -> None:
    """POST /api/v1/investigations/{id}/runs streams ui-command and speech events."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create an investigation
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        assert scenes_resp.status_code == 200
        scene_id = scenes_resp.json()["items"][0]["id"]

        create_resp = await client.post(
            "/api/v1/investigations",
            json={"projectId": "prj_default", "sceneIds": [scene_id], "seedQuery": "Stream emission test"},
        )
        assert create_resp.status_code in (200, 201)
        inv_id = create_resp.json()["investigationId"]

        # 2. Trigger analysis run with streaming
        async with client.stream(
            "POST",
            f"/api/v1/investigations/{inv_id}/runs",
            json={"investigationId": inv_id, "query": "Check infrastructure and highlight findings"},
        ) as response:
            assert response.status_code == 200
            events = []
            async for line in response.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    raw_json = line[len("data:") :].strip()
                    if raw_json:
                        event = json.loads(raw_json)
                        events.append(event)

        event_types = [e.get("type") for e in events]
        assert "run-start" in event_types
        assert "run-complete" in event_types
        assert "ui-command" in event_types
        assert "speech" in event_types

        # Verify ui-command structure
        ui_cmd = next(e for e in events if e.get("type") == "ui-command")
        assert ui_cmd["commandId"] in ("globe.flyTo", "investigation.focusEvidence", "investigation.spotlightClaim")
        assert isinstance(ui_cmd["params"], dict)
        assert ui_cmd["reason"]

        # Verify speech structure and audioUrl accessibility
        speech_evt = next(e for e in events if e.get("type") == "speech")
        assert speech_evt["audioUrl"].startswith("/api/v1/speech/")
        assert speech_evt["text"]

        # 3. Test that the audioUrl emitted in the speech event can be fetched immediately
        audio_resp = await client.get(speech_evt["audioUrl"])
        assert audio_resp.status_code == 200
        assert len(audio_resp.content) > 0
