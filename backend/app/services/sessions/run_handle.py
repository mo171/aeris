"""Runs the graph as a detached task so the conversation can keep going while it works - the structural half of product-truth §1.3.1.

what  : `RunHandle`, returned the moment a run is launched, and `start_run()`, which launches one.
where : Created by `services/sessions/session.py`, held by the CLI and later by Phase 2.3's SSE route.
how   : **This is the file the §1.3 correction is about, and the reason it lands in 1.0 rather than 1.13.**

        The obvious way to run a graph is to await it:

            async for event in graph.astream(...):   # the caller is now blocked for ten minutes
                await render(event)

        Everything AERIS is supposed to be dies at that line. The agent cannot narrate, because it is
        inside the loop. It cannot answer a question asked mid-run, because there is nowhere for the
        question to arrive. It cannot be spoken over without cancelling the analysis, which is exactly the
        rule `product-truth.md` §1.3 was corrected to forbid. And it cannot be retrofitted later without
        changing the signature of everything between the caller and the node.

        So starting a run returns a handle **immediately**. A background task consumes the stream and fans
        it out; the caller is free the moment it has the handle.

        **Terminal events are emitted here, outside the graph.** A run that dies inside its first node
        still has to produce a `run-error`, and there is no node left to produce it from. `run-start` is
        emitted before the graph is invoked for the same reason - a graph that fails to compile has still
        started, from the operator's point of view.

        **Two tasks, not one, and that is what makes abandonment safe.** The outer task is the handle's
        task and is never hard-cancelled by `abandon()`; the inner task consumes the graph. Escalation
        cancels the inner one, so the outer one is always alive to write the terminal event. A single task
        would mean the hard-cancel path produces a run that simply stops, with no terminal event, no
        journal entry saying why, and a trace whose last row spins forever.

        **Abandonment escalates in two steps** (`services/pipeline/cancellation.py`): the cooperative
        signal first, which stops at a node boundary with the checkpoint intact and the run resumable; then
        - only after `pipeline_abandon_grace_seconds` - a hard cancel, for the node that never reaches a
        boundary. The order matters: the first mechanism leaves a resumable run and the second may not.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.constants.intents import Intent
from app.constants.statuses import RunStatus
from app.lib.exceptions import RunCancelledError
from app.schemas.events import (
    AnalysisStreamEvent,
    RunCompleteEvent,
    RunErrorEvent,
    RunStartEvent,
    parse_event,
)
from app.services.pipeline.cancellation import AbandonmentSignal, bound_signal
from app.services.sessions.fanout import EventFanout

logger = logging.getLogger(__name__)


class RunHandle:
    """A run in flight. Returned immediately; the work happens in a task behind it."""

    def __init__(
        self,
        *,
        run_id: str,
        thread_id: str,
        graph: Any,
        initial_state: dict[str, Any] | None,
        fanout: EventFanout,
        intent: Intent,
    ) -> None:
        self.run_id = run_id
        # One LangGraph thread per run, and the thread id **is** the run id. A run is one pipeline
        # execution with its own checkpoint lineage, so sharing a thread across the runs of a session would
        # make the second run resume into the first one's state. It also makes resume a direct lookup:
        # `aeris run --resume run_01J...` needs no table mapping runs to threads.
        self.thread_id = thread_id
        self.intent = intent
        self.status = RunStatus.RUNNING

        self._graph = graph
        # `None` means "resume this thread from its checkpoint" rather than "start with empty state" -
        # LangGraph's own convention, and the whole of what `resume_run` does differently.
        self._initial_state = initial_state
        self._fanout = fanout
        self._signal = AbandonmentSignal(run_id)
        self._started_at = time.perf_counter()
        self._graph_task: asyncio.Task[None] | None = None
        self._task: asyncio.Task[None] = asyncio.create_task(self._execute(), name=f"aeris-run-{run_id}")

    @property
    def is_running(self) -> bool:
        """True while the run is still working. False the moment a terminal event has been emitted."""
        return not self._task.done()

    async def wait(self) -> RunStatus:
        """Block until the run reaches a terminal state, and report which one.

        The one method a caller that genuinely has nothing else to do can use. Everything about the design
        above exists so that calling this is a *choice* - the CLI in 1.0 makes it, the voice loop in 1.13
        will not.
        """
        await self._task
        return self.status

    async def abandon(self, reason: str) -> RunStatus:
        """Stop the run, cooperatively if it will, forcibly if it will not.

        Idempotent: abandoning a finished run is a no-op that reports what it finished as, because the
        operator saying "stop" a moment after it completed should not raise.
        """
        if self._task.done():
            return self.status

        self._signal.request(reason)

        graph_task = self._graph_task
        if graph_task is not None and not graph_task.done():
            try:
                await asyncio.wait_for(
                    asyncio.shield(graph_task), timeout=settings.pipeline_abandon_grace_seconds
                )
            except TimeoutError:
                # The node never reached a boundary - a stalled read, a model that hangs. The operator has
                # already said stop, so the wait ends here. `shield` above is what keeps `wait_for` from
                # cancelling the task itself on timeout, so the cancel below is ours and is deliberate.
                logger.warning(
                    "run did not stop at a node boundary within the grace period; cancelling",
                    extra={"run_id": self.run_id, "grace_seconds": settings.pipeline_abandon_grace_seconds},
                )
                graph_task.cancel()
            except Exception:
                # The graph task's own failure is `_execute`'s to report - it is awaiting the same task and
                # turns it into the terminal event. Swallowed here so that `abandon()` never raises the
                # run's failure at the operator who was only trying to stop it.
                pass

        await self._task
        return self.status

    async def _execute(self) -> None:
        """The outer task. Emits the run's first and last events, and never hard-cancels itself."""
        await self._publish(
            RunStartEvent(run_id=self.run_id, intent=self.intent, started_at=datetime.now(UTC))
        )

        self._graph_task = asyncio.create_task(
            self._consume_graph(), name=f"aeris-graph-{self.run_id}"
        )

        try:
            await self._graph_task
        except RunCancelledError as error:
            self.status = RunStatus.CANCELLED
            await self._publish(
                RunErrorEvent.cancelled(self.run_id, self._signal.reason or str(error))
            )
        except asyncio.CancelledError:
            # Either `abandon()` escalated, or this whole task is being torn down. Only the first is ours
            # to report; in the second case the process is going away and re-raising is correct.
            if not self._signal.is_requested:
                raise
            self.status = RunStatus.CANCELLED
            await self._publish(
                RunErrorEvent.cancelled(self.run_id, self._signal.reason or "no reason given")
            )
        except Exception as error:
            self.status = RunStatus.FAILED
            logger.exception("run failed", extra={"run_id": self.run_id})
            # `str(error)` and not the traceback: this string is rendered to the operator, and
            # `api-contract.md` §1 rule 4 means the wire carries what is safe to show.
            await self._publish(RunErrorEvent(run_id=self.run_id, message=str(error) or type(error).__name__))
        else:
            self.status = RunStatus.COMPLETE
            await self._publish(
                RunCompleteEvent(
                    run_id=self.run_id,
                    confidence=await self._final_confidence(),
                    # 1.0 has no evidence subsystem, so no run can yet decide it has too little. Phase 1.5
                    # is what fills this in; `None` here is "the question was not asked", which is honest.
                    insufficient_evidence=None,
                    total_duration_ms=max(0, round((time.perf_counter() - self._started_at) * 1000)),
                )
            )

    async def _consume_graph(self) -> None:
        """The inner task. Iterates the graph's custom stream and fans each event out."""
        configuration = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": settings.pipeline_recursion_limit,
        }

        # Bound here rather than in `_execute` so the signal is in the context of the task that actually
        # runs the nodes. Python copies the context into every task LangGraph spawns, which is the same
        # mechanism its own `get_stream_writer()` relies on.
        with bound_signal(self._signal):
            async for chunk in self._graph.astream(
                self._initial_state,
                configuration,
                stream_mode="custom",
                durability=settings.pipeline_durability,
            ):
                # `parse_event` rather than trusting the dictionary: an event that does not satisfy the
                # union fails here, at the producer, rather than at the frontend's Zod in Phase 2.
                await self._publish(parse_event(chunk))

    async def _final_confidence(self) -> float | None:
        """The confidence the run ended with, read back from the checkpoint.

        Read from the checkpoint rather than accumulated in this object, because the checkpoint is what a
        resumed run would see. Two sources for one number is how they come to disagree.
        """
        snapshot = await self._graph.aget_state({"configurable": {"thread_id": self.thread_id}})
        return snapshot.values.get("confidence")

    async def _publish(self, event: AnalysisStreamEvent) -> None:
        await self._fanout.publish(event)


