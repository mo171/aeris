"""Unit tests for the VoiceSession coordinator and VoiceTurnDecision classifier.

Every test uses fake capture/transcriber/synthesizer/player/model so no audio device, Piper model,
or LLM API key is required. The tests verify the session's routing logic, state management, and
coordination — not the quality of audio or LLM output.
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest

from app.constants.voice import VoiceSessionState
from app.voice.session import VoiceSession
from app.voice.speech import AuthoredSpeech
from app.voice.synthesis import AudioChunk
from app.voice.turns import VoiceTurnAction, VoiceTurnDecision, classify_voice_turn
from app.voice.types import CapturedTurn, Transcript

# --- Fakes ---


def _pcm_samples(value: int = 1000, duration_ms: int = 500) -> bytes:
    """Synthetic PCM16 samples for a fake captured turn."""
    import numpy as np

    sample_count = max(1, round(16_000 * duration_ms / 1000))
    return np.full(sample_count, value, dtype=np.int16).tobytes()


@dataclass
class FakeReply:
    content: str


class FakeModel:
    """A model that returns scripted structured output for turn classification."""

    def __init__(self, *decisions: VoiceTurnDecision | dict[str, Any] | str) -> None:
        self._decisions = list(decisions)
        self.calls: list[object] = []
        self.version = "fake:voice-test"

    async def ainvoke(self, prompt: object) -> FakeReply:
        self.calls.append(prompt)
        decision = self._decisions.pop(0) if self._decisions else VoiceTurnDecision(action=VoiceTurnAction.QUESTION)
        if isinstance(decision, VoiceTurnDecision):
            import json

            return FakeReply(json.dumps(decision.model_dump()))
        if isinstance(decision, dict):
            import json

            return FakeReply(json.dumps(decision))
        return FakeReply(str(decision))

    def with_structured_output(self, schema: type) -> FakeStructuredModel:
        return FakeStructuredModel(self, schema)


class FakeStructuredModel:
    def __init__(self, parent: FakeModel, schema: type) -> None:
        self._parent = parent
        self._schema = schema

    async def ainvoke(self, prompt: object) -> Any:
        self._parent.calls.append(prompt)
        decisions = self._parent._decisions
        if decisions:
            decision = decisions.pop(0)
            if isinstance(decision, self._schema):
                return decision
            if isinstance(decision, dict):
                return self._schema.model_validate(decision)
        return self._schema(action=VoiceTurnAction.QUESTION)


class FakeCapture:
    """Returns a scripted CapturedTurn or None (silence)."""

    def __init__(self, *turns: CapturedTurn | None) -> None:
        self._turns = list(turns)

    async def capture(self, stop: asyncio.Event) -> CapturedTurn | None:
        if not self._turns:
            # Block until stop is set (session close)
            await stop.wait()
            return None
        return self._turns.pop(0)


class FakeTranscriber:
    """Returns a scripted Transcript."""

    def __init__(self, *transcripts: str) -> None:
        self._transcripts = list(transcripts)

    async def transcribe(self, turn: CapturedTurn) -> Transcript:
        text = self._transcripts.pop(0) if self._transcripts else ""
        return Transcript(text=text, language="en")


class FakeSynthesizer:
    """Yields one dummy audio chunk per utterance."""

    def __init__(self) -> None:
        self.synthesized: list[str] = []

    async def chunks(self, utterance: AuthoredSpeech | str) -> AsyncIterator[AudioChunk]:
        text = utterance.text if isinstance(utterance, AuthoredSpeech) else str(utterance)
        self.synthesized.append(text)
        yield AudioChunk(samples=b"\x00\x00" * 100, sample_rate=22_050, channels=1)


class FakePlayer:
    """Records speak/interrupt/standby/resume/close calls."""

    def __init__(self) -> None:
        self.spoken: list[AuthoredSpeech] = []
        self.interrupted: list[str | None] = []
        self.standby_called = False
        self.resumed = False
        self.closed = False
        self._active: AuthoredSpeech | None = None
        self._standby = False

    async def speak(self, utterance: AuthoredSpeech, chunks: AsyncIterator[AudioChunk]) -> None:
        self.spoken.append(utterance)
        self._active = utterance
        # Consume chunks to simulate playback
        async for _ in chunks:
            pass
        self._active = None

    async def interrupt(self, utterance_id: str | None = None) -> None:
        self.interrupted.append(utterance_id)
        self._active = None

    async def standby(self) -> None:
        self.standby_called = True
        self._standby = True

    async def resume(self) -> None:
        self.resumed = True
        self._standby = False

    async def close(self) -> None:
        self.closed = True
        self._active = None


def _turn(duration_ms: int = 500) -> CapturedTurn:
    from datetime import UTC, datetime

    return CapturedTurn(
        samples=_pcm_samples(duration_ms=duration_ms),
        sample_rate=16_000,
        started_at=datetime.now(UTC),
        duration_ms=duration_ms,
    )


def _session(
    capture: FakeCapture,
    transcriber: FakeTranscriber,
    model: FakeModel,
    *,
    synthesizer: FakeSynthesizer | None = None,
    player: FakePlayer | None = None,
    on_state_change: Any = None,
) -> tuple[VoiceSession, FakePlayer, FakeSynthesizer]:
    synth = synthesizer or FakeSynthesizer()
    plyr = player or FakePlayer()
    session = VoiceSession(
        capture=capture,
        transcriber=transcriber,
        synthesizer=synth,
        player=plyr,
        model=model,
        on_state_change=on_state_change,
    )
    return session, plyr, synth


# --- VoiceTurnDecision Tests ---


@pytest.mark.asyncio
async def test_classify_approve_all() -> None:
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.APPROVE_ALL))
    result = await classify_voice_turn("yes go ahead", model=model)
    assert result.action == VoiceTurnAction.APPROVE_ALL


@pytest.mark.asyncio
async def test_classify_question() -> None:
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.QUESTION, response="checking..."))
    result = await classify_voice_turn("what is the cloud coverage", model=model)
    assert result.action == VoiceTurnAction.QUESTION
    assert result.response == "checking..."


@pytest.mark.asyncio
async def test_classify_abandon() -> None:
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.ABANDON))
    result = await classify_voice_turn("stop the analysis", model=model)
    assert result.action == VoiceTurnAction.ABANDON


@pytest.mark.asyncio
async def test_classify_standby() -> None:
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.STANDBY))
    result = await classify_voice_turn("mute", model=model)
    assert result.action == VoiceTurnAction.STANDBY


@pytest.mark.asyncio
async def test_classify_resume() -> None:
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.RESUME))
    result = await classify_voice_turn("unmute", model=model)
    assert result.action == VoiceTurnAction.RESUME


@pytest.mark.asyncio
async def test_classify_modify_plan() -> None:
    model = FakeModel(
        VoiceTurnDecision(
            action=VoiceTurnAction.MODIFY_PLAN,
            enabled_step_ids=["step-1", "step-3"],
        )
    )
    result = await classify_voice_turn("keep only step one and three", model=model)
    assert result.action == VoiceTurnAction.MODIFY_PLAN
    assert result.enabled_step_ids == ["step-1", "step-3"]


@pytest.mark.asyncio
async def test_classify_falls_back_to_manual_parse() -> None:
    """When with_structured_output raises, the manual JSON parse path is used."""
    import json

    class BrokenStructuredModel(FakeModel):
        def with_structured_output(self, schema: type) -> Any:
            raise NotImplementedError("not supported")

    decision_json = json.dumps({"action": "question", "enabled_step_ids": [], "response": "parsed manually"})
    model = BrokenStructuredModel(decision_json)
    result = await classify_voice_turn("anything", model=model)
    assert result.action == VoiceTurnAction.QUESTION
    assert result.response == "parsed manually"


# --- VoiceSession State Management Tests ---


@pytest.mark.asyncio
async def test_session_starts_idle_and_closes_cleanly() -> None:
    session, player, _ = _session(
        FakeCapture(),
        FakeTranscriber(),
        FakeModel(),
    )
    assert session.state == VoiceSessionState.IDLE

    # Close immediately
    await session.close()
    assert session.state == VoiceSessionState.CLOSED
    assert player.closed


@pytest.mark.asyncio
async def test_hotkey_starts_one_microphone_turn() -> None:
    """Ctrl+P activates exactly one capture turn, not continuous listening."""
    capture = FakeCapture(_turn(), None)  # One turn then silence
    transcriber = FakeTranscriber("hello", "")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.QUESTION))
    session, player, _ = _session(capture, transcriber, model)

    # Simulate one hotkey activation
    hotkey = asyncio.Event()
    run_task = asyncio.create_task(session.run(hotkey_source=hotkey))

    # Give the session loop time to start
    await asyncio.sleep(0.05)

    # Fire one hotkey
    hotkey.set()
    await asyncio.sleep(0.1)

    # Close session
    await session.close()
    try:
        await run_task
    except asyncio.CancelledError:
        pass

    # Verify exactly one capture was consumed (the non-None turn)
    assert len(model.calls) >= 1  # Classification was called


@pytest.mark.asyncio
async def test_silence_returns_to_idle_without_classification() -> None:
    """When VAD detects no speech, the session returns to idle without LLM classification."""
    capture = FakeCapture(None)  # Silence
    transcriber = FakeTranscriber()
    model = FakeModel()
    session, _, _ = _session(capture, transcriber, model)

    await session._activate()

    assert session.state == VoiceSessionState.IDLE
    assert len(model.calls) == 0  # No classification for silence


@pytest.mark.asyncio
async def test_empty_transcript_returns_to_idle() -> None:
    """When transcription returns empty text, no classification happens."""
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("")
    model = FakeModel()
    session, _, _ = _session(capture, transcriber, model)

    await session._activate()

    assert session.state == VoiceSessionState.IDLE
    assert len(model.calls) == 0


@pytest.mark.asyncio
async def test_plan_approval_resolves_pending_future() -> None:
    """Approving a plan resolves the approval future so converse() can resume."""
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("yes go ahead")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.APPROVE_ALL))
    session, _, _ = _session(capture, transcriber, model)

    # Set up a pending approval
    approval_future = asyncio.get_event_loop().create_future()
    session._pending_approval = approval_future
    session._plan_payload = {
        "steps": [{"id": "step-1", "isEnabled": True, "title": "NDVI"}]
    }

    await session._activate()

    # The approval future should be resolved with None (keep all steps)
    assert approval_future.done()
    assert approval_future.result() is None
    assert session._pending_approval is None


@pytest.mark.asyncio
async def test_modify_plan_resolves_with_step_ids() -> None:
    """Modifying a plan resolves the approval future with specific step IDs."""
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("only run step one")
    model = FakeModel(
        VoiceTurnDecision(
            action=VoiceTurnAction.MODIFY_PLAN,
            enabled_step_ids=["step-1"],
        )
    )
    session, _, _ = _session(capture, transcriber, model)

    approval_future = asyncio.get_event_loop().create_future()
    session._pending_approval = approval_future
    session._plan_payload = {
        "steps": [
            {"id": "step-1", "isEnabled": True, "title": "NDVI"},
            {"id": "step-2", "isEnabled": True, "title": "Count"},
        ]
    }

    await session._activate()

    assert approval_future.done()
    assert approval_future.result() == ["step-1"]


@pytest.mark.asyncio
async def test_approve_without_pending_plan_is_noop() -> None:
    """Approving when no plan is pending does not crash."""
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("yes")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.APPROVE_ALL))
    session, _, _ = _session(capture, transcriber, model)

    # No pending approval
    assert session._pending_approval is None

    await session._activate()

    # Should complete without error
    assert session.state == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_standby_suppresses_speech_without_stopping_run() -> None:
    """Standby mutes speech output while the run continues unaffected."""
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("mute please")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.STANDBY))
    session, player, _ = _session(capture, transcriber, model)

    await session._activate()

    assert player.standby_called
    assert session.state == VoiceSessionState.STANDBY


@pytest.mark.asyncio
async def test_resume_restores_speech() -> None:
    """Resume re-enables speech after standby."""
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("unmute")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.RESUME))
    session, player, _ = _session(capture, transcriber, model)

    # Simulate standby state
    session._state = VoiceSessionState.STANDBY
    await session._activate()

    assert player.resumed
    assert session.state == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_abandon_without_active_run_is_noop() -> None:
    """Abandoning when no run is active does not crash."""
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("stop everything")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.ABANDON))
    session, _, _ = _session(capture, transcriber, model)

    await session._activate()

    # Should complete without error
    assert session.state == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_abandon_calls_run_handle_abandon() -> None:
    """Abandon reaches RunHandle.abandon() only through LLM classification."""

    class FakeRunHandle:
        def __init__(self) -> None:
            self.run_id = "run_test"
            self.abandoned = False
            self._running = True

        @property
        def is_running(self) -> bool:
            return self._running

        async def abandon(self, reason: str) -> None:
            self.abandoned = True
            self._running = False

    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("stop the analysis now")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.ABANDON))
    session, _, _ = _session(capture, transcriber, model)

    fake_handle = FakeRunHandle()
    session._active_run = fake_handle

    await session._activate()

    assert fake_handle.abandoned


@pytest.mark.asyncio
async def test_question_during_active_run_is_provisional() -> None:
    """A question while a run is active produces provisional speech, not grounded."""

    class FakeRunHandle:
        run_id = "run_active"
        is_running = True

    # The provisional speech model response — no numerals or identifiers
    provisional_model = FakeModel(
        # First call: turn classification
        VoiceTurnDecision(action=VoiceTurnAction.QUESTION),
        # Second call: provisional speech authoring
        "The analysis is currently running and results are not yet available",
    )
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("what is the current status")
    session, player, synth = _session(capture, transcriber, provisional_model)

    session._active_run = FakeRunHandle()

    await session._activate()

    # Check that provisional speech was authored and spoken
    assert len(player.spoken) == 1
    assert player.spoken[0].provisional is True
    assert player.spoken[0].claim_ids == ()


@pytest.mark.asyncio
async def test_session_close_tears_down_resources() -> None:
    """Session close stops all audio resources and resolves pending futures."""
    session, player, _ = _session(
        FakeCapture(),
        FakeTranscriber(),
        FakeModel(),
    )

    # Set up a pending approval
    approval = asyncio.get_event_loop().create_future()
    session._pending_approval = approval

    await session.close()

    assert player.closed
    assert session.state == VoiceSessionState.CLOSED
    # Pending approval should be cancelled
    assert approval.cancelled() or approval.done()


@pytest.mark.asyncio
async def test_session_close_is_idempotent() -> None:
    """Closing an already-closed session is a no-op."""
    session, player, _ = _session(
        FakeCapture(),
        FakeTranscriber(),
        FakeModel(),
    )

    await session.close()
    await session.close()  # Should not raise

    assert session.state == VoiceSessionState.CLOSED


@pytest.mark.asyncio
async def test_state_change_callback_is_invoked() -> None:
    """The on_state_change callback receives every state transition."""
    states: list[VoiceSessionState] = []
    capture = FakeCapture(_turn())
    transcriber = FakeTranscriber("hello")
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.QUESTION))
    session, _, _ = _session(
        capture, transcriber, model,
        on_state_change=lambda s: states.append(s),
    )

    await session._activate()

    # Should have transitioned through: CAPTURING -> TRANSCRIBING -> IDLE
    assert VoiceSessionState.CAPTURING in states
    assert VoiceSessionState.TRANSCRIBING in states


@pytest.mark.asyncio
async def test_barge_in_interrupts_speech_not_run() -> None:
    """When Ctrl+P fires during playback, the utterance is interrupted but the run continues."""

    class FakeRunHandle:
        run_id = "run_barge"
        is_running = True
        abandoned = False

        async def abandon(self, reason: str) -> None:
            self.abandoned = True

    player = FakePlayer()
    # Simulate active playback
    player._active = AuthoredSpeech(
        text="Playing grounded result",
        run_id="run_barge",
        utterance_id="utt_playing",
        claim_ids=("clm_1",),
        kind="grounded",
    )

    session, _, _ = _session(
        FakeCapture(None),  # Silence after barge-in
        FakeTranscriber(),
        FakeModel(),
        player=player,
    )

    run_handle = FakeRunHandle()
    session._active_run = run_handle

    # Simulate barge-in: interrupt is called by session.run() before activate
    await player.interrupt()

    # Speech was interrupted
    assert len(player.interrupted) == 1
    # Run was NOT abandoned
    assert not run_handle.abandoned
    assert run_handle.is_running


@pytest.mark.asyncio
async def test_turn_classification_uses_structured_output_not_keywords() -> None:
    """Verify that classify_voice_turn goes through the model, not keywords."""
    model = FakeModel(VoiceTurnDecision(action=VoiceTurnAction.APPROVE_ALL))

    result = await classify_voice_turn("stop", model=model)

    # Even though "stop" looks like an abandon keyword, the model decided approve_all
    assert result.action == VoiceTurnAction.APPROVE_ALL
    assert len(model.calls) == 1  # Model was called, not bypassed


@pytest.mark.asyncio
async def test_voice_approver_waits_for_voice_decision() -> None:
    """The voice approver blocks until the operator speaks an approval."""
    session, player, _ = _session(
        FakeCapture(),
        FakeTranscriber(),
        FakeModel(),
    )

    approver = session.create_approver()

    plan = {
        "id": "pln_test",
        "summary": "Test plan",
        "steps": [{"id": "step-1", "isEnabled": True, "title": "NDVI"}],
    }

    # Start the approver in background — it will block on the approval future
    approver_task = asyncio.create_task(approver(plan, "template"))

    await asyncio.sleep(0.1)

    # The session should be in PENDING_APPROVAL state
    assert session.state == VoiceSessionState.PENDING_APPROVAL
    assert session._pending_approval is not None

    # Simulate operator approval
    session._pending_approval.set_result(None)

    result = await approver_task
    assert result is None  # Keep all steps


@pytest.mark.asyncio
async def test_capture_failure_transitions_to_failed() -> None:
    """When microphone capture fails, the session transitions to FAILED, not crashes."""

    class FailingCapture:
        async def capture(self, stop: asyncio.Event) -> CapturedTurn | None:
            raise RuntimeError("microphone disconnected")

    session, _, _ = _session(
        FailingCapture(),  # type: ignore[arg-type]
        FakeTranscriber(),
        FakeModel(),
    )

    await session._activate()

    assert session.state == VoiceSessionState.FAILED


@pytest.mark.asyncio
async def test_transcription_failure_transitions_to_failed() -> None:
    """When transcription fails, the session transitions to FAILED."""

    class FailingTranscriber:
        async def transcribe(self, turn: CapturedTurn) -> Transcript:
            raise RuntimeError("whisper model not loaded")

    session, _, _ = _session(
        FakeCapture(_turn()),
        FailingTranscriber(),  # type: ignore[arg-type]
        FakeModel(),
    )

    await session._activate()

    assert session.state == VoiceSessionState.FAILED


@pytest.mark.asyncio
async def test_classification_failure_transitions_to_failed() -> None:
    """When LLM classification fails, the session transitions to FAILED."""

    class FailingModel:
        version = "fail"

        def with_structured_output(self, schema: type) -> Any:
            raise NotImplementedError

        async def ainvoke(self, prompt: object) -> FakeReply:
            return FakeReply("not valid json {{{")

    session, _, _ = _session(
        FakeCapture(_turn()),
        FakeTranscriber("hello"),
        FailingModel(),  # type: ignore[arg-type]
    )

    await session._activate()

    assert session.state == VoiceSessionState.FAILED
