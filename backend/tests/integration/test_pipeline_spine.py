"""The Phase 1.0 gate: a run streams, checkpoints, resumes, can be abandoned - and survives being interrupted.

what  : Tests over `services/pipeline/`, `services/sessions/` and `cli/renderers/`, driving the probe graph
        end to end.
where : `tests/integration/`. Needs **no Docker** - the checkpointer and the memory store are SQLite files
        in a temporary directory, and the probe graph touches no imagery. That is deliberate: the spine is
        the one part of the system that must be diagnosable on a laptop with everything else switched off.
how   : The roadmap's 1.0 gate is five statements, and each has a test below whose name says which:

        1. a completed run replays from its journal without recomputing
        2. a run killed mid-pipeline resumes from its last checkpoint, not from the beginning
        3. an explicitly abandoned run stops within one node boundary, emits `run-error` with a
           cancellation reason, and is still resumable
        4. **a run survives being interrupted** - a second command into the same session is accepted and
           answered while it continues, and it still reaches `run-complete` with the journal it would have
           produced undisturbed
        5. the journal validates against the vendored contracts

        Statement 4 is the one worth reading. It is the gate `product-truth.md` §1.3 was corrected to
        require, and it fails on any design that awaits `graph.astream()` inline - which is why it is
        written as *two runs in one session*, rather than as a check that some flag is set.

        `probe_pause_seconds` is what makes 3 and 4 deterministic rather than a race. A run that finishes
        in three milliseconds can only be caught mid-flight by luck, and a test that depends on luck is a
        test that fails on someone else's machine.
"""

import asyncio
import json
import time
from pathlib import Path

import pytest
from langgraph.graph import END, START, StateGraph

from app.cli.renderers.journal_writer import journal_path, open_journal, read_journal
from app.constants.intents import Intent
from app.constants.stages import PipelineStage
from app.constants.statuses import RunStatus, TraceStepState
from app.lib.exceptions import RunCancelledError
from app.schemas.events import (
    AnalysisStreamEvent,
    AnswerTokenEvent,
    RunCompleteEvent,
    RunErrorEvent,
    RunStartEvent,
    TraceStepEvent,
)
from app.services.pipeline.cancellation import (
    AbandonmentSignal,
    bound_signal,
    current_signal,
    raise_if_abandoned,
)
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs.probe import build_probe_graph, understand_query
from app.services.pipeline.memory_store import open_memory_store, operator_namespace
from app.services.pipeline.node import pipeline_node
from app.services.pipeline.state import PipelineState
from app.services.sessions.fanout import EventFanout
from app.services.sessions.session import Session, open_session

# How long a test is willing to wait for something that should take milliseconds. Generous, because the
# failure it guards against is a hang, and a hung suite tells you less than a failed assertion.
TIMEOUT_SECONDS = 20.0


class Recorder:
    """A fan-out consumer that keeps every event, so a test can assert on the stream the operator saw."""

    def __init__(self) -> None:
        self.events: list[AnalysisStreamEvent] = []
        # Signalled on every event, so `wait_for_stage` blocks on an event rather than polling. A poll loop
        # would work here, but its interval is a hidden lower bound on how fast a test can act - and these
        # tests act *while a run is in flight*, so acting late is acting at the wrong moment.
        self._arrived = asyncio.Event()

    async def __call__(self, event: AnalysisStreamEvent) -> None:
        self.events.append(event)
        self._arrived.set()

    @property
    def types(self) -> list[str]:
        return [event.type for event in self.events]

    def trace_steps(self) -> list[TraceStepEvent]:
        return [event for event in self.events if isinstance(event, TraceStepEvent)]

    def _has_reached(self, stage: PipelineStage, state: TraceStepState) -> bool:
        return any(
            step.step.stage_code is stage and step.step.state is state for step in self.trace_steps()
        )

    async def wait_for_stage(self, stage: PipelineStage, state: TraceStepState) -> None:
        """Block until a stage reaches a state, so a test acts at a known point rather than after a sleep.

        Clear-then-check-then-wait, in that order. Clearing after the check would race: an event arriving
        between the two would be erased by the clear and waited for forever.
        """
        async with asyncio.timeout(TIMEOUT_SECONDS):
            while True:
                self._arrived.clear()
                if self._has_reached(stage, state):
                    return
                await self._arrived.wait()


