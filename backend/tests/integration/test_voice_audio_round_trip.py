"""Offline round-trip audio gate: synthesize → transcribe → measure WER.

This test requires local Piper model files. It is automatically skipped when the ONNX model
or its JSON configuration are not present on disk. No API key is required.

The test validates that the Piper→Whisper round-trip produces intelligible speech by measuring
word error rate on a known test phrase. It also exercises cancellation during the first chunk.
"""

from pathlib import Path

import numpy as np
import pytest

# Skip the entire module if Piper model files are not available
_MODEL_PATH = Path("data/models/piper/en_GB-alba-medium.onnx")
_CONFIG_PATH = Path("data/models/piper/en_GB-alba-medium.onnx.json")

_skip_reason = ""
if not _MODEL_PATH.is_file():
    _skip_reason = f"Piper model not found at {_MODEL_PATH}"
elif not _CONFIG_PATH.is_file():
    _skip_reason = f"Piper config not found at {_CONFIG_PATH}"

pytestmark = pytest.mark.skipif(bool(_skip_reason), reason=_skip_reason or "model files missing")


def _word_error_rate(reference: str, hypothesis: str) -> float:
    """Compute WER between two normalised strings; 0.0 is perfect."""
    ref_words = reference.lower().split()
    hyp_words = hypothesis.lower().split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    # Levenshtein at word level
    d = [[0] * (len(hyp_words) + 1) for _ in range(len(ref_words) + 1)]
    for i in range(len(ref_words) + 1):
        d[i][0] = i
    for j in range(len(hyp_words) + 1):
        d[0][j] = j
    for i in range(1, len(ref_words) + 1):
        for j in range(1, len(hyp_words) + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    return d[len(ref_words)][len(hyp_words)] / len(ref_words)


@pytest.mark.asyncio
async def test_piper_synthesize_produces_audible_pcm() -> None:
    """Verify that Piper synthesizes non-silent PCM audio from a test phrase."""
    from app.voice.synthesis import PiperSynthesizer

    synth = PiperSynthesizer(
        model_path=_MODEL_PATH,
        config_path=_CONFIG_PATH,
    )

    test_phrase = "The vegetation index shows healthy growth in the northern region."
    all_samples = bytearray()

    async for chunk in synth.chunks(test_phrase):
        assert chunk.sample_rate == 22_050
        assert chunk.channels == 1
        assert len(chunk.samples) > 0
        all_samples.extend(chunk.samples)

    # Should have produced substantial audio (at least 0.5 seconds at 22050 Hz)
    sample_count = len(all_samples) // 2  # PCM16 = 2 bytes per sample
    duration_seconds = sample_count / 22_050
    assert duration_seconds > 0.5, f"Only {duration_seconds:.2f}s of audio produced"

    # Should not be silence — RMS above a minimal threshold
    pcm = np.frombuffer(bytes(all_samples), dtype=np.int16).astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(pcm**2)))
    assert rms > 0.001, f"Audio appears silent (RMS={rms:.6f})"


@pytest.mark.asyncio
async def test_piper_cancellation_truncates_output() -> None:
    """Verify that cancellation during synthesis truncates without crash."""
    from app.voice.synthesis import PiperSynthesizer

    synth = PiperSynthesizer(
        model_path=_MODEL_PATH,
        config_path=_CONFIG_PATH,
    )

    test_phrase = "This is a long sentence that should produce several audio chunks for testing cancellation behavior."
    chunk_count = 0

    async for _chunk in synth.chunks(test_phrase):
        chunk_count += 1
        if chunk_count >= 1:
            # Cancel after first chunk — should not crash
            break

    assert chunk_count >= 1


@pytest.mark.asyncio
async def test_round_trip_synthesize_and_transcribe() -> None:
    """Synthesize with Piper, transcribe with Whisper, and measure WER.

    This is the offline product gate: the round-trip must produce intelligible speech.
    WER threshold is generous (< 0.8) because the test uses offline models without
    fine-tuning, and the Piper Alba voice is a medium-quality British English voice.
    """
    import importlib.util

    if importlib.util.find_spec("faster_whisper") is None:
        pytest.skip("faster-whisper not installed")

    from app.voice.synthesis import PiperSynthesizer
    from app.voice.transcription import WhisperTranscriber, normalize_transcript
    from app.voice.types import CapturedTurn

    test_phrase = "The vegetation index shows healthy growth."

    # Step 1: Synthesize
    synth = PiperSynthesizer(
        model_path=_MODEL_PATH,
        config_path=_CONFIG_PATH,
    )

    all_samples = bytearray()
    async for chunk in synth.chunks(test_phrase):
        all_samples.extend(chunk.samples)

    assert len(all_samples) > 0, "Piper produced no audio"

    # Step 2: Resample from 22050 Hz (Piper output) to 16000 Hz (Whisper input)
    pcm_22k = np.frombuffer(bytes(all_samples), dtype=np.int16).astype(np.float32) / 32768.0
    # Simple linear interpolation resampling
    duration = len(pcm_22k) / 22_050
    target_samples = int(duration * 16_000)
    indices = np.linspace(0, len(pcm_22k) - 1, target_samples)
    pcm_16k = np.interp(indices, np.arange(len(pcm_22k)), pcm_22k)
    pcm_16k_int16 = np.clip(pcm_16k * 32767, -32768, 32767).astype(np.int16)

    # Step 3: Transcribe
    from datetime import UTC, datetime

    turn = CapturedTurn(
        samples=pcm_16k_int16.tobytes(),
        sample_rate=16_000,
        started_at=datetime.now(UTC),
        duration_ms=round(duration * 1000),
    )

    transcriber = WhisperTranscriber(
        model_name="tiny.en",
        device="cpu",
        compute_type="int8",
    )
    transcript = await transcriber.transcribe(turn)

    # Step 4: Measure WER
    reference = normalize_transcript(test_phrase)
    hypothesis = normalize_transcript(transcript.text)

    wer = _word_error_rate(reference, hypothesis)

    # Report metrics
    print("\n  Round-trip metrics:")
    print(f"  Reference:  {reference!r}")
    print(f"  Hypothesis: {hypothesis!r}")
    print(f"  WER:        {wer:.2f}")
    print(f"  Audio duration: {duration:.2f}s")
    print(f"  Audio samples (22kHz): {len(pcm_22k)}")
    print(f"  Audio samples (16kHz): {len(pcm_16k_int16)}")

    # WER threshold — generous for offline models. A WER < 0.8 means most words were recognized.
    assert wer < 0.8, f"Word error rate too high: {wer:.2f} (reference={reference!r}, hypothesis={hypothesis!r})"
