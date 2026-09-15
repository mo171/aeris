"""Defines the non-negotiable PCM contract and lifecycle vocabulary of an offline voice session.

what  : Fixed audio formats shared by capture and playback, plus the explicit states a voice session can
        report without inventing ad-hoc strings.
where : Imported by voice adapters and `app.config`; device choices and operational timing remain settings.
how   : Whisper and Silero require mono 16 kHz PCM16 input, while the selected Kokoro pipeline emits mono
        24 kHz PCM16. These are model-interface invariants, not deployment preferences.
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


# Mono PCM16 is the model and `Raw*Stream` boundary. Channel count and sample width must not vary by host.
VOICE_INPUT_CHANNELS: Final[int] = 1
VOICE_INPUT_SAMPLE_WIDTH_BYTES: Final[int] = 2
VOICE_INPUT_SAMPLE_RATE_HERTZ: Final[int] = 16_000

# Kokoro's selected local pipeline currently yields mono PCM16 at 24 kHz.
VOICE_OUTPUT_CHANNELS: Final[int] = 1
VOICE_OUTPUT_SAMPLE_WIDTH_BYTES: Final[int] = 2
VOICE_OUTPUT_SAMPLE_RATE_HERTZ: Final[int] = 24_000

SUPPORTED_VOICE_INPUT_SAMPLE_RATES_HERTZ: Final[frozenset[int]] = frozenset({VOICE_INPUT_SAMPLE_RATE_HERTZ})
SUPPORTED_VOICE_OUTPUT_SAMPLE_RATES_HERTZ: Final[frozenset[int]] = frozenset({VOICE_OUTPUT_SAMPLE_RATE_HERTZ})

# CTranslate2 compute profiles accepted by the local faster-whisper adapter. Float16 profiles need CUDA.
VOICE_WHISPER_COMPUTE_TYPES: Final[frozenset[str]] = frozenset({"int8", "float32", "float16", "int8_float16"})
VOICE_WHISPER_CPU_COMPUTE_TYPES: Final[frozenset[str]] = frozenset({"int8", "float32"})
