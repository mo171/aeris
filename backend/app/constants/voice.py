"""Defines the non-negotiable PCM contract and lifecycle vocabulary of an offline voice session.

what  : Fixed audio formats shared by capture and playback, plus the explicit states a voice session can
        report without inventing ad-hoc strings.
where : Imported by voice adapters and `app.config`; device choices and operational timing remain settings.
how   : Whisper and Silero require mono 16 kHz PCM16 input. The explicitly configured Piper Alba profile
        emits a 22.05 kHz float waveform, which the playback adapter converts to mono PCM16 for
        `RawOutputStream`. These are model-interface invariants, not deployment preferences.
"""

from enum import StrEnum
from typing import Final


class VoiceSessionState(StrEnum):
    """Every observable lifecycle state for one terminal voice session."""

    IDLE = "idle"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    PENDING_APPROVAL = "pending-approval"
    RUNNING = "running"
    STANDBY = "standby"
    FAILED = "failed"
    CLOSED = "closed"


class SpeechKind(StrEnum):
    """The evidence source and presentation policy of one utterance."""

    GROUNDED = "grounded"
    PROVISIONAL = "provisional"
    PROGRESS = "progress"
    REFUSAL = "refusal"


# Mono PCM16 is the model and `Raw*Stream` boundary. Channel count and sample width must not vary by host.
VOICE_INPUT_CHANNELS: Final[int] = 1
VOICE_INPUT_SAMPLE_WIDTH_BYTES: Final[int] = 2
VOICE_INPUT_SAMPLE_RATE_HERTZ: Final[int] = 16_000
# Silero's 16 kHz streaming model accepts this exact window. Partial windows are retained for transcription,
# but never sent to the model because shape-dependent inference is not endpointing.
VOICE_VAD_WINDOW_SAMPLES: Final[int] = 512

# Piper's explicitly configured Alba profile emits float samples at 22.05 kHz; the playback boundary
# serialises them as mono PCM16.
VOICE_OUTPUT_CHANNELS: Final[int] = 1
VOICE_OUTPUT_SAMPLE_WIDTH_BYTES: Final[int] = 2
VOICE_OUTPUT_SAMPLE_RATE_HERTZ: Final[int] = 22_050

SUPPORTED_VOICE_INPUT_SAMPLE_RATES_HERTZ: Final[frozenset[int]] = frozenset({VOICE_INPUT_SAMPLE_RATE_HERTZ})
SUPPORTED_VOICE_OUTPUT_SAMPLE_RATES_HERTZ: Final[frozenset[int]] = frozenset({VOICE_OUTPUT_SAMPLE_RATE_HERTZ})
