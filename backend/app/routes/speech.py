"""HTTP endpoints for serving spoken audio utterances.

Endpoints:
- GET /api/v1/speech/{utterance_id}
- GET /api/v1/speech/{utterance_id}.opus
- GET /api/v1/speech/{utterance_id}.wav
"""

from fastapi import APIRouter, Response

from app.controllers.speech_controller import speech_registry

router = APIRouter(prefix="/speech", tags=["speech"])


@router.get("/{utterance_id}")
async def get_speech_audio(utterance_id: str) -> Response:
    """Stream or deliver synthesized audio for an authored utterance."""
    audio_bytes, media_type = speech_registry.get_utterance_audio(utterance_id)
    return Response(
        content=audio_bytes,
        media_type=media_type,
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            "Accept-Ranges": "bytes",
        },
    )