@pytest.fixture
async def graph(isolated_pipeline_paths: Path):
    """A compiled probe graph over a checkpointer and store isolated to this test."""
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        yield build_probe_graph().compile(checkpointer=checkpointer, store=store)


async def run_to_completion(
    session: Session, graph, query: str, *, pause_seconds: float = 0.0
) -> tuple[str, Recorder]:
    """Start a run, journal it, wait for it, and return its id and everything it emitted."""
    recorder = Recorder()
    fanout = EventFanout()
    handle = await session.start(
        graph=graph,
        query=query,
        intent=Intent.CHANGE_DETECT,
        fanout=fanout,
        extra_state={"probe_pause_seconds": pause_seconds},
    )
    async with open_journal(handle.run_id) as journal:
        fanout.register("journal", journal)
        fanout.register("recorder", recorder)
        await handle.wait()
    return handle.run_id, recorder


# --- 1. The run itself -------------------------------------------------------------------------------


async def test_a_run_streams_its_trace_and_completes(graph) -> None:
    """The baseline: two stages, each emitted twice, an answer, a completion."""
    async with open_session() as session:
        run_id, recorder = await run_to_completion(session, graph, "Did the built-up area increase?")
        assert session.run(run_id).status is RunStatus.COMPLETE

    assert recorder.types[0] == "run-start"
    assert recorder.types[-1] == "run-complete"
    assert [step.step.stage_code for step in recorder.trace_steps()] == [
        PipelineStage.S1, PipelineStage.S1, PipelineStage.S20, PipelineStage.S20
    ]


async def test_every_trace_step_is_emitted_twice_under_one_id(graph) -> None:
    """`running` then terminal, **keyed on the same id** (`api-contract.md` §3.1).

    The shared id is the load-bearing half. The frontend replaces the row rather than appending a second
    one, so two ids for one stage would produce a trace that looks correct in the terminal and shows every
    stage twice in the browser - discovered in Phase 2, against a run that costs a GPU to reproduce.
    """
    async with open_session() as session:
        _, recorder = await run_to_completion(session, graph, "anything")

    by_id: dict[str, list[TraceStepState]] = {}
    for event in recorder.trace_steps():
        by_id.setdefault(event.step.id, []).append(event.step.state)

    assert len(by_id) == 2, "two stages ran, so there must be exactly two step ids"
    for states in by_id.values():
        assert states == [TraceStepState.RUNNING, TraceStepState.COMPLETED]

    # And the duration appears only on the terminal emission - it does not exist yet on the first.
    for event in recorder.trace_steps():
        if event.step.state is TraceStepState.RUNNING:
            assert event.step.duration_ms is None
        else:
            assert event.step.duration_ms is not None


async def test_the_run_declines_to_state_a_confidence_it_did_not_measure(graph) -> None:
    """`None`, never `0.0`. Zero is the claim "no confidence", which is a different statement."""
    async with open_session() as session:
        _, recorder = await run_to_completion(session, graph, "anything")

    completion = recorder.events[-1]
    assert isinstance(completion, RunCompleteEvent)
    assert completion.confidence is None


# --- 2. The journal ----------------------------------------------------------------------------------


async def test_the_journal_holds_exactly_what_the_stream_carried(graph) -> None:
    """Gate 1, first half. Every event, in order, one JSON object per line."""
    async with open_session() as session:
        run_id, recorder = await run_to_completion(session, graph, "anything")

    lines = journal_path(run_id).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(recorder.events)
    assert [json.loads(line)["type"] for line in lines] == recorder.types