async def start_run(
    *,
    run_id: str,
    graph: Any,
    initial_state: dict[str, Any],
    fanout: EventFanout,
    intent: Intent,
) -> RunHandle:
    """Launch a run and return its handle immediately.

    A coroutine although it awaits nothing today: it is the seam where Phase 2.5 hands the invocation to
    Inngest instead of to a local task, and where 1.9 will persist the run row before the first node. A
    caller written against a sync function would have to change at every call site then.
    """
    handle = RunHandle(
        run_id=run_id,
        thread_id=run_id,
        graph=graph,
        initial_state=initial_state,
        fanout=fanout,
        intent=intent,
    )
    logger.info("run started", extra={"run_id": run_id, "intent": intent.value})
    return handle


async def resume_run(
    *,
    run_id: str,
    graph: Any,
    fanout: EventFanout,
    intent: Intent,
) -> RunHandle:
    """Continue a run that stopped partway, from its last checkpoint rather than from S1.

    The only difference from `start_run` is the input: `None` tells LangGraph to pick the thread up where
    it left off instead of starting a fresh execution. Verified rather than assumed - the recorded run in
    `tests/integration/test_pipeline_spine.py` abandons a run inside its second node and resumes it to
    completion, and the resumed execution re-runs only the interrupted node.
    """
    handle = RunHandle(
        run_id=run_id,
        thread_id=run_id,
        graph=graph,
        initial_state=None,
        fanout=fanout,
        intent=intent,
    )
    logger.info("run resumed from checkpoint", extra={"run_id": run_id})
    return handle
