"""Offline voice adapters for capture, model-authored speech, and local playback.

The package exposes only typed turns, validated prose, and cancellable audio boundaries. Session routing and
scientific execution remain outside this package, so a device adapter cannot accidentally start an agent.
"""

from app.voice.audio import MicrophoneCapture, SoundDeviceBlockSource
from app.voice.session import VoiceSession
from app.voice.speech import (
    AuthoredSpeech,
    SpeechGenerationError,
    SpeechRequest,
    author_grounded_speech,
    author_progress_speech,
    author_provisional_speech,
)
from app.voice.synthesis import (
    AudioChunk,
    KokoroSynthesizer,
    PiperSynthesizer,
    SpeechPlaybackError,
    SpeechPlayer,
    SpeechSynthesisError,
)
from app.voice.transcription import WhisperTranscriber, normalize_transcript
from app.voice.turns import VoiceTurnAction, VoiceTurnDecision, classify_voice_turn
from app.voice.types import CapturedTurn, Transcript, TranscriptSegment, VoiceInputError

__all__ = [
    "CapturedTurn",
    "MicrophoneCapture",
    "SoundDeviceBlockSource",
    "Transcript",
    "TranscriptSegment",
    "VoiceInputError",
    "WhisperTranscriber",
    "normalize_transcript",
    "AuthoredSpeech",
    "SpeechGenerationError",
    "SpeechRequest",
    "author_grounded_speech",
    "author_progress_speech",
    "author_provisional_speech",
    "AudioChunk",
    "KokoroSynthesizer",
    "PiperSynthesizer",
    "SpeechPlaybackError",
    "SpeechPlayer",
    "SpeechSynthesisError",
    "VoiceSession",
    "VoiceTurnAction",
    "VoiceTurnDecision",
    "classify_voice_turn",
]