async def test_a_run_replays_from_its_journal_without_recomputing(graph) -> None:
    """**Gate 1.** The journal alone reproduces the run - no graph, no checkpointer, no infrastructure."""
    async with open_session() as session:
        run_id, recorder = await run_to_completion(session, graph, "anything")

    replayed = list(read_journal(run_id))

    assert replayed == recorder.events, "a replay that differs from the live run means the journal is lossy"


# --- 3. Resume ---------------------------------------------------------------------------------------


async def test_an_abandoned_run_stops_at_a_node_boundary_and_stays_resumable(graph) -> None:
    """**Gate 3.** Abandon mid-stage: `run-error` with a reason, checkpoint intact, resume completes it.

    The two halves are equally important. Stopping is easy; stopping *and still being resumable* is the
    thing that makes an operator willing to press stop at all.
    """
    async with open_session() as session:
        recorder = Recorder()
        fanout = EventFanout()
        handle = await session.start(
            graph=graph,
            query="the long one",
            intent=Intent.CHANGE_DETECT,
            fanout=fanout,
            extra_state={"probe_pause_seconds": 5.0},
        )
        fanout.register("recorder", recorder)

        await recorder.wait_for_stage(PipelineStage.S20, TraceStepState.RUNNING)
        status = await handle.abandon("the operator asked for a different scene")

        assert status is RunStatus.CANCELLED

        terminal = recorder.events[-1]
        assert isinstance(terminal, RunErrorEvent)
        assert "abandoned" in terminal.message.lower()
        assert "different scene" in terminal.message, "the reason has to survive to the operator"

        # S1 finished before the stop, so the checkpoint holds its work and S20 is what remains.
        snapshot = await read_thread_state(graph, handle.run_id)
        assert snapshot.next == ("compose_answer",), "the abandoned node must not be recorded as done"
        assert "Understood: the long one." in snapshot.values["answer_tokens"]

        # And it resumes to completion, re-running only the stage that was interrupted.
        resumed_recorder = Recorder()
        resumed_fanout = EventFanout()
        resumed_fanout.register("recorder", resumed_recorder)
        resumed = await session.resume(
            graph=graph, run_id=handle.run_id, intent=Intent.CHANGE_DETECT, fanout=resumed_fanout
        )
        assert await resumed.wait() is RunStatus.COMPLETE

        resumed_stages = [step.step.stage_code for step in resumed_recorder.trace_steps()]
        assert PipelineStage.S1 not in resumed_stages, "S1 completed before the stop; resuming must not redo it"
        assert PipelineStage.S20 in resumed_stages


async def test_a_node_does_not_start_when_the_run_is_already_abandoned() -> None:
    """The **entry** boundary check, on its own, because end-to-end it is masked by two other guards.

    Written after mutation testing found the gap. Deleting the entry check from `pipeline_node` left every
    test green: the probe graph's slow stage also checks the signal inside its own loop, and the decorator
    checks again on the way *out* of the previous stage - so the run still stopped, by a different route.

    Three mechanisms, one behaviour, and none of them individually tested is how a guard quietly stops
    working. This one is the guarantee that matters for a real pipeline: **a stage whose body never checks
    anything must still not begin.** Almost every node is that shape - inference in a thread, a raster read
    - and for those, the boundary is the only place a run can stop.

    Isolated rather than end-to-end because it has to be deterministic: the node must be observed *not*
    starting, and there is no reliable moment to catch that in a graph whose stages take microseconds.
    """
    signal = AbandonmentSignal("run_never_started")
    signal.request("the operator asked for a different scene")

    with bound_signal(signal), pytest.raises(RunCancelledError) as raised:
        await understand_query({"run_id": "run_never_started", "query": "anything"})

    assert "different scene" in str(raised.value)
    # `RunCancelledError`, specifically. Without the entry check the body would run and fail on `emit()`
    # with a `RuntimeError` about a missing runnable context - a failure, but the wrong one, and one that
    # says nothing about abandonment.


