"""One-shot asynchronous microphone capture with Silero model endpointing.

`MicrophoneCapture` never opens a device until `capture()` is called, and each call consumes one bounded
turn. The injected block source and VAD factory are the test seam; production uses sounddevice and Silero.
All device operations and model calls are kept off the event-loop thread.
"""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

import numpy as np

from app.constants.voice import VOICE_INPUT_SAMPLE_RATE_HERTZ
from app.voice.types import CapturedTurn

PcmBlock = bytes | bytearray | memoryview | np.ndarray
BlockSource = AsyncIterator[PcmBlock]
BlockSourceFactory = Callable[[], BlockSource]
VadFactory = Callable[[], Any]


class SoundDeviceBlockSource:
    """Async iterator over mono PCM16 blocks from one sounddevice raw input stream."""

    def __init__(
        self,
        *,
        sample_rate: int = VOICE_INPUT_SAMPLE_RATE_HERTZ,
        block_size: int = 512,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device = device
        self._stream: Any = None

    def __aiter__(self) -> SoundDeviceBlockSource:
        return self

    async def __anext__(self) -> bytes:
        if self._stream is None:
            await self._open()
        try:
            data, _overflowed = await asyncio.to_thread(self._stream.read, self.block_size)
        except (StopAsyncIteration, EOFError) as error:
            await self.aclose()
            raise StopAsyncIteration from error
        return bytes(data)

    async def _open(self) -> None:
        """Construct and start the blocking PortAudio stream outside asyncio's event loop."""
        import sounddevice

        self._stream = await asyncio.to_thread(
            sounddevice.RawInputStream,
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=1,
            dtype="int16",
            device=self.device,
        )
        try:
            await asyncio.to_thread(self._stream.start)
        except Exception:
            await self.aclose()
            raise

    async def aclose(self) -> None:
        """Stop and close the stream, even when capture ends at an endpoint."""
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            await asyncio.to_thread(stream.stop)
        finally:
            await asyncio.to_thread(stream.close)


class MicrophoneCapture:
    """Capture exactly one model-endpointed, PCM16 microphone turn."""

    def __init__(
        self,
        *,
        block_source: BlockSourceFactory | BlockSource | None = None,
        vad_factory: VadFactory | None = None,
        sample_rate: int = VOICE_INPUT_SAMPLE_RATE_HERTZ,
        block_size: int = 512,
        device: int | str | None = None,
        vad_threshold: float = 0.5,
        silence_duration_seconds: float | None = None,
        min_speech_duration_milliseconds: int | None = None,
        max_duration_seconds: float | None = None,
        settings: Any | None = None,
    ) -> None:
        if silence_duration_seconds is None or min_speech_duration_milliseconds is None or max_duration_seconds is None:
            if settings is None:
                from app.config import settings as app_settings

                settings = app_settings
            silence_duration_seconds = (
                settings.voice_vad_silence_duration_seconds
                if silence_duration_seconds is None
                else silence_duration_seconds
            )
            min_speech_duration_milliseconds = (
                settings.voice_vad_min_speech_duration_milliseconds
                if min_speech_duration_milliseconds is None
                else min_speech_duration_milliseconds
            )
            max_duration_seconds = (
                settings.voice_capture_max_duration_seconds
                if max_duration_seconds is None
                else max_duration_seconds
            )
        assert silence_duration_seconds is not None
        assert min_speech_duration_milliseconds is not None
        assert max_duration_seconds is not None
        if sample_rate != VOICE_INPUT_SAMPLE_RATE_HERTZ:
            raise ValueError(f"voice input must be {VOICE_INPUT_SAMPLE_RATE_HERTZ} Hz")
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        if not 0 < vad_threshold < 1:
            raise ValueError("vad_threshold must be between zero and one")
        if silence_duration_seconds <= 0:
            raise ValueError("silence_duration_seconds must be positive")
        if min_speech_duration_milliseconds <= 0:
            raise ValueError("min_speech_duration_milliseconds must be positive")
        if max_duration_seconds <= 0:
            raise ValueError("max_duration_seconds must be positive")
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device = device
        self.vad_threshold = vad_threshold
        self.silence_duration_seconds = silence_duration_seconds
        self.min_speech_duration_milliseconds = min_speech_duration_milliseconds
        self.max_duration_seconds = max_duration_seconds
        self._block_source = block_source
        self._vad_factory = vad_factory
        self._vad_model: Any = None
        self._capture_lock = asyncio.Lock()

    async def capture(self, stop_requested: asyncio.Event) -> CapturedTurn | None:
        """Consume one hotkey turn; return no turn when Silero never observes speech."""
        if stop_requested.is_set():
            return None
        async with self._capture_lock:
            if stop_requested.is_set():
                return None
            source = await self._source()
            vad = await self._new_vad()
            started_at = datetime.now(UTC)
            max_samples = max(1, round(self.max_duration_seconds * self.sample_rate))
            captured = bytearray()
            collected_samples = 0
            speech_start: int | None = None
            endpoint_end: int | None = None
            try:
                async for raw_block in source:
                    if stop_requested.is_set():
                        break
                    block = _as_pcm16_bytes(raw_block)
                    remaining = max_samples - collected_samples
                    if remaining <= 0:
                        break
                    block = block[: remaining * 2]
                    if not block:
                        continue
                    block_start = collected_samples
                    captured.extend(block)
                    block_samples = len(block) // 2
                    collected_samples += block_samples
                    event = await asyncio.to_thread(vad, _as_vad_samples(block))
                    if event is None:
                        continue
                    if not isinstance(event, dict):
                        raise TypeError("Silero VAD iterator must return a start/end event or None")
                    if "start" in event and speech_start is None:
                        speech_start = _event_sample(event["start"], block_start, collected_samples)
                    if "end" in event and speech_start is not None:
                        candidate_end = _event_sample(event["end"], block_start, collected_samples)
                        if candidate_end - speech_start >= round(
                            self.min_speech_duration_milliseconds * self.sample_rate / 1000
                        ):
                            endpoint_end = candidate_end
                            break
                        speech_start = None
                    if collected_samples >= max_samples:
                        break
            finally:
                await _close_source(source)

            if speech_start is None:
                return None
            end_sample = endpoint_end or collected_samples
            start_sample = min(max(0, speech_start), end_sample)
            samples = bytes(captured[start_sample * 2 : end_sample * 2])
            if not samples:
                return None
            duration_ms = round(len(samples) / 2 / self.sample_rate * 1000)
            return CapturedTurn(samples, self.sample_rate, started_at, duration_ms)

    async def _source(self) -> BlockSource:
        if self._block_source is None:
            return SoundDeviceBlockSource(
                sample_rate=self.sample_rate,
                block_size=self.block_size,
                device=self.device,
            )
        source = self._block_source() if callable(self._block_source) else self._block_source
        if hasattr(source, "__await__"):
            source = await source
        return source

    async def _new_vad(self) -> Any:
        if self._vad_factory is not None:
            vad = await asyncio.to_thread(self._vad_factory)
            if hasattr(vad, "__await__"):
                vad = await vad
            return vad
        if self._vad_model is None:
            from silero_vad import load_silero_vad

            self._vad_model = await asyncio.to_thread(load_silero_vad)
        from silero_vad import VADIterator

        return VADIterator(
            self._vad_model,
            threshold=self.vad_threshold,
            sampling_rate=self.sample_rate,
            min_silence_duration_ms=round(self.silence_duration_seconds * 1000),
        )


def _as_pcm16_bytes(block: PcmBlock) -> bytes:
    if isinstance(block, bytes):
        return block if len(block) % 2 == 0 else block[:-1]
    if isinstance(block, (bytearray, memoryview)):
        data = bytes(block)
        return data if len(data) % 2 == 0 else data[:-1]
    array = np.asarray(block)
    if array.ndim != 1:
        raise ValueError("voice input blocks must be mono")
    if np.issubdtype(array.dtype, np.floating):
        array = np.rint(np.clip(array, -1, 1) * 32767).astype("<i2")
    else:
        array = array.astype("<i2", copy=False)
    return array.tobytes()


def _as_vad_samples(block: bytes) -> np.ndarray:
    """Convert PCM16 to the normalized waveform Silero consumes; this is a format conversion, not detection."""
    return np.frombuffer(block, dtype="<i2").astype(np.float32) / 32768.0


def _event_sample(value: object, block_start: int, collected_samples: int) -> int:
    if not isinstance(value, (int, float)):
        raise TypeError("Silero VAD event positions must be numeric sample offsets")
    return min(max(0, round(value)), collected_samples)


async def _close_source(source: BlockSource) -> None:
    close = getattr(source, "aclose", None)
    if close is not None:
        result = await asyncio.to_thread(close)
        if hasattr(result, "__await__"):
            await result
