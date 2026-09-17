"""Offline faster-whisper transcription for a VAD-delimited captured turn."""

import asyncio
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from app.constants.voice import VOICE_INPUT_SAMPLE_RATE_HERTZ
from app.voice.types import CapturedTurn, Transcript, TranscriptSegment

_WHITESPACE = re.compile(r"\s+")


class WhisperTranscriber:
    """Lazily construct faster-whisper and run its blocking generator off-thread."""

    def __init__(
        self,
        *,
        model: Any | None = None,
        model_factory: Callable[[], Any] | None = None,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
        model_directory: Path | None = None,
        settings: Any | None = None,
    ) -> None:
        if model is not None and model_factory is not None:
            raise ValueError("provide model or model_factory, not both")
        self._model = model
        self._model_factory = model_factory
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.model_directory = model_directory
        self._settings = settings
        self._model_lock = asyncio.Lock()

    async def transcribe(self, turn: CapturedTurn) -> Transcript:
        """Transcribe one VAD-delimited waveform with word timestamps and no second VAD filter."""
        if turn.sample_rate != VOICE_INPUT_SAMPLE_RATE_HERTZ:
            raise ValueError(f"voice input must be {VOICE_INPUT_SAMPLE_RATE_HERTZ} Hz")
        waveform = np.frombuffer(turn.samples, dtype="<i2").astype(np.float32) / 32768.0
        if not waveform.size:
            return Transcript("", self.language or self._configured_language())
        model = await self._get_model()
        language = self.language or self._configured_language()
        text, language, segments = await asyncio.to_thread(
            self._transcribe_blocking, model, waveform, language
        )
        return Transcript(normalize_transcript(text), language, tuple(segments))

    async def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model
            factory = self._model_factory or self._default_model_factory()
            model = await asyncio.to_thread(factory)
            if hasattr(model, "__await__"):
                model = await model
            self._model = model
            return self._model

    def _default_model_factory(self) -> Callable[[], Any]:
        from faster_whisper import WhisperModel

        settings = self._configured_settings()

        name = self.model_name or settings.voice_whisper_model
        device = self.device or settings.voice_whisper_device
        compute_type = self.compute_type or settings.voice_whisper_compute_type
        directory = self.model_directory or settings.model_weights_path
        return lambda: WhisperModel(
            name,
            device=device,
            compute_type=compute_type,
            download_root=str(directory),
        )

    def _configured_settings(self) -> Any:
        if self._settings is not None:
            return self._settings
        from app.config import settings

        return settings

    def _configured_language(self) -> str:
        return self._settings.voice_whisper_language if self._settings is not None else self._default_language()

    @staticmethod
    def _default_language() -> str:
        from app.config import settings

        return settings.voice_whisper_language

    @staticmethod
    def _transcribe_blocking(
        model: Any, waveform: np.ndarray, language: str | None
    ) -> tuple[str, str | None, list[TranscriptSegment]]:
        result = model.transcribe(
            waveform,
            language=language,
            word_timestamps=True,
            vad_filter=False,
        )
        segments_result, info = result if isinstance(result, tuple) and len(result) == 2 else (result, None)
        segments = list(segments_result)
        records: list[TranscriptSegment] = []
        for segment in segments:
            text = _segment_value(segment, "text", "")
            records.append(
                TranscriptSegment(
                    text=text,
                    start_seconds=_optional_float(_segment_value(segment, "start", None)),
                    end_seconds=_optional_float(_segment_value(segment, "end", None)),
                )
            )
        language = _segment_value(info, "language", None) if info is not None else None
        return " ".join(record.text for record in records), language, records


def normalize_transcript(text: str) -> str:
    """Normalize model punctuation/casing for stable turn classification and WER measurement."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = "".join(" " if unicodedata.category(char).startswith(("P", "S")) else char for char in normalized)
    return _WHITESPACE.sub(" ", normalized).strip()


def _segment_value(segment: Any, name: str, default: Any) -> Any:
    if isinstance(segment, dict):
        return segment.get(name, default)
    return getattr(segment, name, default)


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None
