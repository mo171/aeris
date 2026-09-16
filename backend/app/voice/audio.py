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

from app.constants.voice import VOICE_INPUT_SAMPLE_RATE_HERTZ, VOICE_VAD_WINDOW_SAMPLES
from app.voice.types import CapturedTurn, VoiceInputError

PcmBlock = bytes | bytearray | memoryview | np.ndarray
BlockSource = AsyncIterator[PcmBlock]
BlockSourceFactory = Callable[[], BlockSource]
VadFactory = Callable[[], Any]
_STOP_REQUESTED = object()


class SoundDeviceBlockSource:
    """Async iterator over mono PCM16 blocks from one sounddevice raw input stream."""

    def __init__(
        self,
        *,
        sample_rate: int = VOICE_INPUT_SAMPLE_RATE_HERTZ,
        block_size: int = VOICE_VAD_WINDOW_SAMPLES,
        device: int | str | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.device = device
        self._stream: Any = None
        self._read_task: asyncio.Task[Any] | None = None

    def __aiter__(self) -> SoundDeviceBlockSource:
        return self

    async def __anext__(self) -> bytes:
        if self._stream is None:
            await self._open()
        read_task = asyncio.create_task(asyncio.to_thread(self._stream.read, self.block_size))
        self._read_task = read_task
        try:
            data, _overflowed = await asyncio.shield(read_task)
        except asyncio.CancelledError:
            # Cancellation cannot close PortAudio while its worker is still inside read(). Abort first,
            # await the worker, and let capture's finally block perform the subsequent close.
            await self._abort_read()
            raise
        except (StopAsyncIteration, EOFError) as error:
            await self._abort_read()
            raise StopAsyncIteration from error
        except Exception as error:
            await self._abort_read()
            raise await self._input_error("read", error) from error
        finally:
            if self._read_task is read_task:
                self._read_task = None
        return bytes(data)

    async def _open(self) -> None:
        """Construct and start the blocking PortAudio stream outside asyncio's event loop."""
        try:
            import sounddevice

            self._stream = await asyncio.to_thread(
                sounddevice.RawInputStream,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                channels=1,
                dtype="int16",
                device=self.device,
            )
        except Exception as error:
            raise await self._input_error("open", error) from error
        try:
            await asyncio.to_thread(self._stream.start)
        except Exception as error:
            await self.aclose()
            raise await self._input_error("start", error) from error

    async def _abort_read(self) -> None:
        read_task = self._read_task
        stream = self._stream
        if read_task is None or read_task.done() or stream is None:
            if read_task is not None:
                try:
                    await asyncio.shield(read_task)
                except Exception:
                    pass
            return
        abort = getattr(stream, "abort", None) or getattr(stream, "stop", None)
        if abort is not None:
            await asyncio.to_thread(abort)
        try:
            await asyncio.shield(read_task)
        except (StopAsyncIteration, EOFError, asyncio.CancelledError):
            pass
        except Exception:
            pass

    async def aclose(self) -> None:
        """Stop and close the stream, even when capture ends at an endpoint."""
        await self._abort_read()
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            await asyncio.to_thread(stream.stop)
        finally:
            await asyncio.to_thread(stream.close)

    async def _input_error(self, operation: str, cause: BaseException) -> VoiceInputError:
        try:
            import sounddevice

            inventory = await asyncio.to_thread(sounddevice.query_devices)
            devices = tuple(
                str(item.get("name", item)) if isinstance(item, dict) else str(item) for item in inventory
            )
        except Exception:
            devices = ()
        return VoiceInputError(
            str(cause) or type(cause).__name__,
            operation=operation,
            devices=devices,
            remediation=(
                "Connect an input microphone and set VOICE_INPUT_DEVICE to one of the listed device names "
                "or indices, then retry"
            ),
        )


class MicrophoneCapture:
    """Capture exactly one model-endpointed, PCM16 microphone turn."""

    def __init__(
        self,
        *,
        block_source: BlockSourceFactory | BlockSource | None = None,
        vad_factory: VadFactory | None = None,
        sample_rate: int = VOICE_INPUT_SAMPLE_RATE_HERTZ,
        block_size: int = VOICE_VAD_WINDOW_SAMPLES,
        device: int | str | None = None,
        vad_threshold: float = 0.5,
        silence_duration_seconds: float | None = None,
        min_speech_duration_milliseconds: int | None = None,
        max_duration_seconds: float | None = None,
        settings: Any | None = None,
    ) -> None:
        self._settings = settings
        if silence_duration_seconds is None or min_speech_duration_milliseconds is None or max_duration_seconds is None:
            if self._settings is None:
                from app.config import settings as app_settings

                self._settings = app_settings
            silence_duration_seconds = (
                self._settings.voice_vad_silence_duration_seconds
                if silence_duration_seconds is None
                else silence_duration_seconds
            )
            min_speech_duration_milliseconds = (
                self._settings.voice_vad_min_speech_duration_milliseconds
                if min_speech_duration_milliseconds is None
                else min_speech_duration_milliseconds
            )
            max_duration_seconds = (
                self._settings.voice_capture_max_duration_seconds
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
        configured_device = getattr(self._settings, "voice_input_device", None)
        self.device = configured_device if device is None else device
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
            pending_vad = bytearray()
            collected_samples = 0
            vad_samples = 0
            speech_start: int | None = None
            endpoint_end: int | None = None
            try:
                while not stop_requested.is_set():
                    try:
                        raw_block = await _next_block_or_stop(source, stop_requested)
                    except StopAsyncIteration:
                        break
                    if raw_block is _STOP_REQUESTED:
                        break
                    block = _as_pcm16_bytes(raw_block)
                    remaining = max_samples - collected_samples
                    if remaining <= 0:
                        break
                    block = block[: remaining * 2]
                    if not block:
                        continue
                    captured.extend(block)
                    collected_samples += len(block) // 2
                    pending_vad.extend(block)
                    while len(pending_vad) >= VOICE_VAD_WINDOW_SAMPLES * 2:
                        vad_block = bytes(pending_vad[: VOICE_VAD_WINDOW_SAMPLES * 2])
                        del pending_vad[: VOICE_VAD_WINDOW_SAMPLES * 2]
                        event = await asyncio.to_thread(vad, _as_vad_samples(vad_block))
                        vad_samples += VOICE_VAD_WINDOW_SAMPLES
                        if event is None:
                            continue
                        if not isinstance(event, dict):
                            raise TypeError("Silero VAD iterator must return a start/end event or None")
                        if "start" in event and speech_start is None:
                            speech_start = _event_sample(event["start"], vad_samples)
                        if "end" in event and speech_start is not None:
                            candidate_end = _event_sample(event["end"], vad_samples)
                            if candidate_end - speech_start >= round(
                                self.min_speech_duration_milliseconds * self.sample_rate / 1000
                            ):
                                endpoint_end = candidate_end
                                break
                            speech_start = None
                    if endpoint_end is not None or collected_samples >= max_samples:
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
        if len(block) % 2:
            raise ValueError("PCM16 blocks must contain an even number of bytes")
        return block
    if isinstance(block, (bytearray, memoryview)):
        data = bytes(block)
        if len(data) % 2:
            raise ValueError("PCM16 blocks must contain an even number of bytes")
        return data
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


def _event_sample(value: object, collected_samples: int) -> int:
    if not isinstance(value, (int, float)):
        raise TypeError("Silero VAD event positions must be numeric sample offsets")
    return min(max(0, round(value)), collected_samples)


async def _close_source(source: BlockSource) -> None:
    close = getattr(source, "aclose", None)
    if close is not None:
        result = await asyncio.to_thread(close)
        if hasattr(result, "__await__"):
            await result


async def _next_block_or_stop(source: BlockSource, stop_requested: asyncio.Event) -> PcmBlock | object:
    """Race one device read against the second hotkey and finish the read before capture closes it."""
    next_task = asyncio.create_task(anext(source))
    stop_task = asyncio.create_task(stop_requested.wait())
    try:
        done, _ = await asyncio.wait((next_task, stop_task), return_when=asyncio.FIRST_COMPLETED)
        if next_task in done:
            return await next_task
        next_task.cancel()
        await asyncio.gather(next_task, return_exceptions=True)
        return _STOP_REQUESTED
    except asyncio.CancelledError:
        next_task.cancel()
        await asyncio.gather(next_task, return_exceptions=True)
        raise
    finally:
        stop_task.cancel()
        await asyncio.gather(stop_task, return_exceptions=True)
