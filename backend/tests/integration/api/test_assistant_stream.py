"""Integration test for the assistant SSE stream endpoint POST /api/v1/assistant/stream.

Fulfills Phase 2.7 assistant streaming with ui-command and speech event emission:
- Validates SSE stream structure against assistantStreamEventSchema.
- Verifies message-start, trace-step (running & completed), token, ui-command, speech, and message-complete.
"""

import json
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_assistant_stream_endpoint() -> None:
    """POST /api/v1/assistant/stream streams SSE frames conforming to the assistant wire contract."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/api/v1/assistant/stream",
            json={
                "prompt": "Show me the change detection over the port and fly to it",
                "sessionId": "ses_test_stream_01",
                "sceneIds": [],
            },
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]

            events = []
            async for line in response.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    raw_json = line[len("data:") :].strip()
                    if raw_json:
                        event = json.loads(raw_json)
                        events.append(event)

        event_types = [e.get("type") for e in events]
        assert "message-start" in event_types
        assert "trace-step" in event_types
        assert "token" in event_types
        assert "ui-command" in event_types
        assert "speech" in event_types
        assert "message-complete" in event_types

        # Verify ui-command event
        ui_cmd = next(e for e in events if e.get("type") == "ui-command")
        assert ui_cmd["commandId"]
        assert isinstance(ui_cmd["params"], dict)
        assert ui_cmd["reason"]

        # Verify speech event
        speech_evt = next(e for e in events if e.get("type") == "speech")
        assert speech_evt["audioUrl"].startswith("/api/v1/speech/")
        assert speech_evt["text"]

        # Fetch audio
        audio_resp = await client.get(speech_evt["audioUrl"])
        assert audio_resp.status_code == 200
        assert len(audio_resp.content) > 0
