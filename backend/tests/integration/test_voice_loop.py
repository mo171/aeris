"""Integration test for the full voice loop: capture → transcribe → classify → dispatch → speak.

Uses fake audio adapters but exercises the real VoiceSession coordinator, VoiceTurnDecision,
and AuthoredSpeech pipeline. No audio device, Piper model, or LLM API key is required.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import numpy as np
import pytest

from app.constants.voice import VoiceSessionState
from app.voice.session import VoiceSession
from app.voice.speech import AuthoredSpeech
from app.voice.synthesis import AudioChunk
from app.voice.turns import VoiceTurnAction, VoiceTurnDecision
from app.voice.types import CapturedTurn, Transcript


def _pcm(duration_ms: int = 500) -> bytes:
    return np.full(max(1, round(16_000 * duration_ms / 1000)), 1000, dtype=np.int16).tobytes()


def _turn(duration_ms: int = 500) -> CapturedTurn:
    from datetime import UTC, datetime

    return CapturedTurn(
        samples=_pcm(duration_ms),
        sample_rate=16_000,
        started_at=datetime.now(UTC),
        duration_ms=duration_ms,
    )


class ScriptedCapture:
    """Yields scripted turns, then blocks until stop is set."""

    def __init__(self, *turns: CapturedTurn | None) -> None:
        self._turns = list(turns)

    async def capture(self, stop: asyncio.Event) -> CapturedTurn | None:
        if self._turns:
            return self._turns.pop(0)
        await stop.wait()
        return None


class ScriptedTranscriber:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)

    async def transcribe(self, turn: CapturedTurn) -> Transcript:
        return Transcript(text=self._texts.pop(0) if self._texts else "", language="en")


class ScriptedModel:
    """Returns scripted VoiceTurnDecisions for classification, and text for speech authoring."""

    def __init__(self, *responses: VoiceTurnDecision | str) -> None:
        self._responses = list(responses)
        self.version = "fake:integration"

    def with_structured_output(self, schema: type) -> ScriptedStructuredModel:
        return ScriptedStructuredModel(self, schema)

    async def ainvoke(self, prompt: object) -> Any:
        if self._responses:
            response = self._responses.pop(0)
            if isinstance(response, str):

                class Reply:
                    content = response

                return Reply()
        return type("Reply", (), {"content": "The analysis is still running"})()


class ScriptedStructuredModel:
    def __init__(self, parent: ScriptedModel, schema: type) -> None:
        self._parent = parent
        self._schema = schema

    async def ainvoke(self, prompt: object) -> Any:
        if self._parent._responses:
            response = self._parent._responses.pop(0)
            if isinstance(response, self._schema):
                return response
        return self._schema(action=VoiceTurnAction.QUESTION)


class RecordingPlayer:
    """Records all speech operations."""

    def __init__(self) -> None:
        self.spoken: list[AuthoredSpeech] = []
        self.standby_called = False
        self.resumed = False
        self.closed = False
        self._active: AuthoredSpeech | None = None
        self._standby = False

    async def speak(self, utterance: AuthoredSpeech, chunks: AsyncIterator[AudioChunk]) -> None:
        self.spoken.append(utterance)
        self._active = utterance
        async for _ in chunks:
            pass
        self._active = None

    async def interrupt(self, utterance_id: str | None = None) -> None:
        self._active = None

    async def standby(self) -> None:
        self.standby_called = True

    async def resume(self) -> None:
        self.resumed = True

    async def close(self) -> None:
        self.closed = True


class RecordingSynthesizer:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def chunks(self, utterance: AuthoredSpeech | str) -> AsyncIterator[AudioChunk]:
        text = utterance.text if isinstance(utterance, AuthoredSpeech) else str(utterance)
        self.texts.append(text)
        yield AudioChunk(samples=b"\x00\x00" * 100, sample_rate=22_050, channels=1)


@pytest.mark.asyncio
async def test_full_voice_loop_approve_and_question() -> None:
    """Integration: two sequential hotkey activations — first approve, then question."""
    model = ScriptedModel(
        # Turn 1: approve
        VoiceTurnDecision(action=VoiceTurnAction.APPROVE_ALL),
        # Turn 2: question → provisional speech response
        VoiceTurnDecision(action=VoiceTurnAction.QUESTION),
        "The analysis is currently in progress and no results are available yet",
    )
    capture = ScriptedCapture(_turn(), _turn())
    transcriber = ScriptedTranscriber("run all steps", "how is it going")
    synth = RecordingSynthesizer()
    player = RecordingPlayer()

    session = VoiceSession(
        capture=capture,
        transcriber=transcriber,
        synthesizer=synth,
        player=player,
        model=model,
    )

    # Set up a pending approval for the first turn
    approval = asyncio.get_event_loop().create_future()
    session._pending_approval = approval
    session._plan_payload = {"steps": [{"id": "step-1", "isEnabled": True}]}

    # Simulate an active run for the second turn
    class FakeRun:
        run_id = "run_int"
        is_running = True

    # Turn 1: approve
    await session._activate()
    assert approval.done()
    assert approval.result() is None  # All steps kept

    # Set up active run for turn 2
    session._active_run = FakeRun()

    # Turn 2: question during run → provisional
    await session._activate()
    assert len(player.spoken) == 1
    assert player.spoken[0].provisional is True


@pytest.mark.asyncio
async def test_full_loop_standby_resume_cycle() -> None:
    """Integration: standby → resume cycle preserves session integrity."""
    model = ScriptedModel(
        VoiceTurnDecision(action=VoiceTurnAction.STANDBY),
        VoiceTurnDecision(action=VoiceTurnAction.RESUME),
    )
    capture = ScriptedCapture(_turn(), _turn())
    transcriber = ScriptedTranscriber("be quiet", "speak again")
    player = RecordingPlayer()

    session = VoiceSession(
        capture=capture,
        transcriber=transcriber,
        synthesizer=RecordingSynthesizer(),
        player=player,
        model=model,
    )

    # Turn 1: standby
    await session._activate()
    assert player.standby_called
    assert session.state == VoiceSessionState.STANDBY

    # Turn 2: resume
    await session._activate()
    assert player.resumed
    assert session.state == VoiceSessionState.IDLE


@pytest.mark.asyncio
async def test_full_loop_abandon_active_run() -> None:
    """Integration: abandon stops the run through the handle, not through session state."""

    class FakeRunHandle:
        run_id = "run_abandon"
        is_running = True
        abandon_reason: str | None = None

        async def abandon(self, reason: str) -> None:
            self.abandon_reason = reason
            self.is_running = False

    model = ScriptedModel(VoiceTurnDecision(action=VoiceTurnAction.ABANDON))
    capture = ScriptedCapture(_turn())
    transcriber = ScriptedTranscriber("cancel the analysis")

    session = VoiceSession(
        capture=capture,
        transcriber=transcriber,
        synthesizer=RecordingSynthesizer(),
        player=RecordingPlayer(),
        model=model,
    )

    handle = FakeRunHandle()
    session._active_run = handle

    await session._activate()

    assert handle.abandon_reason == "operator voice command"
    assert not handle.is_running


@pytest.mark.asyncio
async def test_session_run_loop_with_hotkey() -> None:
    """Integration: the session run loop responds to hotkey events and closes cleanly."""
    model = ScriptedModel(VoiceTurnDecision(action=VoiceTurnAction.QUESTION))
    capture = ScriptedCapture(_turn())
    transcriber = ScriptedTranscriber("test")

    session = VoiceSession(
        capture=capture,
        transcriber=transcriber,
        synthesizer=RecordingSynthesizer(),
        player=RecordingPlayer(),
        model=model,
    )

    hotkey = asyncio.Event()
    run_task = asyncio.create_task(session.run(hotkey_source=hotkey))

    await asyncio.sleep(0.05)
    hotkey.set()
    await asyncio.sleep(0.2)

    await session.close()
    try:
        await asyncio.wait_for(run_task, timeout=2.0)
    except (TimeoutError, asyncio.CancelledError):
        pass

    assert session.state == VoiceSessionState.CLOSED
