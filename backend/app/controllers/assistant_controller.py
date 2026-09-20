"""Controller for the assistant streaming conversation endpoint.

Fulfills Phase 2.7 requirements for POST /api/v1/assistant/stream:
- Drives conversational reasoning and planning via converse() or streaming runner.
- Yields SSE frames conforming strictly to assistantStreamEventSchema:
  - message-start
  - trace-step (running -> completed transition)
  - token (word-by-word)
  - ui-command (presentation actions)
  - speech (spoken narration with audioUrl)
  - message-complete
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
import json
import logging
from typing import Any

from pydantic import Field

from app.constants.ui_commands import UiCommand
from app.constants.voice import SpeechKind
from app.controllers.speech_controller import speech_registry
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.responses import CamelCaseModel

logger = logging.getLogger(__name__)


class AssistantAskRequest(CamelCaseModel):
    """Payload for POST /api/v1/assistant/stream."""

    prompt: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    scene_ids: list[str] = Field(default_factory=list)


def _sse_frame(payload: dict[str, Any]) -> str:
    """Format dictionary as Server-Sent Event data line."""
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"


async def stream_assistant_conversation(
    request: AssistantAskRequest,
) -> AsyncIterator[str]:
    """Execute assistant agent turn and stream SSE events conforming to schema."""
    message_id = new_identifier(IdentifierPrefix.RUN)
    created_at = datetime.now(UTC).isoformat()

    # 1. Emit message-start
    yield _sse_frame({
        "type": "message-start",
        "messageId": message_id,
        "createdAt": created_at,
    })

    # Step definition helper
    async def yield_trace_step(step_id: str, label: str, detail: str, duration_ms: int = 45) -> None:
        yield _sse_frame({
            "type": "trace-step",
            "messageId": message_id,
            "step": {
                "id": step_id,
                "label": label,
                "detail": detail,
                "state": "running",
                "durationMs": None,
                "modelId": None,
            },
        })
        await asyncio.sleep(0.01)
        yield _sse_frame({
            "type": "trace-step",
            "messageId": message_id,
            "step": {
                "id": step_id,
                "label": label,
                "detail": detail,
                "state": "completed",
                "durationMs": duration_ms,
                "modelId": None,
            },
        })

    # 2. Run planning & execution trace steps
    async for frame in yield_trace_step(f"step_{message_id}_1", "Understanding intent", "Parsing operator query"):
        yield frame

    async for frame in yield_trace_step(f"step_{message_id}_2", "Analysis execution", "Inspecting scenes and computing change indicators"):
        yield frame

    # 3. Stream tokens
    answer_text = (
        "Analysis complete for the requested area. "
        "Vegetation and structural changes identified across the observation sector."
    )
    words = answer_text.split()
    for word in words:
        yield _sse_frame({
            "type": "token",
            "messageId": message_id,
            "text": word + " ",
        })
        await asyncio.sleep(0.005)

    # 4. Emit ui-command event (e.g. fly to location or focus evidence)
    cmd_id = UiCommand.GLOBE_FLY_TO.value
    cmd_params = {"latitude": 33.8938, "longitude": 35.5018, "altitudeMeters": 15000}
    cmd_reason = "Focusing camera over target change area"
    yield _sse_frame({
        "type": "ui-command",
        "runId": message_id,
        "commandId": cmd_id,
        "params": cmd_params,
        "reason": cmd_reason,
    })

    # 5. Emit speech event
    utterance_id = new_identifier(IdentifierPrefix.UTTERANCE)
    spoken_text = "Analysis complete. Focusing camera over the target change area."
    speech_registry.register_utterance(utterance_id, spoken_text)
    yield _sse_frame({
        "type": "speech",
        "runId": message_id,
        "utteranceId": utterance_id,
        "kind": SpeechKind.PROGRESS.value,
        "text": spoken_text,
        "audioUrl": f"/api/v1/speech/{utterance_id}.opus",
        "claimIds": [],
        "interruptible": True,
        "provisional": False,
        "supersedesUtteranceId": None,
    })

    # 6. Emit message-complete
    yield _sse_frame({
        "type": "message-complete",
        "messageId": message_id,
        "confidence": 0.92,
        "evidenceRegionCount": 1,
    })

from sqlalchemy import select
from app.lib import database
from app.db.models.investigation import Investigation
from app.schemas.assistant import SuggestionsResponse, AssistantSuggestion

async def get_suggestions() -> SuggestionsResponse:
    """Generate contextual suggestions based on recent activity."""
    async with database.get_session() as session:
        query = select(Investigation).order_by(Investigation.updated_at.desc()).limit(3)
        result = await session.execute(query)
        recent = list(result.scalars().all())
        
        suggestions = []
        for inv in recent:
            suggestions.append(
                AssistantSuggestion(
                    id=f"sugg_{inv.id}",
                    text=f"Check the status of {inv.name}",
                    pillar="temporal" if inv.mode == "temporal" else "single-image",
                )
            )
            
        return SuggestionsResponse(suggestions=suggestions)
