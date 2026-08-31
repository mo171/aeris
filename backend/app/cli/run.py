"""Everything `aeris run` does - start a run, resume one from its checkpoint, or replay one from its journal.

what  : `execute_run()`, `execute_resume()` and `execute_replay()`, the three async functions behind the
        one Typer command in `cli/main.py`.
where : Called from `cli/main.py`, which owns the single `asyncio.run()` and turns the result into an exit
        code. Phase 1.10 points the same command at the three real graphs; Phase 2.3 calls the same
        session and run-handle code from an SSE route.
how   : The three modes are one command because they answer one question - *what happened in this run* -
        from three different starting points, and because they share every line below the entry point:
        the same session, the same fan-out, the same two renderers.

        **Replay reads the journal and never touches the graph.** That is the whole point of it: a run
        that took ten minutes and a GPU can be re-rendered in milliseconds with no infrastructure at all.
        It is also the thing that proves the journal is complete - if replaying a run produces a different
        display from watching it live, the journal was missing something.

        **Resume reads the checkpoint and never touches the journal.** Symmetrically: the checkpoint knows
        what the pipeline computed, the journal knows what the operator was shown. Keeping them separate is
        what makes each one answerable on its own.

        **The intent is an argument until Phase 1.8.** `run-start` requires one, and 1.8 is where a
        classifier produces it. Asking the operator in the meantime is honest; defaulting silently to
        `SCENE_VQA` would put a value on the wire that nothing chose.
"""

import logging

from rich.console import Console

from app.cli.renderers.journal_writer import JournalWriter, journal_path, open_journal, read_journal
from app.cli.renderers.trace_renderer import TraceRenderer
from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.statuses import RunStatus
from app.schemas.events import RunCompleteEvent, RunErrorEvent
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.session import open_session

logger = logging.getLogger(__name__)


def _register_consumers(fanout: EventFanout, journal: JournalWriter, renderer: TraceRenderer) -> None:
    """Register the two consumers, journal first.

    Order is the contract (`services/sessions/fanout.py`): the journal is provenance and the renderer is
    decoration, so if the process dies between two consumers the journal is the one that already has the
    event.
    """
    fanout.register("journal", journal)
    fanout.register("trace", renderer)


async def execute_run(
    *,
    query: str,
    intent: Intent,
    graph_name: GraphName,
    console: Console,
    pause_seconds: float,
) -> RunStatus:
    """Start a run and watch it to completion."""
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = GRAPH_BUILDERS[graph_name]().compile(checkpointer=checkpointer, store=store)

        async with open_session() as session:
            # The run id is not known until the session mints it, and the journal is named after it - so
            # the session starts the run, and the journal opens around the handle rather than before it.
            # `start()` returns immediately, which is what makes that ordering possible at all.
            fanout = EventFanout()
            handle = await session.start(
                graph=graph,
                query=query,
                intent=intent,
                fanout=fanout,
                extra_state={"probe_pause_seconds": pause_seconds} if graph_name is GraphName.PROBE else None,
            )

            async with open_journal(handle.run_id) as journal:
                with TraceRenderer(console) as renderer:
                    _register_consumers(fanout, journal, renderer)
                    status = await handle.wait()

            console.print(f"journal: {journal_path(handle.run_id)}")
            return status


async def execute_resume(
    *, run_id: str, intent: Intent, graph_name: GraphName, console: Console
) -> RunStatus:
    """Continue a run that stopped partway, from its last checkpoint rather than from S1."""
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = GRAPH_BUILDERS[graph_name]().compile(checkpointer=checkpointer, store=store)

        snapshot = await read_thread_state(graph, run_id)
        if snapshot.created_at is None:
            console.print(f"[red]No checkpoint for {run_id}.[/red] Nothing to resume.")
            return RunStatus.FAILED
        if not snapshot.next:
            # `next` empty means the thread ran to the end. Reported rather than re-run, because resuming a
            # finished run would append a second set of events to its journal and change its record.
            console.print(f"Run {run_id} is already complete. Nothing to resume.")
            return RunStatus.COMPLETE

        console.print(f"Resuming {run_id} at {', '.join(snapshot.next)}.")

        async with open_session() as session:
            fanout = EventFanout()
            async with open_journal(run_id) as journal:
                with TraceRenderer(console) as renderer:
                    _register_consumers(fanout, journal, renderer)
                    handle = await session.resume(
                        graph=graph, run_id=run_id, intent=intent, fanout=fanout
                    )
                    return await handle.wait()


async def execute_replay(*, run_id: str, console: Console) -> RunStatus:
    """Re-render a finished run from its journal, computing nothing.

    Needs no checkpointer, no store, no graph and no infrastructure - which is the property that makes a
    journal worth writing. The renderer is the same object the live run used, fed the same events in the
    same order, so a replay that looks different from the live run means the journal is incomplete.
    """
    status = RunStatus.FAILED
    with TraceRenderer(console) as renderer:
        for event in read_journal(run_id):
            await renderer(event)
            match event:
                case RunCompleteEvent():
                    status = RunStatus.COMPLETE
                case RunErrorEvent():
                    # `FAILED`, not `CANCELLED`, and not by inspecting the message. The frontend's
                    # `run-error` carries no code field (api-contract.md §5), so a replay genuinely cannot
                    # tell a failure from an abandonment. Reporting the outcome it can defend is better
                    # than string-matching the operator-facing text and being wrong on a reworded message.
                    status = RunStatus.FAILED
    return status