async def test_a_node_outside_a_run_is_not_treated_as_abandoned() -> None:
    """No signal bound means nothing to check, not "assume the worst".

    A node called with no run around it is a unit test of that node, and a boundary check that raised there
    would make every future node untestable in isolation.
    """
    assert current_signal() is None
    raise_if_abandoned()


@pipeline_node(PipelineStage.S19, detail="a stage that never checks anything itself")
async def stage_abandoned_from_outside(state: dict) -> dict:
    """A node whose body ignores the signal entirely, stopped while it works.

    Stands in for the ordinary case: almost every real stage is inference in a thread or a raster read,
    with no natural point to check anything. Requesting abandonment from inside the body is how a test
    reproduces "the operator pressed stop while this stage was running" without a race.
    """
    signal = current_signal()
    assert signal is not None, "a node inside a run must have a signal bound"
    signal.request("the operator stopped it mid-stage")
    return {"answer_tokens": ["done anyway"]}


async def test_a_run_abandoned_during_its_final_stage_does_not_report_success(
    isolated_pipeline_paths: Path,
) -> None:
    """The **exit** boundary check, which mutation testing showed nothing else covers.

    Removing it left all twenty other tests green, because for every stage *except the last* the next
    stage's entry check stops the run anyway. The last stage is where it is the only guard - and without
    it, a run the operator was told was cancelled emits `run-complete` instead. The handle says one thing
    and the permanent record says the other, which is the worst kind of disagreement to find later.

    A single-node graph, because "the last stage" is the whole case.
    """
    builder: StateGraph = StateGraph(PipelineState)
    builder.add_node("only_stage", stage_abandoned_from_outside)
    builder.add_edge(START, "only_stage")
    builder.add_edge("only_stage", END)

    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        one_stage_graph = builder.compile(checkpointer=checkpointer, store=store)

        async with open_session() as session:
            recorder = Recorder()
            fanout = EventFanout()
            handle = await session.start(
                graph=one_stage_graph, query="anything", intent=Intent.SCENE_VQA, fanout=fanout
            )
            fanout.register("recorder", recorder)

            assert await handle.wait() is RunStatus.CANCELLED

    terminal = recorder.events[-1]
    assert isinstance(terminal, RunErrorEvent), "the record must agree with what the operator was told"
    assert "mid-stage" in terminal.message

    # The stage itself still completed - it was not interrupted, it simply was the last thing that ran.
    assert [step.step.state for step in recorder.trace_steps()] == [
        TraceStepState.RUNNING,
        TraceStepState.COMPLETED,
    ]


async def test_abandoning_a_long_stage_does_not_wait_for_it_to_finish(graph) -> None:
    """What the in-node check buys: stop is felt immediately rather than at the end of the stage.

    Without it a run still stops - the boundary check catches it - but only once the current stage is over,
    which for a real stage is minutes. That is the difference between an operator who presses stop and one
    who learns that pressing stop does nothing.
    """
    async with open_session() as session:
        recorder = Recorder()
        fanout = EventFanout()
        handle = await session.start(
            graph=graph,
            query="the long one",
            intent=Intent.CHANGE_DETECT,
            fanout=fanout,
            extra_state={"probe_pause_seconds": 10.0},
        )
        fanout.register("recorder", recorder)
        await recorder.wait_for_stage(PipelineStage.S20, TraceStepState.RUNNING)

        started_at = time.perf_counter()
        assert await handle.abandon("stop now") is RunStatus.CANCELLED
        elapsed = time.perf_counter() - started_at

    assert elapsed < 2.0, (
        f"abandoning took {elapsed:.1f}s of a 10s stage. The stage is not checking the signal in its own "
        "loop, so stop waits for the whole stage - see ABANDONMENT_CHECK_INTERVAL_SECONDS in graphs/probe.py."
    )


