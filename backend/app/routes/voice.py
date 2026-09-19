"""FastAPI WebSocket endpoint for bidirectional real-time voice streaming.

Handles real-time audio transport (<30ms frames) for Silero VAD and Whisper ASR,
and streams Piper/Kokoro TTS binary PCM chunks and JSON control/event messages
back to the browser client over a single multiplexed WebSocket connection at /api/v1/voice/ws.
"""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.constants.voice import VOICE_VAD_WINDOW_SAMPLES, VoiceSessionState
from app.schemas.events.base import StreamEvent, serialise_event
from app.voice.audio import MicrophoneCapture
from app.voice.audio_transport import WebSocketBlockSource, WebSocketSpeechPlayer
from app.voice.session import VoiceSession
from app.voice.synthesis import PiperSynthesizer
from app.voice.transcription import WhisperTranscriber
from app.voice.types import Transcript

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


def create_voice_session(
    websocket: WebSocket,
    audio_queue: asyncio.Queue[bytes | None],
    *,
    send_lock: asyncio.Lock | None = None,
    capture: Any = None,
    transcriber: Any = None,
    synthesizer: Any = None,
    player: Any = None,
    model: Any = None,
    on_state_change: Callable[[VoiceSessionState], Any] | None = None,
    on_transcript: Callable[[Transcript], Any] | None = None,
) -> tuple[VoiceSession, WebSocketBlockSource, WebSocketSpeechPlayer]:
    """Factory creating VoiceSession and attached WebSocket audio adapters."""
    lock = send_lock if send_lock is not None else asyncio.Lock()
    block_source = WebSocketBlockSource(
        queue=audio_queue,
        block_size=VOICE_VAD_WINDOW_SAMPLES * 2,
    )
    cap = capture or MicrophoneCapture(
        block_source=lambda: WebSocketBlockSource(
            audio_queue, block_size=VOICE_VAD_WINDOW_SAMPLES * 2
        ),
    )
    trans = transcriber or WhisperTranscriber()
    synth = synthesizer or PiperSynthesizer()
    ply = player or WebSocketSpeechPlayer(websocket=websocket, send_lock=lock)

    if model is None:
        try:
            from app.lib.llm.chat_model import build_chat_model

            model = build_chat_model()
        except Exception:
            logger.debug("LLM model build skipped or deferred", exc_info=True)

    session = VoiceSession(
        capture=cap,
        transcriber=trans,
        synthesizer=synth,
        player=ply,
        model=model,
        on_state_change=on_state_change,
        on_transcript=on_transcript,
    )
    return session, block_source, ply


# Factory hook for dependency overrides during testing
_SESSION_FACTORY: Callable[..., tuple[VoiceSession, WebSocketBlockSource, WebSocketSpeechPlayer]] = create_voice_session


def set_voice_session_factory(
    factory: Callable[..., tuple[VoiceSession, WebSocketBlockSource, WebSocketSpeechPlayer]],
) -> None:
    """Override session factory for testing."""
    global _SESSION_FACTORY
    _SESSION_FACTORY = factory


def reset_voice_session_factory() -> None:
    """Reset session factory to default implementation."""
    global _SESSION_FACTORY
    _SESSION_FACTORY = create_voice_session


@router.websocket("/ws")
async def voice_websocket(websocket: WebSocket) -> None:
    """Bidirectional WebSocket voice endpoint.

    Multiplexes:
    - Inbound: binary PCM16 audio chunks and JSON control commands
      (start_turn, end_turn, interrupt, standby, resume, approve_plan, abandon).
    - Outbound: initial session_state, state transitions, transcript frames,
      SpeechEvent frames, and binary PCM chunks.
    """
    await websocket.accept()

    send_lock = asyncio.Lock()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    hotkey_event = asyncio.Event()

    async def send_json(data: dict[str, Any]) -> None:
        try:
            async with send_lock:
                await websocket.send_json(data)
        except (WebSocketDisconnect, RuntimeError):
            logger.debug("WebSocket client disconnected during send_json")

    async def handle_state_change(state: VoiceSessionState) -> None:
        await send_json({
            "type": "session_state",
            "state": state.value,
        })

    async def handle_transcript(transcript: Transcript) -> None:
        await send_json({
            "type": "transcript",
            "text": transcript.text,
            "language": transcript.language,
            "isFinal": True,
        })

    session, block_source, player = _SESSION_FACTORY(
        websocket,
        audio_queue,
        send_lock=send_lock,
        on_state_change=handle_state_change,
        on_transcript=handle_transcript,
    )

    # Initial announcement to client
    await send_json({"type": "session_state", "state": "idle"})

    async def reader_loop() -> None:
        """Continuously read frames from the WebSocket and dispatch them."""
        while True:
            try:
                message = await websocket.receive()
            except (WebSocketDisconnect, RuntimeError):
                break

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                binary_frame: bytes = message["bytes"]
                if binary_frame:
                    await audio_queue.put(binary_frame)

            elif "text" in message and message["text"] is not None:
                text_content: str = message["text"].strip()
                if not text_content:
                    continue
                try:
                    data = json.loads(text_content)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received over voice WebSocket: %r", text_content)
                    continue

                if not isinstance(data, dict):
                    continue

                msg_type = data.get("type")
                if msg_type == "start_turn":
                    # Clear any unconsumed audio from previous turns
                    while not audio_queue.empty():
                        try:
                            audio_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    hotkey_event.set()

                elif msg_type == "end_turn":
                    session._stop_capture.set()
                    await audio_queue.put(None)

                elif msg_type == "interrupt":
                    utterance_id = data.get("utteranceId") or data.get("utterance_id")
                    await player.interrupt(utterance_id)

                elif msg_type == "standby":
                    await session._handle_standby()

                elif msg_type == "resume":
                    await session._handle_resume()

                elif msg_type == "approve_plan":
                    approved_step_ids = data.get("approvedStepIds") or data.get("approved_step_ids")
                    await session._handle_approve(enabled_step_ids=approved_step_ids)

                elif msg_type == "abandon":
                    await session._handle_abandon()

                else:
                    logger.debug("Unhandled voice WebSocket control message: %s", msg_type)

    session_task = asyncio.create_task(session.run(hotkey_source=hotkey_event))
    reader_task = asyncio.create_task(reader_loop())

    try:
        await asyncio.wait(
            [reader_task, session_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        # Tear down session and transport without leaking asyncio tasks
        await session.close()
        await player.close()
        await block_source.aclose()

        for task in (reader_task, session_task):
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

        try:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close()
        except Exception:
            pass
