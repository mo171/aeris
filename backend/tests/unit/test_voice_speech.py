"""Tests for evidence-bound voice prose and the local Piper playback boundary."""

import asyncio
import threading
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
from app.voice.synthesis import AudioChunk, PiperSynthesizer, SpeechPlaybackError, SpeechPlayer, SpeechSynthesisError


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


async def test_progress_prompt_json_serializes_structured_active_trace() -> None:
    model = FakeModel("The evidence stage is being checked.")

    await author_progress_speech({"detail": "Checking", "activeTrace": {"stage": "registration", "ready": True}}, model)

    prompt = model.prompts[0]
    assert '"activeTrace": {"ready": true, "stage": "registration"}' in str(prompt)
    assert "'activeTrace'" not in str(prompt)


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


async def test_grounded_authored_speech_requires_claim_ids() -> None:
    with pytest.raises(ValueError, match="claim ids"):
        AuthoredSpeech(text="A result", kind="grounded")


async def test_authored_utterance_id_is_the_only_event_identity() -> None:
    speech = AuthoredSpeech(text="A result", claim_ids=("clm_1",), utterance_id="utt_1")

    event = speech.to_event(run_id="run_1")

    assert event.utterance_id == "utt_1"
    with pytest.raises(TypeError):
        speech.to_event(run_id="run_1", utterance_id="stale")


async def test_unresolved_or_duplicate_placeholders_are_rejected_for_every_speech_kind() -> None:
    for kind, _kwargs in (("progress", {}), ("provisional", {"provisional": True})):
        model = FakeModel("The update is {m1}.", "The update is {m1}.")
        with pytest.raises(SpeechGenerationError, match="placeholder"):
            if kind == "progress":
                await author_progress_speech({"detail": "Checking evidence"}, model)
            else:
                await author_provisional_speech({"question": "What is happening?"}, model)

    model = FakeModel("The mapped area is {m1} {m1}.", "The mapped area is {m1} {m1}.")
    with pytest.raises(SpeechGenerationError, match="placeholder"):
        await author_grounded_speech("How much?", [claim()], model)


async def test_spelled_out_cardinal_and_ordinal_numbers_are_guarded() -> None:
    model = FakeModel("The mapped area is two hectares.", "The mapped area is second hectares.")

    with pytest.raises(SpeechGenerationError, match="number"):
        await author_grounded_speech("How much?", [claim()], model)


class FakeVoice:
    def synthesize(self, text: str, **kwargs: object):
        assert text == "hello"
        assert kwargs
        yield b"one!"
        yield b"two!"


class ProductionShapedAudio:
    def __init__(self, payload: bytes, sample_rate: int = VOICE_OUTPUT_SAMPLE_RATE_HERTZ) -> None:
        self.audio_int16_bytes = payload
        self.sample_rate = sample_rate
        self.sample_width = 2
        self.channel_count = 1


@pytest.mark.parametrize(
    "sample_width,sample_channels,sample_rate",
    [(4, 1, VOICE_OUTPUT_SAMPLE_RATE_HERTZ), (2, 2, VOICE_OUTPUT_SAMPLE_RATE_HERTZ), (2, 1, 16_000)],
)
async def test_piper_rejects_audio_outside_production_pcm_contract(
    sample_width: int, sample_channels: int, sample_rate: int
) -> None:
    item = ProductionShapedAudio(b"aa", sample_rate)
    item.sample_width = sample_width
    item.sample_channels = sample_channels

    with pytest.raises(SpeechSynthesisError, match="format"):
        PiperSynthesizer._audio_chunk(item)


class StreamingVoice:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.finished = asyncio.Event()
        self.closed = asyncio.Event()

    def synthesize(self, text: str, **kwargs: object):
        self.started.set()
        try:
            yield ProductionShapedAudio(b"aa")
            self.finished.set()
            yield ProductionShapedAudio(b"bb")
        finally:
            self.closed.set()


class FakeOutput:
    def __init__(self, *, fail: bool = False) -> None:
        self.writes: list[bytes] = []
        self.fail = fail
        self.aborts = 0
        self.closed = False

    def write(self, data: bytes) -> None:
        if self.fail:
            raise OSError("speaker offline")
        self.writes.append(data)

    def abort(self) -> None:
        self.aborts += 1

    def close(self) -> None:
        self.closed = True


class BlockingOutput(FakeOutput):
    def __init__(self) -> None:
        super().__init__()
        self.write_started = threading.Event()
        self.abort_called = threading.Event()
        self.release = threading.Event()

    def write(self, data: bytes) -> None:
        self.write_started.set()
        self.release.wait()
        super().write(data)

    def abort(self) -> None:
        self.abort_called.set()


async def test_piper_chunks_are_ordered_and_run_synthesis_off_loop() -> None:
    synthesizer = PiperSynthesizer(voice=FakeVoice(), speaker_id=0, length_scale=1.0)

    chunks = [chunk async for chunk in synthesizer.chunks("hello")]

    assert [chunk.samples for chunk in chunks] == [b"one!", b"two!"]
    assert all(chunk.sample_rate == VOICE_OUTPUT_SAMPLE_RATE_HERTZ for chunk in chunks)