async def test_abandoning_a_finished_run_is_a_no_op(graph) -> None:
    """The operator saying stop a moment after it completed must not raise, and must not rewrite history."""
    async with open_session() as session:
        recorder = Recorder()
        fanout = EventFanout()
        handle = await session.start(
            graph=graph, query="quick", intent=Intent.SCENE_VQA, fanout=fanout, extra_state={}
        )
        fanout.register("recorder", recorder)
        assert await handle.wait() is RunStatus.COMPLETE

        assert await handle.abandon("too late") is RunStatus.COMPLETE
        assert recorder.types[-1] == "run-complete"


# --- 4. The gate the correction is about --------------------------------------------------------------


async def test_a_run_survives_being_interrupted(graph) -> None:
    """**Gate 4, and the reason this file exists.** A second command mid-run is answered; the run continues.

    `product-truth.md` §1.3: barge-in stops the utterance, never the work. That is only implementable if
    the run is a detached task over a shared session, so this test is written as the operator's actual
    behaviour - ask something long, then ask something else while it works - rather than as an assertion
    about an internal flag.

    It fails on any design that awaits the run inline, because there would be no line on which to ask the
    second question.
    """
    async with open_session() as session:
        slow_recorder = Recorder()
        slow_fanout = EventFanout()
        slow = await session.start(
            graph=graph,
            query="the long one",
            intent=Intent.CHANGE_DETECT,
            fanout=slow_fanout,
            extra_state={"probe_pause_seconds": 2.0},
        )
        slow_fanout.register("recorder", slow_recorder)

        await slow_recorder.wait_for_stage(PipelineStage.S20, TraceStepState.RUNNING)
        assert slow.is_running

        # The operator interrupts and asks something else. The session takes it immediately.
        quick_run_id, quick_recorder = await run_to_completion(session, graph, "and what sensor is that?")

        assert quick_recorder.types[-1] == "run-complete"
        assert slow.is_running, "answering a second question must not have touched the first run"
        assert len(session.running) == 1

        assert await slow.wait() is RunStatus.COMPLETE
        assert slow_recorder.types[-1] == "run-complete"
        assert quick_run_id != slow.run_id


async def test_an_interrupted_run_produces_the_journal_it_would_have_undisturbed(graph) -> None:
    """The second half of gate 4: interrupting changes *nothing* about the run's record.

    Compared against a control run of the same shape rather than against a hard-coded list, so the test
    keeps meaning something when the probe graph changes.
    """
    async with open_session() as session:
        control_id, _ = await run_to_completion(session, graph, "the long one", pause_seconds=0.5)

        disturbed_recorder = Recorder()
        disturbed_fanout = EventFanout()
        disturbed = await session.start(
            graph=graph,
            query="the long one",
            intent=Intent.CHANGE_DETECT,
            fanout=disturbed_fanout,
            extra_state={"probe_pause_seconds": 0.5},
        )
        async with open_journal(disturbed.run_id) as journal:
            disturbed_fanout.register("journal", journal)
            disturbed_fanout.register("recorder", disturbed_recorder)
            await disturbed_recorder.wait_for_stage(PipelineStage.S20, TraceStepState.RUNNING)
            await run_to_completion(session, graph, "an interruption")
            await run_to_completion(session, graph, "another interruption")
            assert await disturbed.wait() is RunStatus.COMPLETE

    control_types = [event.type for event in read_journal(control_id)]
    disturbed_types = [event.type for event in read_journal(disturbed.run_id)]
    assert disturbed_types == control_types


