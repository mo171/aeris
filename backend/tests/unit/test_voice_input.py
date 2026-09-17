"""Focused tests for the offline microphone-turn and transcription boundaries.

The blocks below are synthetic PCM16 arrays. They are deliberately not presented as a human recording:
the Task 8 real-device gate is the only place where microphone quality is measured. A fake VAD iterator
returns model decisions, which keeps these tests about endpoint policy rather than signal heuristics.
"""

import asyncio
import sys
import threading
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest

from app.voice.audio import MicrophoneCapture, SoundDeviceBlockSource
from app.voice.transcription import WhisperTranscriber, normalize_transcript
from app.voice.types import CapturedTurn, Transcript, VoiceInputError


def pcm_block(value: int, samples: int = 512) -> bytes:
    """Make a provenance-safe synthetic PCM16 block; values are never used as a speech heuristic."""
    return np.full(samples, value, dtype=np.int16).tobytes()


def source_for(*blocks: bytes):
    async def source():
        for block in blocks:
            yield block

    return source


class ScriptedVad:
    def __init__(self, events: list[dict[str, int] | None]) -> None:
        self.events = iter(events)

    def __call__(self, _samples: np.ndarray) -> dict[str, int] | None:
        return next(self.events, None)


class ShapeRecordingVad:
    def __init__(self) -> None:
        self.shapes: list[int] = []

    def __call__(self, samples: np.ndarray) -> dict[str, int] | None:
        self.shapes.append(len(samples))
        return {"start": 0} if len(self.shapes) == 1 else None


@pytest.mark.asyncio
async def test_silence_returns_no_turn_without_transcript() -> None:
    capture = MicrophoneCapture(
        block_source=source_for(pcm_block(0), pcm_block(0)),
        vad_factory=lambda: ScriptedVad([None, None]),
        max_duration_seconds=1,
    )

    result = await capture.capture(asyncio.Event())

    assert result is None


@pytest.mark.asyncio
async def test_speech_followed_by_model_silence_returns_trimmed_turn() -> None:
    capture = MicrophoneCapture(
        block_source=source_for(pcm_block(0), pcm_block(100), pcm_block(100), pcm_block(0)),
        vad_factory=lambda: ScriptedVad([
            None,
            {"start": 512},
            None,
            {"end": 1_450},
        ]),
        max_duration_seconds=2,
        min_speech_duration_milliseconds=20,
    )

    result = await capture.capture(asyncio.Event())

    assert result is not None
    assert result.sample_rate == 16_000
    assert result.samples == pcm_block(100, 938)
    assert result.duration_ms == 59
    assert result.started_at.tzinfo is UTC


@pytest.mark.asyncio
async def test_vad_receives_only_fixed_512_sample_windows_and_no_partial_window() -> None:
    vad = ShapeRecordingVad()
    capture = MicrophoneCapture(
        block_source=source_for(pcm_block(100, 300), pcm_block(100, 400)),
        vad_factory=lambda: vad,
        silence_duration_seconds=0.1,
        min_speech_duration_milliseconds=1,
        max_duration_seconds=1,
    )

    result = await capture.capture(asyncio.Event())

    assert result is not None
    assert vad.shapes == [512]


@pytest.mark.asyncio
async def test_default_capture_boundary_is_30_seconds_and_still_drops_partial_vad_window() -> None:
    vad = ShapeRecordingVad()
    settings = type(
        "VoiceSettings",
        (),
        {
            "voice_vad_silence_duration_seconds": 0.8,
            "voice_vad_min_speech_duration_milliseconds": 250,
            "voice_capture_max_duration_seconds": 30.0,
        },
    )()
    capture = MicrophoneCapture(
        block_source=source_for(np.zeros(480_256 + 256, dtype=np.int16)),
        vad_factory=lambda: vad,
        settings=settings,
    )

    result = await capture.capture(asyncio.Event())

    assert result is not None
    assert len(result.samples) == 480_000 * 2
    assert len(vad.shapes) == 937
    assert set(vad.shapes) == {512}


@pytest.mark.asyncio
async def test_odd_pcm16_block_is_rejected_instead_of_silently_truncated() -> None:
    capture = MicrophoneCapture(
        block_source=source_for(b"\x01"),
        vad_factory=lambda: ScriptedVad([]),
        silence_duration_seconds=0.1,
        min_speech_duration_milliseconds=1,
        max_duration_seconds=1,
    )

    with pytest.raises(ValueError, match="even number of bytes"):
        await capture.capture(asyncio.Event())


@pytest.mark.asyncio
async def test_background_noise_probability_without_vad_start_is_ignored() -> None:
    capture = MicrophoneCapture(
        block_source=source_for(pcm_block(2_000), pcm_block(-2_000), pcm_block(1_500)),
        vad_factory=lambda: ScriptedVad([None, None, None]),
    )

    assert await capture.capture(asyncio.Event()) is None


@pytest.mark.asyncio
async def test_maximum_duration_bounds_a_speech_turn() -> None:
    capture = MicrophoneCapture(
        block_source=source_for(*([pcm_block(1_000)] * 5)),
        vad_factory=lambda: ScriptedVad([{"start": 0}, None, None, None, None]),
        max_duration_seconds=0.1,
        min_speech_duration_milliseconds=1,
    )

    result = await capture.capture(asyncio.Event())

    assert result is not None
    assert len(result.samples) == 3_200  # 100 ms * 16,000 samples/s * 2 bytes/sample
    assert result.duration_ms == 100