async def test_piper_yields_production_audio_chunks_before_generator_finishes() -> None:
    voice = StreamingVoice()
    synthesizer = PiperSynthesizer(voice=voice, speaker_id=0, length_scale=1.0)
    iterator = synthesizer.chunks("hello").__aiter__()

    first = await iterator.__anext__()

    assert first.samples == b"aa"
    assert voice.finished.is_set() is False
    assert (await iterator.__anext__()).samples == b"bb"
    assert voice.finished.is_set() is True


async def test_closing_piper_stream_stops_requesting_more_generator_chunks() -> None:
    voice = StreamingVoice()
    synthesizer = PiperSynthesizer(voice=voice, speaker_id=0, length_scale=1.0)
    iterator = synthesizer.chunks("hello").__aiter__()

    assert (await iterator.__anext__()).samples == b"aa"
    await iterator.aclose()

    assert voice.finished.is_set() is False
    assert voice.closed.is_set() is True


async def test_player_interrupts_only_current_utterance_and_standby_suppresses_new_speech() -> None:
    output = FakeOutput()
    player = SpeechPlayer(output=output)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    chunks_closed = False

    async def first_chunks():
        nonlocal chunks_closed
        try:
            yield AudioChunk(b"one!", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)
            first_started.set()
            await release_first.wait()
            yield AudioChunk(b"two!", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)
        finally:
            chunks_closed = True

    first = AuthoredSpeech(text="one", claim_ids=("clm_1",), utterance_id="one")
    task = asyncio.create_task(player.speak(first, first_chunks()))
    await asyncio.wait_for(first_started.wait(), 1)
    await player.interrupt("one")
    release_first.set()
    await asyncio.wait_for(task, 1)
    assert chunks_closed is True

    await player.standby()
    await player.speak(AuthoredSpeech(text="quiet", claim_ids=("clm_1",)), _chunks("quiet"))
    assert output.writes == [b"one!"]
    await player.resume()


async def test_interrupted_one_shot_output_cannot_be_reused() -> None:
    output = FakeOutput()
    player = SpeechPlayer(output=output)
    started = asyncio.Event()
    release = asyncio.Event()

    async def chunks():
        yield AudioChunk(b"aa", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)
        started.set()
        await release.wait()

    first = AuthoredSpeech(text="first", claim_ids=("clm_1",), utterance_id="utt_1")
    task = asyncio.create_task(player.speak(first, chunks()))
    await started.wait()
    await player.interrupt("utt_1")
    release.set()
    await task

    with pytest.raises(SpeechPlaybackError, match="one-shot"):
        await player.speak(AuthoredSpeech(text="next", claim_ids=("clm_1",), utterance_id="utt_2"), _chunks("next"))


async def test_interrupt_aborts_then_awaits_inflight_write_before_closing_output() -> None:
    output = BlockingOutput()
    player = SpeechPlayer(output=output)
    utterance = AuthoredSpeech(text="first", claim_ids=("clm_1",), utterance_id="utt_1")
    task = asyncio.create_task(player.speak(utterance, _chunks("first")))
    await asyncio.to_thread(output.write_started.wait)

    interrupt_task = asyncio.create_task(player.interrupt("utt_1"))
    await asyncio.to_thread(output.abort_called.wait)
    assert output.closed is False
    output.release.set()
    await interrupt_task
    await task
    assert output.closed is True


async def test_refusal_ignores_interrupt_until_playback_finishes() -> None:
    output = FakeOutput()
    player = SpeechPlayer(output=output)
    refusal = AuthoredSpeech(text="refusal", kind="refusal", interruptible=False)

    await player.speak(refusal, _chunks("refusal", "boundary"))
    await player.interrupt()

    assert output.writes == [b"refusal!", b"boundary"]


async def test_stale_interrupt_id_cannot_abort_a_new_utterance_and_abort_restarts_output() -> None:
    output_instances = [FakeOutput(), FakeOutput()]
    outputs = list(output_instances)
    player = SpeechPlayer(output_factory=lambda: outputs.pop(0))
    first = AuthoredSpeech(text="first", claim_ids=("clm_1",), utterance_id="utt_1")
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def first_chunks():
        yield AudioChunk(b"aa", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)
        first_started.set()
        await release_first.wait()
        yield AudioChunk(b"bb", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)

    task = asyncio.create_task(player.speak(first, first_chunks()))
    await asyncio.wait_for(first_started.wait(), 1)
    await player.interrupt("utt_1")
    release_first.set()
    await task

    second = AuthoredSpeech(text="next", claim_ids=("clm_1",), utterance_id="utt_2")
    await player.interrupt("utt_1")
    await player.speak(second, _chunks("next"))

    assert output_instances[0].aborts == 1
    assert output_instances[0].closed is True
    assert output_instances[1].writes == [b"next"]


async def test_output_failures_are_typed_and_do_not_become_provider_fallbacks() -> None:
    player = SpeechPlayer(output=FakeOutput(fail=True))

    with pytest.raises(SpeechPlaybackError, match="speaker"):
        await player.speak(AuthoredSpeech(text="hello", claim_ids=("clm_1",)), _chunks("hello"))


async def _chunks(*values: str):
    for value in values:
        data = value.encode()
        yield AudioChunk(data if len(data) % 2 == 0 else data + b"!", VOICE_OUTPUT_SAMPLE_RATE_HERTZ)