async def test_a_session_waits_for_its_runs_rather_than_killing_them(graph) -> None:
    """Leaving a session is not the same statement as stopping the analysis it started.

    The inverse - closing a session cancels its runs - is the same mistake as barge-in cancelling a run,
    one level up, and it is the shape a session would naturally be written in if nobody had decided.
    """
    recorder = Recorder()
    async with open_session() as session:
        fanout = EventFanout()
        handle = await session.start(
            graph=graph,
            query="still going",
            intent=Intent.SCENE_VQA,
            fanout=fanout,
            extra_state={"probe_pause_seconds": 0.4},
        )
        fanout.register("recorder", recorder)
        assert handle.is_running

    assert handle.status is RunStatus.COMPLETE
    assert recorder.types[-1] == "run-complete"


# --- 5. The fan-out ----------------------------------------------------------------------------------


async def test_a_failing_consumer_is_detached_and_the_run_still_completes(graph) -> None:
    """A broken terminal must not lose a ten-minute analysis.

    The journal is registered first for exactly this reason, and the test asserts the surviving consumer
    got the whole stream rather than just that the run did not crash.
    """
    async def explode(event: AnalysisStreamEvent) -> None:
        raise RuntimeError("the terminal was resized")

    async with open_session() as session:
        recorder = Recorder()
        fanout = EventFanout()
        handle = await session.start(
            graph=graph, query="anything", intent=Intent.SCENE_VQA, fanout=fanout, extra_state={}
        )
        fanout.register("recorder", recorder)
        fanout.register("broken", explode)

        assert await handle.wait() is RunStatus.COMPLETE

    assert "broken" not in fanout.consumer_names, "a consumer that raised must be detached"
    assert "recorder" in fanout.consumer_names
    assert recorder.types[-1] == "run-complete"


async def test_the_journal_is_registered_before_the_renderer(graph) -> None:
    """Order is the contract: provenance is written before decoration is drawn."""
    fanout = EventFanout()
    fanout.register("journal", Recorder())
    fanout.register("trace", Recorder())
    assert fanout.consumer_names == ("journal", "trace")


# --- 6. Memory ---------------------------------------------------------------------------------------


async def test_long_term_memory_is_a_different_database_from_the_checkpoints(
    isolated_pipeline_paths: Path,
) -> None:
    """Two files, deliberately (`product-truth.md` §1.6).

    They have opposite lifetimes: checkpoints are per-run scratch that is safe to delete, long-term memory
    is what the operator taught the system. Sharing a file makes "clear the checkpoints" a command that can
    destroy the second, and no care at the call site makes that safe again.
    """
    from app.config import settings

    assert settings.checkpoint_database_path != settings.memory_database_path


async def test_a_memory_outlives_the_process_that_wrote_it(isolated_pipeline_paths: Path) -> None:
    """The 1.0 claim about memory, and the whole of it: the store opens, writes, and remembers.

    Nothing populates it yet - 1.9 adds `remember` and `recall` as agent tools. What is proven here is that
    the phase which does has somewhere to put things, and that closing the store does not lose them.
    """
    namespace = operator_namespace()

    async with open_memory_store() as store:
        await store.aput(namespace, "prefers-hectares", {"unit": "hectares"})

    async with open_memory_store() as store:
        item = await store.aget(namespace, "prefers-hectares")

    assert item is not None, "a memory that does not survive the store closing is not long-term memory"
    assert item.value == {"unit": "hectares"}


async def test_a_session_carries_its_own_memory_namespace() -> None:
    """Two sessions must not write into each other's memories."""
    async with open_session() as first, open_session() as second:
        assert first.memory_namespace != second.memory_namespace
        assert first.memory_namespace[:2] == ("aeris", "memory")


# --- 7. Identity -------------------------------------------------------------------------------------


async def test_the_thread_id_is_the_run_id(graph) -> None:
    """Resume is a direct lookup, with no table mapping runs to threads.

    A session's runs must not share a thread: the second would resume into the first one's half-finished
    state, which is the kind of bug that presents as an answer about the wrong scene.
    """
    async with open_session() as session:
        first_id, _ = await run_to_completion(session, graph, "one")
        second_id, _ = await run_to_completion(session, graph, "two")

        assert session.run(first_id).thread_id == first_id
        assert session.run(second_id).thread_id == second_id

        first_state = await read_thread_state(graph, first_id)
        assert first_state.values["query"] == "one"


