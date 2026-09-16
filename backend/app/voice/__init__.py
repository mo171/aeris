"""Offline voice input adapters.

The package deliberately stops at a typed captured turn and transcript. Session routing, speech authoring,
and playback belong to the later voice-loop stages, so an input adapter cannot accidentally start an agent.
"""

from app.voice.audio import MicrophoneCapture, SoundDeviceBlockSource
from app.voice.transcription import WhisperTranscriber, normalize_transcript
from app.voice.types import CapturedTurn, Transcript, TranscriptSegment

__all__ = [
    "CapturedTurn",
    "MicrophoneCapture",
    "SoundDeviceBlockSource",
    "Transcript",
    "TranscriptSegment",
    "WhisperTranscriber",
    "normalize_transcript",
]
