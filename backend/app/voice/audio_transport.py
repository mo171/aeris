"""Bidirectional WebSocket audio transport adapters for AERIS voice sessions.

Fulfills Task 1 of Phase 2.4 WebSocket Voice Architecture:
- `WebSocketBlockSource` (alias `WebSocketAudioCapture`): Async iterator over PCM16 mono blocks
  fed by WebSocket binary frames for Silero VAD endpointing.
- `WebSocketAudioPlayback` (alias `WebSocketSpeechPlayer`): Streaming sink that publishes
  canonical SpeechEvent JSON frames followed by binary PCM chunks to the client over WebSocket,
  supporting instant barge-in interruption.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from starlette.websockets import WebSocketDisconnect

from app.constants.voice import VOICE_VAD_WINDOW_SAMPLES
from app.schemas.events.base import StreamEvent, serialise_event
from app.voice.speech import AuthoredSpeech
from app.voice.synthesis import AudioChunk

logger = logging.getLogger(__name__)


class WebSocketBlockSource:
    """Async iterator over PCM16 mono blocks yielded from an asyncio.Queue.

    Consumes arbitrary-sized binary frames pushed from the WebSocket reader loop
    and surfaces normalized blocks of `block_size` bytes (default: 1024 bytes = 512 samples @ 16 kHz)
    conforming to the MicrophoneCapture / Silero VAD interface.
    """

    def __init__(
        self,
        queue: asyncio.Queue[bytes | None] | None = None,
        *,
        block_size: int = VOICE_VAD_WINDOW_SAMPLES * 2,
    ) -> None:
        if block_size <= 0 or block_size % 2 != 0:
            raise ValueError("block_size must be a positive even integer for PCM16 audio")
        self.queue: asyncio.Queue[bytes | None] = queue if queue is not None else asyncio.Queue()
        self.block_size = block_size
        self._buffer = bytearray()
        self._closed = False

    def __aiter__(self) -> "WebSocketBlockSource":
        return self

    async def __anext__(self) -> bytes:
        if self._closed:
            raise StopAsyncIteration

        while len(self._buffer) < self.block_size:
            chunk = await self.queue.get()
            if chunk is None:
                # Sentinel signaling end of turn or connection closed
                self._closed = True
                if len(self._buffer) >= 2:
                    even_len = len(self._buffer) - (len(self._buffer) % 2)
                    block = bytes(self._buffer[:even_len])
                    self._buffer.clear()
                    return block
                raise StopAsyncIteration
            self._buffer.extend(chunk)

        block = bytes(self._buffer[: self.block_size])
        del self._buffer[: self.block_size]
        return block

    async def aclose(self) -> None:
        """Close the block source and flush the turn buffer."""
        self._closed = True
        self._buffer.clear()

    def reset(self) -> None:
        """Reset the source for a new turn."""
        self._closed = False
        self._buffer.clear()

    def drain(self) -> None:
        """Drain the queue and clear remaining buffer bytes."""
        self._buffer.clear()
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break


class WebSocketAudioPlayback:
    """Stream synthesized speech events and binary PCM chunks over a WebSocket.

    Complies with the VoiceSession player interface:
    - speak(utterance, chunks)
    - interrupt(utterance_id)
    - standby()
    - resume()
    - close()
    """

    def __init__(
        self,
        websocket: Any,
        *,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        self.websocket = websocket
        self._send_lock = send_lock if send_lock is not None else asyncio.Lock()
        self._active: AuthoredSpeech | None = None
        self._interrupt_requested = False
        self._standby = False
        self._closed = False
        self._interrupt_event = asyncio.Event()

    @property
    def is_active(self) -> bool:
        """True if speech is actively playing or streaming."""
        return self._active is not None

    async def send_json(self, data: dict[str, Any]) -> None:
        """Send JSON message over WebSocket safely synchronized with the send lock."""
        if self._closed:
            return
        try:
            async with self._send_lock:
                await self.websocket.send_json(data)
        except (WebSocketDisconnect, RuntimeError):
            self._closed = True
            logger.debug("WebSocket closed while sending JSON frame")

    async def send_bytes(self, data: bytes) -> None:
        """Send binary audio frame over WebSocket safely synchronized with the send lock."""
        if self._closed or not data:
            return
        try:
            async with self._send_lock:
                await self.websocket.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):
            self._closed = True
            logger.debug("WebSocket closed while sending binary audio frame")

    async def speak(
        self, utterance: AuthoredSpeech | Any, chunks: AsyncIterator[AudioChunk | bytes]
    ) -> None:
        """Stream one authored utterance: emit SpeechEvent JSON frame, then binary PCM chunks."""
        if self._standby or self._closed:
            return

        self._active = utterance
        self._interrupt_requested = False
        self._interrupt_event.clear()

        # Step 1: Send canonical SpeechEvent JSON frame
        try:
            if hasattr(utterance, "to_event"):
                event = utterance.to_event()
                payload = serialise_event(event)
            elif isinstance(utterance, StreamEvent):
                payload = serialise_event(utterance)
            elif isinstance(utterance, dict):
                payload = utterance
            else:
                payload = {"type": "speech", "text": str(utterance)}
            await self.send_json(payload)
        except Exception:
            logger.warning("Failed to serialize or send SpeechEvent JSON frame", exc_info=True)

        # Step 2: Stream binary PCM chunks with instantaneous barge-in interruption
        iterator = chunks.__aiter__()
        try:
            while not self._interrupt_requested and not self._closed:
                next_chunk_task = asyncio.create_task(anext(iterator))
                interrupt_task = asyncio.create_task(self._interrupt_event.wait())
                done, _ = await asyncio.wait(
                    (next_chunk_task, interrupt_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if interrupt_task in done:
                    # Interrupted during chunk generation
                    next_chunk_task.cancel()
                    try:
                        await next_chunk_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    break

                interrupt_task.cancel()
                try:
                    await interrupt_task
                except (asyncio.CancelledError, Exception):
                    pass

                try:
                    chunk = next_chunk_task.result()
                except StopAsyncIteration:
                    break

                if self._interrupt_requested and (
                    getattr(utterance, "interruptible", True) or self._closed
                ):
                    break

                if isinstance(chunk, bytes):
                    pcm_bytes = chunk
                else:
                    pcm_bytes = getattr(chunk, "samples", getattr(chunk, "pcm", b""))

                if pcm_bytes:
                    await self.send_bytes(pcm_bytes)
        finally:
            close_iterator = getattr(iterator, "aclose", None)
            if close_iterator is not None:
                try:
                    await close_iterator()
                except Exception:
                    pass
            self._active = None
            self._interrupt_requested = False
            self._interrupt_event.clear()

    async def interrupt(self, utterance_id: str | None = None) -> None:
        """Request immediate cancellation of the active interruptible utterance."""
        active = self._active
        if active is None:
            return
        if utterance_id is not None and getattr(active, "utterance_id", None) != utterance_id:
            return
        if not getattr(active, "interruptible", True) and not self._closed:
            return
        self._interrupt_requested = True
        self._interrupt_event.set()

    async def standby(self) -> None:
        """Suppress future speech output and interrupt current speech."""
        self._standby = True
        await self.interrupt()

    async def resume(self) -> None:
        """Restore speech playback after standby."""
        self._standby = False

    async def close(self) -> None:
        """Close playback and interrupt any active speech."""
        self._closed = True
        await self.interrupt()


# Contract aliases for cross-layer compatibility
WebSocketAudioCapture = WebSocketBlockSource
WebSocketSpeechPlayer = WebSocketAudioPlayback
