"""Runs one pipeline graph over one scene as a function: start, journal, figures, wait, read the checkpoint back.

what  : `IndexQueryOutcome` and `run_index_query()`.
where : `cli/analyse.py` (with a console, so the live trace draws) and `agents/tools/analysis_tools.py`
        (without one). One function, so the agent's run and the operator's run are the same run: same
        journal, same figures on disk, same provenance record, same checkpoint read at the end.
how   : The graph is compiled with the run checkpointer and the memory store, started through a session
        (which owns the run id, the fan-out and the abandonment signal), and observed by the journal
        writer and the figure writer; the console's trace renderer joins when a console is given. The
        outcome is read from the checkpoint - `read_thread_state` - for the reason `cli/analyse.py` gives:
        the checkpoint is what a resumed run would see, and two sources for one number is how they come to
        disagree.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
from app.constants.statuses import RunStatus
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.figure_writer import open_figure_writer
from app.services.sessions.journal_writer import journal_path, open_journal
from app.services.sessions.session import open_session
from app.services.spectral.indices import IndexTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IndexQueryOutcome:
    run_id: str
    status: RunStatus
    # The checkpointed state at the end: claims, evidence, measurement, answer tokens, provenance paths.
    values: dict[str, Any]
    journal: Path
    figures: tuple[Path, ...] = field(default=())

    @property
    def claims(self) -> list[dict[str, Any]]:
        return list(self.values.get("claims") or [])

    @property
    def answer(self) -> str:
        return " ".join(self.values.get("answer_tokens") or [])


async def run_index_query(
    *, scene_directory: Path, query: str, target: IndexTarget, intent: Intent = Intent.INDEX_QUERY,
    declared_level: ProcessingLevel | None = None, console: Console | None = None,
) -> IndexQueryOutcome:
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = GRAPH_BUILDERS[GraphName.INDEX_QUERY]().compile(checkpointer=checkpointer, store=store)
        async with open_session() as session:
            fanout = EventFanout()
            handle = await session.start(
                graph=graph, query=query, intent=intent, fanout=fanout,
                extra_state={
                    "scene_directory": str(scene_directory), "scene_id": scene_directory.name,
                    "declared_level": declared_level.value if declared_level else None,
                    "index": target.index.value, "target_lower": target.lower, "target_upper": target.upper,
                    "target_label": target.label, "target_phrase": target.phrase,
                },
            )
            async with open_journal(handle.run_id) as journal, open_figure_writer(handle.run_id) as figures:
                # Journal first: provenance before decoration (`services/sessions/fanout.py`).
                fanout.register("journal", journal)
                if console is not None:
                    from app.cli.renderers.trace_renderer import TraceRenderer

                    with TraceRenderer(console) as renderer:
                        fanout.register("trace", renderer)
                        fanout.register("figures", figures)
                        status = await handle.wait()
                else:
                    fanout.register("figures", figures)
                    status = await handle.wait()
            values = (await read_thread_state(graph, handle.run_id)).values if status is RunStatus.COMPLETE else {}
            return IndexQueryOutcome(handle.run_id, status, dict(values), journal_path(handle.run_id), tuple(figures.written))
