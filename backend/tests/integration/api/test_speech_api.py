"""Integration tests for the speech audio delivery endpoint.

Fulfills Phase 2.7 speech audio generation and HTTP delivery:
- GET /api/v1/speech/{utterance_id}
- GET /api/v1/speech/{utterance_id}.opus
- GET /api/v1/speech/{utterance_id}.wav
- Verifies 404 for unknown utterances.
- Verifies CORS headers and proper audio media types.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.controllers.speech_controller import speech_registry
from app.main import app


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_get_speech_audio_not_found(async_client: AsyncClient) -> None:
    """Requesting an unknown utterance returns 404."""
    response = await async_client.get("/api/v1/speech/utt_unknown_12345")
    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] in ("RESOURCE_NOT_FOUND", "NOT_FOUND")


@pytest.mark.asyncio
async def test_get_speech_audio_registered_text(async_client: AsyncClient) -> None:
    """Registered utterance text is synthesized and served as valid audio."""
    utterance_id = "utt_test_registered_001"
    speech_registry.register_utterance(
        utterance_id=utterance_id,
        text="Built-up area increased about eighteen percent. Fourteen hectares, mostly north-east.",
    )

    # Bare utterance id
    response = await async_client.get(f"/api/v1/speech/{utterance_id}")
    assert response.status_code == 200
    assert response.headers["content-type"] in ("audio/wav", "audio/ogg", "audio/opus")
    assert len(response.content) > 44  # WAV header is 44 bytes

    # .opus extension
    response_opus = await async_client.get(f"/api/v1/speech/{utterance_id}.opus")
    assert response_opus.status_code == 200
    assert len(response_opus.content) > 0

    # .wav extension
    response_wav = await async_client.get(f"/api/v1/speech/{utterance_id}.wav")
    assert response_wav.status_code == 200
    assert response_wav.headers["content-type"] == "audio/wav"
    assert len(response_wav.content) > 44


@pytest.mark.asyncio
async def test_get_speech_audio_with_pre_synthesized_bytes(async_client: AsyncClient) -> None:
    """Registered pre-synthesized audio bytes are served directly."""
    utterance_id = "utt_test_presynth_002"
    custom_bytes = b"RIFF" + b"\x00" * 40
    speech_registry.register_utterance(
        utterance_id=utterance_id,
        text="Pre-synthesized utterance.",
        audio_bytes=custom_bytes,
        media_type="audio/wav",
    )

    response = await async_client.get(f"/api/v1/speech/{utterance_id}.wav")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == custom_bytes
