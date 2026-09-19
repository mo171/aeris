"""Hotkey-activated terminal voice session coordinating capture, classification, and speech.

``VoiceSession`` ties together the adapters built in Tasks 3-6 with the agent graph from ``agents/run.py``.
It never invokes the graph directly; it drives ``converse()`` through an async approver callback and observes
run events through the fanout's consumer interface.

Design invariants:
- ``Ctrl+P`` activates one microphone turn; the microphone is never always-on.
- Barge-in (``Ctrl+P`` during playback) interrupts the active utterance, never the scientific run.
- Turn classification uses structured LLM output exclusively; no keyword/regex shortcuts.
- Provisional speech during an active run has ``claim_ids=[]`` and ``provisional=True``.
- Grounded speech supersedes provisional speech when the run completes.
- ``RunHandle.abandon()`` is reachable only through an LLM-classified explicit abandon action.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.constants.voice import VoiceSessionState, SpeechKind
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.voice.speech import (
    AuthoredSpeech,
    SpeechRequest,
    author_grounded_speech,
    author_progress_speech,
    author_provisional_speech,
)
from app.voice.turns import VoiceTurnAction, VoiceTurnDecision, classify_voice_turn
from app.voice.types import Transcript

logger = logging.getLogger(__name__)


class VoiceSession:
    """Coordinate one terminal voice conversation with capture, classification, and speech.

    The session owns the audio lifecycle but delegates scientific execution to ``converse()``.
    Event observation is injected through the fanout consumer interface so graph state is never
    stored on this object or in checkpoint state.
    """

    def __init__(
        self,
        *,
        capture: Any,
        transcriber: Any,
        synthesizer: Any,
        player: Any,
        model: Any = None,
        on_state_change: Callable[[VoiceSessionState], Any] | None = None,
        on_transcript: Callable[[Transcript], Any] | None = None,
    ) -> None:
        self._capture = capture
        self._transcriber = transcriber
        self._synthesizer = synthesizer
        self._player = player
        self._model = model
        self._on_state_change = on_state_change
        self._on_transcript = on_transcript

        self._state = VoiceSessionState.IDLE
        self._stop_capture = asyncio.Event()
        self._session_closed = asyncio.Event()
        self._hotkey_event = asyncio.Event()

        # Active run tracking — never stored in graph checkpoint
        self._active_run: Any = None  # RunHandle when a run is in flight
        self._pending_approval: asyncio.Future[list[str] | None] | None = None
        self._plan_payload: dict[str, Any] | None = None
        self._plan_source: str = "template"
        self._last_provisional_id: str | None = None
        self._run_task: asyncio.Task[Any] | None = None

    @property
    def state(self) -> VoiceSessionState:
        return self._state

    def _set_state(self, state: VoiceSessionState) -> None:
        if self._state == state:
            return
        self._state = state
        if self._on_state_change is not None:
            try:
                result = self._on_state_change(state)
                if asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception:  # noqa: BLE001 — state callbacks must not kill the session
                logger.debug("state change callback failed", exc_info=True)

    async def run(self, *, hotkey_source: asyncio.Event | None = None) -> None:
        """Main session loop. Waits for hotkey activations until closed.

        ``hotkey_source`` is the event that fires on each ``Ctrl+P`` press. When ``None``, the
        session creates its own event and the caller is responsible for signalling it (used by
        the prompt-toolkit integration in ``cli/voice.py``).
        """
        hotkey = hotkey_source or self._hotkey_event
        self._set_state(VoiceSessionState.IDLE)
        try:
            while not self._session_closed.is_set():
                # Wait for either a hotkey press or session close
                hotkey_task = asyncio.create_task(hotkey.wait())
                close_task = asyncio.create_task(self._session_closed.wait())
                done, _ = await asyncio.wait(
                    (hotkey_task, close_task), return_when=asyncio.FIRST_COMPLETED
                )
                # Clean up the loser
                for task in (hotkey_task, close_task):
                    if task not in done:
                        task.cancel()
                        try:
                            await task
                        except (asyncio.CancelledError, Exception):
                            pass

                if self._session_closed.is_set():
                    break

                hotkey.clear()

                # If speech is playing, interrupt it first (barge-in), then capture
                if self._player._active is not None:
                    await self._player.interrupt()

                await self._activate()
        except asyncio.CancelledError:
            pass
        finally:
            await self.close()

    async def _activate(self) -> None:
        """Execute one complete voice turn: capture → transcribe → classify → dispatch."""
        # Capture
        self._set_state(VoiceSessionState.CAPTURING)
        self._stop_capture.clear()
        try:
            turn = await self._capture.capture(self._stop_capture)
        except Exception as error:  # noqa: BLE001 — device errors are reported, not fatal
            logger.warning("voice capture failed: %s", error)
            self._set_state(VoiceSessionState.FAILED)
            return

        if turn is None:
            self._set_state(VoiceSessionState.IDLE)
            return

        # Transcribe
        self._set_state(VoiceSessionState.TRANSCRIBING)
        try:
            transcript = await self._transcriber.transcribe(turn)
        except Exception as error:  # noqa: BLE001 — transcription errors are reported, not fatal
            logger.warning("voice transcription failed: %s", error)
            self._set_state(VoiceSessionState.FAILED)
            return

        if self._on_transcript is not None:
            try:
                result = self._on_transcript(transcript)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001 — transcript callback errors must not kill the session
                logger.debug("transcript callback failed", exc_info=True)

        if not transcript.text.strip():
            self._set_state(VoiceSessionState.IDLE)
            return

        logger.info("operator said: %r", transcript.text)

        # Classify the turn through structured LLM output
        context = self._session_context()
        try:
            decision = await classify_voice_turn(
                transcript.text, session_context=context, model=self._model
            )
        except Exception as error:  # noqa: BLE001 — classification errors are reported, not fatal
            logger.warning("voice-turn classification failed: %s", error)
            self._set_state(VoiceSessionState.FAILED)
            return

        logger.info("classified as: %s", decision.action)

        # Dispatch the classified action
        await self._dispatch(decision, transcript.text)

    async def _dispatch(self, decision: VoiceTurnDecision, transcript: str) -> None:
        """Route a classified turn to its handler. Every branch is an LLM decision."""
        action = decision.action

        if action in (VoiceTurnAction.APPROVE_ALL, VoiceTurnAction.APPROVE_PLAN):
            await self._handle_approve(enabled_step_ids=None)
        elif action == VoiceTurnAction.MODIFY_PLAN:
            await self._handle_approve(enabled_step_ids=decision.enabled_step_ids or None)
        elif action == VoiceTurnAction.QUESTION:
            await self._handle_question(transcript)
        elif action == VoiceTurnAction.ABANDON:
            await self._handle_abandon()
        elif action == VoiceTurnAction.STANDBY:
            await self._handle_standby()
        elif action == VoiceTurnAction.RESUME:
            await self._handle_resume()
        else:
            logger.warning("unhandled voice-turn action: %s", action)

        # Return to idle unless the handler changed state
        if self._state not in (
            VoiceSessionState.RUNNING,
            VoiceSessionState.STANDBY,
            VoiceSessionState.CLOSED,
        ):
            self._set_state(VoiceSessionState.IDLE)

    async def _handle_approve(self, *, enabled_step_ids: list[str] | None) -> None:
        """Resume a paused LangGraph with the operator's approval decision."""
        if self._pending_approval is None:
            logger.info("no plan pending approval; ignoring approve action")
            return
        try:
            self._pending_approval.set_result(enabled_step_ids)
        except asyncio.InvalidStateError:
            logger.debug("approval future already resolved")
            return
        self._pending_approval = None
        self._plan_payload = None
        self._set_state(VoiceSessionState.RUNNING)

    async def _handle_question(self, transcript: str) -> None:
        """Answer a question. Provisional if a run is active; otherwise direct."""
        if self._active_run is not None and self._active_run.is_running:
            # Active run — give a provisional response without touching the graph
            utterance_id = new_identifier(IdentifierPrefix.UTTERANCE)
            request = SpeechRequest(
                run_id=self._active_run.run_id,
                utterance_id=utterance_id,
                question=transcript,
                context=self._run_context(),
            )
            try:
                authored = await author_provisional_speech(request, model=self._model)
                self._last_provisional_id = utterance_id
                await self._speak(authored)
            except Exception as error:  # noqa: BLE001 — speech errors don't kill the session
                logger.warning("provisional speech failed: %s", error)
        else:
            # No active run - full voice Q&A is Phase 2, but provide audible feedback instead of silence
            logger.info("question outside active run: %r (full Q&A is Phase 2)", transcript)
            speech = AuthoredSpeech(
                text="I do not have a mission loaded. Please provide an observation or command a mission.",
                run_id="sys_session",
                utterance_id=new_identifier(IdentifierPrefix.UTTERANCE),
                kind=SpeechKind.REFUSAL,
            )
            await self._speak(speech)

    async def _handle_abandon(self) -> None:
        """Abandon the active run at a safe node boundary."""
        if self._active_run is None or not self._active_run.is_running:
            logger.info("no active run to abandon")
            return
        logger.info("abandoning run %s", self._active_run.run_id)
        await self._active_run.abandon("operator voice command")

    async def _handle_standby(self) -> None:
        """Suppress speech while the scientific run continues."""
        await self._player.standby()
        self._set_state(VoiceSessionState.STANDBY)

    async def _handle_resume(self) -> None:
        """Restore speech after standby."""
        await self._player.resume()
        if self._active_run is not None and self._active_run.is_running:
            self._set_state(VoiceSessionState.RUNNING)
        elif self._pending_approval is not None:
            self._set_state(VoiceSessionState.PENDING_APPROVAL)
        else:
            self._set_state(VoiceSessionState.IDLE)

    async def _speak(self, authored: AuthoredSpeech) -> None:
        """Synthesize and play one authored utterance."""
        try:
            chunks = self._synthesizer.chunks(authored)
            await self._player.speak(authored, chunks)
        except Exception as error:  # noqa: BLE001 — playback errors don't kill the session
            logger.warning("speech playback failed: %s", error)

    def _session_context(self) -> str:
        """Build a brief text description of the session state for the turn classifier."""
        parts: list[str] = [f"state={self._state.value}"]
        if self._pending_approval is not None and self._plan_payload is not None:
            step_ids = [
                step["id"]
                for step in self._plan_payload.get("steps", [])
                if step.get("isEnabled")
            ]
            parts.append(f"pending_approval=true, planned_steps={step_ids}")
        if self._active_run is not None:
            parts.append(
                f"active_run={self._active_run.run_id}, "
                f"run_status={'running' if self._active_run.is_running else 'finished'}"
            )
        return "; ".join(parts)

    def _run_context(self) -> str:
        """Minimal context for a provisional speech request during an active run."""
        if self._active_run is None:
            return ""
        return f"run_id={self._active_run.run_id}, status={'running' if self._active_run.is_running else 'finished'}"

    def create_approver(self) -> Callable[[dict[str, Any], str], Any]:
        """Build an async approver callback for ``converse()`` that waits for voice approval.

        The approver is what makes the LangGraph ``interrupt()`` wait for the operator's voice
        instead of a terminal prompt.
        """

        async def voice_approver(plan: dict[str, Any], source: str) -> list[str] | None:
            self._plan_payload = plan
            self._plan_source = source
            self._pending_approval = asyncio.get_event_loop().create_future()
            self._set_state(VoiceSessionState.PENDING_APPROVAL)

            # Speak the plan summary so the operator knows what to approve
            utterance_id = new_identifier(IdentifierPrefix.UTTERANCE)
            step_summaries = []
            for step in plan.get("steps", []):
                if step.get("isEnabled"):
                    step_summaries.append(step.get("title", step.get("id", "unknown")))

            summary = plan.get("summary", "Analysis plan ready.")
            plan_text = f"{summary} The plan has {len(step_summaries)} steps: {', '.join(step_summaries)}. Say approve to run, or tell me which steps to keep."

            # Author progress speech for the plan announcement
            run_id = new_identifier(IdentifierPrefix.RUN)  # temporary run id for plan speech
            request = SpeechRequest(
                run_id=run_id,
                utterance_id=utterance_id,
                question=plan_text,
            )
            try:
                authored = await author_progress_speech(
                    request, {"detail": plan_text, "state": "pending"}, model=self._model
                )
                if authored is not None:
                    await self._speak(authored)
            except Exception:  # noqa: BLE001 — plan speech failure doesn't block approval
                logger.debug("plan announcement speech failed", exc_info=True)

            # Wait for the operator's voice approval
            kept = await self._pending_approval
            return kept

        return voice_approver

    async def start_agent_run(
        self,
        request: str,
        *,
        scene_directory: Any = None,
        reference_directory: Any = None,
        image_paths: list[Any] | None = None,
        sar: list[bool] | None = None,
        declared_level: Any = None,
        ground_sample_distance: float | None = None,
        declared_registered: bool = False,
        thread: str | None = None,
    ) -> Any:
        """Launch a full agent conversation with voice approval and speech narration."""
        from app.agents.run import converse

        approver = self.create_approver()
        self._set_state(VoiceSessionState.RUNNING)

        try:
            outcome = await converse(
                request,
                approver=approver,
                agent_id=thread,
                scene_directory=scene_directory,
                reference_directory=reference_directory,
                declared_registered=declared_registered,
                image_paths=image_paths or [],
                sar=sar,
                declared_level=declared_level,
                ground_sample_distance=ground_sample_distance,
            )

            # Speak the grounded result
            claims = []
            for result in outcome.results:
                claims.extend(result.get("claims") or [])

            if claims:
                utterance_id = new_identifier(IdentifierPrefix.UTTERANCE)
                request_obj = SpeechRequest(
                    run_id=outcome.request_id,
                    utterance_id=utterance_id,
                    question=outcome.state.get("request", ""),
                    supersedes_utterance_id=self._last_provisional_id,
                )
                try:
                    authored = await author_grounded_speech(
                        request_obj, claims, model=self._model
                    )
                    self._last_provisional_id = None
                    await self._speak(authored)
                except Exception:  # noqa: BLE001 — grounded speech failure is reported
                    logger.warning("grounded result speech failed", exc_info=True)

            self._set_state(VoiceSessionState.IDLE)
            return outcome

        except Exception as error:  # noqa: BLE001 — run errors are reported, session continues
            logger.error("agent run failed: %s", error)
            self._set_state(VoiceSessionState.IDLE)
            raise

    async def close(self) -> None:
        """Tear down all audio resources."""
        if self._state == VoiceSessionState.CLOSED:
            return
        self._session_closed.set()
        self._stop_capture.set()
        # Resolve any pending approval so converse() unblocks
        if self._pending_approval is not None and not self._pending_approval.done():
            self._pending_approval.cancel()
            self._pending_approval = None
        try:
            await self._player.close()
        except Exception:  # noqa: BLE001 — close errors are logged, not fatal
            logger.debug("player close failed", exc_info=True)
        self._set_state(VoiceSessionState.CLOSED)

    def signal_hotkey(self) -> None:
        """Called by the prompt-toolkit key binding when Ctrl+P is pressed."""
        self._hotkey_event.set()
