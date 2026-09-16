"""Tests for evidence-bound voice prose and the local Piper playback boundary."""

import asyncio
from dataclasses import dataclass

import pytest

from app.constants.voice import VOICE_OUTPUT_SAMPLE_RATE_HERTZ
from app.voice.speech import (
    AuthoredSpeech,
    SpeechGenerationError,
    author_grounded_speech,
    author_progress_speech,
    author_provisional_speech,
)
from app.voice.synthesis import AudioChunk, PiperSynthesizer, SpeechPlaybackError, SpeechPlayer


@dataclass
class Reply:
    content: str


class FakeModel:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.prompts: list[object] = []
        self.version = "fake:voice"

    async def ainvoke(self, prompt: object) -> Reply:
        self.prompts.append(prompt)
        return Reply(self.responses.pop(0))


def claim(*, claim_id: str = "clm_1", text: str = "Built-up land covers 12.50 ha.") -> dict:
    return {
        "id": claim_id,
        "text": text,
        "isPrimary": True,
        "metrics": [{"label": "area", "value": 12.5, "precision": 2, "unit": "ha"}],
    }


async def test_grounded_speech_fills_model_placeholders_and_keeps_claim_ids() -> None:
    model = FakeModel("The mapped area is {m1}.")

    authored = await author_grounded_speech("How much built-up land?", [claim()], model)

    assert authored.text == "The mapped area is 12.50 ha."
    assert authored.claim_ids == ("clm_1",)
    assert authored.provisional is False
    assert authored.kind.value == "grounded"
    assert authored.model_version == "fake:voice"


async def test_invalid_numbers_are_retried_then_raise_typed_error_without_fallback() -> None:
    model = FakeModel("The mapped area is 99 hectares.", "Still 99 hectares.")

    with pytest.raises(SpeechGenerationError, match="numeral"):
        await author_grounded_speech("How much?", [claim()], model)

    assert len(model.prompts) == 2


async def test_refusal_must_survive_as_exact_ai_authored_text_and_is_non_interruptible() -> None:
    refusal = "The sensors disagree at 8 pixels, so AERIS cannot produce a fused conclusion."
    model = FakeModel(f"{refusal} Please review the separate observations.")

    authored = await author_grounded_speech(
        {"question": "Can they be fused?", "run_id": "run_1", "refusal": refusal}, [], model
    )

    assert authored.kind.value == "refusal"
    assert authored.text.startswith(refusal)
    assert authored.claim_ids == ()
    assert authored.interruptible is False


async def test_internal_identifiers_are_not_allowed_in_spoken_prose() -> None:
    model = FakeModel("The mapped area is {m1}; claim clm_1 is ready.", "The mapped area is {m1}; claim clm_1 is ready.")

    with pytest.raises(SpeechGenerationError, match="identifier"):
        await author_grounded_speech("What happened?", [claim()], model)


async def test_missing_refusal_or_claim_binding_is_rejected() -> None:
    model = FakeModel("There is no reliable result.", "There is still no reliable result.")

    with pytest.raises(SpeechGenerationError, match="refusal"):
        await author_grounded_speech(
            {"question": "Can they be fused?", "refusal": "The observations conflict."}, [], model
        )


async def test_progress_speech_cannot_introduce_a_measurement() -> None:
    model = FakeModel("The registration step is complete and the evidence is being checked.")

    authored = await author_progress_speech(
        {"id": "stp_1", "stageCode": "S9", "detail": "Checking registration residual"}, model
    )

    assert authored is not None
    assert authored.kind.value == "progress"
    assert authored.claim_ids == ()
    assert authored.provisional is False


async def test_provisional_speech_is_explicitly_ungrounded_and_supersedable() -> None:
    model = FakeModel("The run is still checking the evidence.")

    authored = await author_provisional_speech(
        {"question": "What is happening?", "context": "The active analysis has not completed.", "supersedesUtteranceId": "utt_1"},
        model,
    )

    assert authored.kind.value == "provisional"
    assert authored.provisional is True
    assert authored.claim_ids == ()
    assert authored.supersedes_utterance_id == "utt_1"


async def test_progress_numbers_are_rejected_and_provider_failures_are_typed() -> None:
    with pytest.raises(SpeechGenerationError, match="numeral"):
        await author_progress_speech({"detail": "Checking evidence"}, FakeModel("Step 2 is complete.", "Step 3 is complete."))

    class BrokenModel:
        async def ainvoke(self, prompt: object) -> Reply:
            raise RuntimeError("provider unavailable")

    with pytest.raises(SpeechGenerationError, match="provider"):
        await author_progress_speech({"detail": "Checking evidence"}, BrokenModel())


class FakeVoice:
    def synthesize(self, text: str, **kwargs: object):
        assert text == "hello"
        assert kwargs
        yield b"one!"
        yield b"two!"


class FakeOutput:
    def __init__(self, *, fail: bool = False) -> None:
        self.writes: list[bytes] = []
        self.fail = fail
        self.aborts = 0

    def write(self, data: bytes) -> None:
        if self.fail:
            raise OSError("speaker offline")
        self.writes.append(data)

    def abort(self) -> None:
        self.aborts += 1


async def test_piper_chunks_are_ordered_and_run_synthesis_off_loop() -> None:
    synthesizer = PiperSynthesizer(voice=FakeVoice(), speaker_id=0, length_scale=1.0)

    chunks = [chunk async for chunk in synthesizer.chunks("hello")]

    assert [chunk.samples for chunk in chunks] == [b"one!", b"two!"]
    assert all(chunk.sample_rate == VOICE_OUTPUT_SAMPLE_RATE_HERTZ for chunk in chunks)


async def test_player_interrupts_only_current_utterance_and_standby_suppresses_new_speech() -> None:
    output = FakeOutput()
    player = SpeechPlayer(output=output)
    first_started = asyncio.Event()

    async def first_chunks():
        yield AudioChunk(b"one!", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)
        first_started.set()
        await asyncio.sleep(0)
        yield AudioChunk(b"two!", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)

    first = AuthoredSpeech(text="one", claim_ids=("clm_1",))
    task = asyncio.create_task(player.speak(first, first_chunks()))
    await asyncio.wait_for(first_started.wait(), 1)
    await player.interrupt()
    await asyncio.wait_for(task, 1)

    await player.standby()
    await player.speak(AuthoredSpeech(text="quiet", claim_ids=("clm_1",)), _chunks("quiet"))
    assert output.writes == [b"one!"]
    await player.resume()


async def test_refusal_ignores_interrupt_until_playback_finishes() -> None:
    output = FakeOutput()
    player = SpeechPlayer(output=output)
    refusal = AuthoredSpeech(text="refusal", kind="refusal", interruptible=False)

    await player.speak(refusal, _chunks("refusal", "boundary"))
    await player.interrupt()

    assert output.writes == [b"refusal!", b"boundary"]


async def test_output_failures_are_typed_and_do_not_become_provider_fallbacks() -> None:
    player = SpeechPlayer(output=FakeOutput(fail=True))

    with pytest.raises(SpeechPlaybackError, match="speaker"):
        await player.speak(AuthoredSpeech(text="hello", claim_ids=("clm_1",)), _chunks("hello"))


async def _chunks(*values: str):
    for value in values:
        data = value.encode()
        yield AudioChunk(data if len(data) % 2 == 0 else data + b"!", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)
