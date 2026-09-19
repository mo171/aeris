"""Declaration of assistant routes.

Follows bcontext/folder-archtecture.md:
Declaration only. No business logic, routed to controllers/assistant_controller.py.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.controllers import assistant_controller
from app.controllers.assistant_controller import AssistantAskRequest

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/stream")
async def stream_assistant(
    request: AssistantAskRequest,
) -> StreamingResponse:
    """Stream assistant conversation trace, tokens, ui-command and speech via Server-Sent Events (SSE)."""
    generator = assistant_controller.stream_assistant_conversation(request)
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
