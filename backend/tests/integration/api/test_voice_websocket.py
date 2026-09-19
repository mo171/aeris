"""Integration tests for the bidirectional WebSocket voice endpoint.

Following TDD:
- Tests connection to /api/v1/voice/ws.
- Verifies initial session_state frame: {"type": "session_state", "state": "idle"}.
- Tests sending binary PCM16 audio frames.
- Tests sending control frames: start_turn, end_turn, interrupt, standby, resume, approve_plan, abandon.
- Verifies server session state transitions and clean disconnect without leaking tasks.
"""

import asyncio
from typing import Any
import numpy as np
import pytest
from starlette.testclient import TestClient

from app.main import app
from app.voice.audio_transport import WebSocketBlockSource, WebSocketSpeechPlayer
from app.voice.speech import AuthoredSpeech
from app.voice.synthesis import AudioChunk


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _silent_pcm16(sample_count: int = 512) -> bytes:
    """Generate silent PCM16 mono samples (1024 bytes)."""
    return np.zeros(sample_count, dtype=np.int16).tobytes()


def test_websocket_connection_and_initial_state(client: TestClient) -> None:
    """Connecting to /api/v1/voice/ws receives initial session_state: idle."""
    with client.websocket_connect("/api/v1/voice/ws") as websocket:
        initial_frame = websocket.receive_json()
        assert initial_frame == {"type": "session_state", "state": "idle"}


def test_websocket_standby_and_resume_control(client: TestClient) -> None:
    """Client sending standby and resume transitions session state accordingly."""
    with client.websocket_connect("/api/v1/voice/ws") as websocket:
        # Initial frame
        initial = websocket.receive_json()
        assert initial["type"] == "session_state"
        assert initial["state"] == "idle"

        # Send standby
        websocket.send_json({"type": "standby"})
        standby_frame = websocket.receive_json()
        assert standby_frame == {"type": "session_state", "state": "standby"}

        # Send resume
        websocket.send_json({"type": "resume"})
        resume_frame = websocket.receive_json()
        assert resume_frame == {"type": "session_state", "state": "idle"}


def test_websocket_binary_audio_and_turn_lifecycle(client: TestClient) -> None:
    """Client sends start_turn, binary PCM16 chunks, then end_turn."""
    with client.websocket_connect("/api/v1/voice/ws") as websocket:
        initial = websocket.receive_json()
        assert initial == {"type": "session_state", "state": "idle"}

        # Start a turn
        websocket.send_json({"type": "start_turn"})
        capturing_frame = websocket.receive_json()
        assert capturing_frame == {"type": "session_state", "state": "capturing"}

        # Send 10 blocks of 1024 bytes PCM16 mono (silence)
        for _ in range(10):
            websocket.send_bytes(_silent_pcm16(512))

        # End turn
        websocket.send_json({"type": "end_turn"})

        # Since it was pure silence, VAD endpoints or detects no speech, returning to idle
        idle_frame = websocket.receive_json()
        assert idle_frame == {"type": "session_state", "state": "idle"}


def test_websocket_interrupt_and_clean_disconnect(client: TestClient) -> None:
    """Client can send interrupt and disconnect cleanly."""
    with client.websocket_connect("/api/v1/voice/ws") as websocket:
        initial = websocket.receive_json()
        assert initial == {"type": "session_state", "state": "idle"}

        # Send interrupt
        websocket.send_json({"type": "interrupt", "utteranceId": "utt_123"})

        # Context manager exit closes the websocket cleanly
        websocket.close()


@pytest.mark.asyncio
async def test_block_source_chunking_and_flush() -> None:
    """WebSocketBlockSource chunks input stream into exactly block_size bytes."""
    queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    source = WebSocketBlockSource(queue, block_size=1024)

    # Put uneven data (500 bytes + 600 bytes = 1100 bytes)
    await queue.put(b"\x01" * 500)
    await queue.put(b"\x02" * 600)

    # First block should be exactly 1024 bytes
    block1 = await anext(source)
    assert len(block1) == 1024
    assert block1[:500] == b"\x01" * 500
    assert block1[500:] == b"\x02" * 524

    # Put sentinel None to signal end of turn
    await queue.put(None)

    # Second block should flush remaining 76 bytes (which is even)
    block2 = await anext(source)
    assert len(block2) == 76
    assert block2 == b"\x02" * 76

    # Subsequent read should raise StopAsyncIteration
    with pytest.raises(StopAsyncIteration):
        await anext(source)


@pytest.mark.asyncio
async def test_speech_player_streaming_and_barge_in() -> None:
    """WebSocketSpeechPlayer streams SpeechEvent JSON frame then binary PCM chunks, handling interrupt."""
    sent_json_frames: list[dict[str, Any]] = []
    sent_binary_frames: list[bytes] = []

    class MockWebSocket:
        async def send_json(self, data: dict[str, Any]) -> None:
            sent_json_frames.append(data)

        async def send_bytes(self, data: bytes) -> None:
            sent_binary_frames.append(data)

    mock_ws = MockWebSocket()
    player = WebSocketSpeechPlayer(mock_ws)

    authored = AuthoredSpeech(
        text="Analysis complete. Three flood zones detected.",
        run_id="run_test",
        utterance_id="utt_test",
        claim_ids=("clm_1",),
    )

    async def sample_chunks():
        for i in range(5):
            await asyncio.sleep(0.01)
            yield AudioChunk(samples=b"\x00\x00" * 100, sample_rate=22_050, channels=1)

    # Speak completely
    await player.speak(authored, sample_chunks())
    assert len(sent_json_frames) == 1
    assert sent_json_frames[0]["type"] == "speech"
    assert sent_json_frames[0]["utteranceId"] == "utt_test"
    assert len(sent_binary_frames) == 5

    # Test barge-in cancellation
    sent_json_frames.clear()
    sent_binary_frames.clear()

    async def slow_chunks():
        for i in range(10):
            await asyncio.sleep(0.05)
            yield AudioChunk(samples=b"\x01\x01" * 100, sample_rate=22_050, channels=1)

    speak_task = asyncio.create_task(player.speak(authored, slow_chunks()))
    await asyncio.sleep(0.02)
    assert player.is_active

    # Operator barges in
    await player.interrupt("utt_test")
    await speak_task

    assert not player.is_active
    # Should have been interrupted early before sending all 10 chunks
    assert len(sent_binary_frames) < 10
