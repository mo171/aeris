"""Focused tests for the offline microphone-turn and transcription boundaries.

The blocks below are synthetic PCM16 arrays. They are deliberately not presented as a human recording:
the Task 8 real-device gate is the only place where microphone quality is measured. A fake VAD iterator
returns model decisions, which keeps these tests about endpoint policy rather than signal heuristics.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest

from app.voice.audio import MicrophoneCapture
from app.voice.transcription import WhisperTranscriber, normalize_transcript
from app.voice.types import CapturedTurn, Transcript


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
    assert len(result.samples) == 1_024


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