async def test_the_run_start_event_names_the_intent_the_operator_chose(graph) -> None:
    """Until 1.8 classifies it, the intent is the operator's - and it has to reach the wire unchanged."""
    async with open_session() as session:
        recorder = Recorder()
        fanout = EventFanout()
        handle = await session.start(
            graph=graph, query="anything", intent=Intent.CROSS_MODAL, fanout=fanout, extra_state={}
        )
        fanout.register("recorder", recorder)
        await handle.wait()

    start = recorder.events[0]
    assert isinstance(start, RunStartEvent)
    assert start.intent is Intent.CROSS_MODAL


async def test_the_answer_is_streamed_as_tokens_rather_than_one_block(graph) -> None:
    """The token path has a producer before Phase 1.7 writes a real one."""
    async with open_session() as session:
        _, recorder = await run_to_completion(session, graph, "anything")

    tokens = [event for event in recorder.events if isinstance(event, AnswerTokenEvent)]
    assert len(tokens) > 1
    assert " ".join(token.text for token in tokens) == "The spine is working."


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/integration/test_pipeline_spine.py -q                        2026-08-31
#
#   ......................                                                   [100%]
#   22 passed in 12.73s
#
# No Docker. The checkpointer and the memory store are SQLite files under pytest's tmp_path, and the probe
# graph touches no imagery - so the spine stays diagnosable on a machine with every container stopped.
#
# Checked by mutation. Each row is a real edit to application code, the test run that caught it, and a
# restore verified by byte-comparing the file against its original:
#
#   A  `Session.start` awaits the run before returning     -> test_a_run_survives_being_interrupted FAILED
#      (the inline design product-truth.md §1.3.1 forbids)
#
#   B  entry boundary check deleted from pipeline_node     -> test_a_node_does_not_start_when_the_run_is
#                                                             _already_abandoned FAILED
#
#   B2 exit boundary check deleted from pipeline_node      -> test_a_run_abandoned_during_its_final_stage
#                                                             _does_not_report_success FAILED
#
#   B4 the slow node stops checking its own loop           -> test_abandoning_a_long_stage_does_not_wait
#                                                             _for_it_to_finish FAILED (29.8s vs 13.0s -
#                                                             the run waited out the whole 10s stage)
#
#   C  a fresh trace step id on every emission             -> test_every_trace_step_is_emitted_twice_under
#                                                             _one_id FAILED
#
#   E  session close abandons its runs instead of waiting  -> test_a_session_waits_for_its_runs_rather
#                                                             _than_killing_them FAILED
#
#   F  a failing consumer is re-raised, not detached       -> test_a_failing_consumer_is_detached_and_the
#                                                             _run_still_completes FAILED
#
#   G  the `running` trace emission dropped                -> test_every_trace_step_is_emitted_twice_under
#                                                             _one_id FAILED
#
#   H  a declined confidence coerced to 0.0                -> test_the_run_declines_to_state_a_confidence
#                                                             _it_did_not_measure FAILED
#
# **B2 and B4 are here because the first mutation pass did not catch them.** Deleting the entry check alone
# left all twenty tests green: three mechanisms stop an abandoned run - the entry check, the exit check, and
# the node's own loop - and every end-to-end test was satisfied by whichever fired first. Three guards, one
# observable behaviour, none of them individually tested, which is how a guard quietly stops working.
#
# The three tests above were written to separate them, and each one is the *only* thing that catches its
# mutation. The exit check turned out to matter for exactly one case - the last stage, where there is no
# next node whose entry check would catch it - and without it a run the operator was told was cancelled
# emits `run-complete`. That disagreement between the handle and the permanent record is the bug the
# mutation pass surfaced.