@pytest.mark.asyncio
async def test_explicit_stop_ends_an_active_turn_without_waiting_for_vad_silence() -> None:
    stop_requested = asyncio.Event()

    async def blocks():
        yield pcm_block(100)
        stop_requested.set()
        yield pcm_block(100)

    capture = MicrophoneCapture(
        block_source=blocks,
        vad_factory=lambda: ScriptedVad([{"start": 0}, None]),
        min_speech_duration_milliseconds=10_000,
    )

    result = await capture.capture(stop_requested)

    assert result is not None
    assert len(result.samples) == 2_048


@pytest.mark.asyncio
async def test_configured_input_device_is_used_by_the_no_arg_source() -> None:
    class VoiceSettings:
        voice_input_device = "Configured microphone"
        voice_vad_silence_duration_seconds = 0.1
        voice_vad_min_speech_duration_milliseconds = 1
        voice_capture_max_duration_seconds = 1

    capture = MicrophoneCapture(settings=VoiceSettings())
    source = await capture._source()

    assert isinstance(source, SoundDeviceBlockSource)
    assert source.device == "Configured microphone"


@pytest.mark.asyncio
async def test_portaudio_abort_waits_for_read_worker_before_close() -> None:
    release = threading.Event()
    order: list[str] = []

    class BlockingStream:
        def read(self, _block_size: int) -> tuple[bytes, bool]:
            release.wait(timeout=2)
            order.append("read_done")
            return b"", False

        def abort(self) -> None:
            order.append("abort")
            release.set()

        def stop(self) -> None:
            order.append("stop")

        def close(self) -> None:
            order.append("close")

    source = SoundDeviceBlockSource()
    source._stream = BlockingStream()
    read_task = asyncio.create_task(source.__anext__())
    await asyncio.sleep(0)
    read_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await read_task
    await source.aclose()

    assert order.index("abort") < order.index("read_done") < order.index("close")


@pytest.mark.asyncio
async def test_second_hotkey_aborts_portaudio_read_before_capture_closes_source() -> None:
    release = threading.Event()
    started = threading.Event()
    order: list[str] = []

    class BlockingStream:
        def read(self, _block_size: int) -> tuple[bytes, bool]:
            started.set()
            release.wait(timeout=2)
            order.append("read_done")
            return b"", False

        def abort(self) -> None:
            order.append("abort")
            release.set()

        def stop(self) -> None:
            order.append("stop")

        def close(self) -> None:
            order.append("close")

    source = SoundDeviceBlockSource()
    source._stream = BlockingStream()
    capture = MicrophoneCapture(
        block_source=source,
        vad_factory=lambda: ScriptedVad([]),
        silence_duration_seconds=0.1,
        min_speech_duration_milliseconds=1,
        max_duration_seconds=1,
    )
    stop_requested = asyncio.Event()
    capture_task = asyncio.create_task(capture.capture(stop_requested))
    await asyncio.to_thread(started.wait, 1)
    stop_requested.set()

    assert await capture_task is None
    assert order.index("abort") < order.index("read_done") < order.index("close")


@pytest.mark.asyncio
async def test_device_open_error_contains_inventory_and_remediation(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSoundDevice:
        @staticmethod
        def RawInputStream(**_kwargs: Any):
            raise RuntimeError("no input device")

        @staticmethod
        def query_devices():
            return [{"name": "Built-in Mic"}, {"name": "USB Mic"}]

    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice)
    source = SoundDeviceBlockSource(device="Missing Mic")

    with pytest.raises(VoiceInputError) as raised:
        await source.__anext__()

    assert raised.value.devices == ("Built-in Mic", "USB Mic")
    assert "VOICE_INPUT_DEVICE" in raised.value.remediation


def test_transcript_normalization_is_case_and_whitespace_stable() -> None:
    assert normalize_transcript("  Where   IS the reservoir? ") == "where is the reservoir"


@pytest.mark.asyncio
async def test_transcriber_uses_injected_model_and_normalizes_segments() -> None:
    class FakeModel:
        def transcribe(self, audio: np.ndarray, **kwargs: Any):
            assert audio.dtype == np.float32
            assert kwargs == {
                "language": "en",
                "word_timestamps": True,
                "vad_filter": False,
            }
            return [type("Segment", (), {"text": "  Where   IS the reservoir? "})()], type(
                "Info", (), {"language": "en"}
            )()

    turn = CapturedTurn(
        samples=pcm_block(100),
        sample_rate=16_000,
        started_at=datetime.now(UTC),
        duration_ms=32,
    )
    transcriber = WhisperTranscriber(model=FakeModel(), language="en")

    result = await transcriber.transcribe(turn)

    assert isinstance(result, Transcript)
    assert result.text == "where is the reservoir"
    assert result.language == "en"


@pytest.mark.asyncio
async def test_transcriber_uses_configured_language_when_language_is_omitted() -> None:
    calls: list[str | None] = []

    class FakeModel:
        def transcribe(self, _audio: np.ndarray, **kwargs: Any):
            calls.append(kwargs["language"])
            return [], type("Info", (), {"language": "fr"})()

    class VoiceSettings:
        voice_whisper_language = "fr"

    turn = CapturedTurn(b"\x00\x00" * 512, 16_000, datetime.now(UTC), 32)
    transcriber = WhisperTranscriber(model=FakeModel(), settings=VoiceSettings())

    await transcriber.transcribe(turn)

    assert calls == ["fr"]
