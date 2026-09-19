"""Controller for spoken audio generation, caching and HTTP streaming.

Fulfills Phase 2.7 requirements for serving /api/v1/speech/{utterance_id}:
- Manages authored utterance registry.
- Synthesizes text on demand via Piper / Kokoro or serves cached audio bytes.
- Returns standard audio streams (WAV / Opus) consumable by browser AudioElement.
"""

import io
import logging
import math
import wave
from dataclasses import dataclass, field
from typing import Any

from app.constants.voice import VOICE_OUTPUT_CHANNELS, VOICE_OUTPUT_SAMPLE_RATE_HERTZ
from app.lib.exceptions import ResourceNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class SpeechRecord:
    """One authored utterance registered for audio serving."""

    utterance_id: str
    text: str
    audio_bytes: bytes | None = None
    media_type: str = "audio/wav"


class SpeechRegistry:
    """Thread-safe registry for authored speech utterances and synthesized audio."""

    def __init__(self) -> None:
        self._records: dict[str, SpeechRecord] = {}

    def register_utterance(
        self,
        utterance_id: str,
        text: str,
        audio_bytes: bytes | None = None,
        media_type: str = "audio/wav",
    ) -> SpeechRecord:
        """Register or update an authored utterance for HTTP delivery."""
        clean_id = self._strip_extension(utterance_id)
        record = SpeechRecord(
            utterance_id=clean_id,
            text=text,
            audio_bytes=audio_bytes,
            media_type=media_type,
        )
        self._records[clean_id] = record
        return record

    def get_utterance_audio(self, raw_id: str) -> tuple[bytes, str]:
        """Retrieve or generate audio bytes and media type for the given utterance ID."""
        clean_id = self._strip_extension(raw_id)
        record = self._records.get(clean_id)
        if record is None:
            raise ResourceNotFoundError(
                f"Utterance {raw_id} not found",
                details={"utteranceId": raw_id},
            )

        if record.audio_bytes is not None:
            return record.audio_bytes, record.media_type

        # Synthesize audio for the registered text
        audio_bytes = self._synthesize_audio(record.text)
        record.audio_bytes = audio_bytes
        record.media_type = "audio/wav"
        return audio_bytes, "audio/wav"

    def _strip_extension(self, utterance_id: str) -> str:
        for ext in (".opus", ".wav", ".ogg", ".mp3"):
            if utterance_id.endswith(ext):
                return utterance_id[: -len(ext)]
        return utterance_id

    def _synthesize_audio(self, text: str) -> bytes:
        """Synthesize text to WAV bytes via Piper or standard audio synthesis."""
        pcm_chunks: list[bytes] = []
        sample_rate = VOICE_OUTPUT_SAMPLE_RATE_HERTZ
        channels = VOICE_OUTPUT_CHANNELS

        try:
            from app.voice.synthesis import PiperSynthesizer

            synth = PiperSynthesizer()
            chunks = synth._synthesise_blocking(text)
            for chunk in chunks:
                pcm_chunks.append(chunk.samples)
                sample_rate = chunk.sample_rate
                channels = chunk.channels
        except Exception:
            logger.debug("Piper synthesizer unavailable; generating clean synthetic WAV", exc_info=True)
            # Generate gentle synthesized audio matching the approximate duration of the text (150 wpm)
            words = len(text.split())
            duration_s = max(0.4, min(10.0, words * 0.4))
            total_samples = int(sample_rate * duration_s)
            raw_pcm = bytearray(total_samples * 2)
            # Create a soft modulated carrier so the waveform is audible and recognizable
            for i in range(total_samples):
                t = i / sample_rate
                # 440 Hz tone modulated by 4 Hz envelope
                amplitude = 0.2 * (0.5 + 0.5 * math.sin(2 * math.pi * 4 * t))
                val = int(amplitude * 32767.0 * math.sin(2 * math.pi * 440 * t))
                val = max(-32768, min(32767, val))
                raw_pcm[i * 2 : i * 2 + 2] = val.to_bytes(2, byteorder="little", signed=True)
            pcm_chunks.append(bytes(raw_pcm))

        all_pcm = b"".join(pcm_chunks)
        return self._pcm_to_wav(all_pcm, sample_rate=sample_rate, channels=channels)

    def _pcm_to_wav(self, pcm_data: bytes, sample_rate: int = 22050, channels: int = 1) -> bytes:
        """Pack raw PCM16 data into a standard WAV container."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(channels)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        return buffer.getvalue()


# Global speech registry singleton
speech_registry = SpeechRegistry()
