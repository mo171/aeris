"""Typed boundaries shared by microphone capture and offline transcription."""

from dataclasses import dataclass
from datetime import datetime

from app.constants.voice import VOICE_INPUT_SAMPLE_RATE_HERTZ


@dataclass(frozen=True, slots=True)
class CapturedTurn:
    """The PCM16 waveform for one explicitly activated microphone turn."""

    samples: bytes
    sample_rate: int
    started_at: datetime
    duration_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.samples, bytes):
            raise TypeError("CapturedTurn.samples must be PCM16 bytes")
        if self.sample_rate != VOICE_INPUT_SAMPLE_RATE_HERTZ:
            raise ValueError(f"voice input must be {VOICE_INPUT_SAMPLE_RATE_HERTZ} Hz")
        if len(self.samples) % 2:
            raise ValueError("PCM16 samples must contain an even number of bytes")
        if self.duration_ms < 0:
            raise ValueError("duration_ms cannot be negative")


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """A faster-whisper segment retained for timing and observability."""

    text: str
    start_seconds: float | None = None
    end_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class Transcript:
    """Normalized words produced by the configured speech-recognition model."""

    text: str
    language: str | None = None
    segments: tuple[TranscriptSegment, ...] = ()
