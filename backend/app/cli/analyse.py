"""Everything `aeris analyse` does - resolve the question to an index, run the index-query graph over a scene, and show what it measured.

what  : `execute_analyse()`, the async function behind the one Typer command in `cli/main.py`.
where : Called from `cli/main.py`. Phase 1.8 replaces the phrase table with a classifier and 1.10 points
        the same command at the `single_image` graph; the flags do not change.
how   : The 1.4 gate, exactly: *"`aeris analyse --scene <id> --query "unhealthy vegetation"` produces an
        NDVI map, a stressed-region mask and an area in hectares"*. This is an adapter and nothing more -
        the question is resolved by `services/spectral/indices.py`, the work is the graph in
        `services/pipeline/graphs/index_query.py`, and the run goes through the same session, fan-out
        and renderers `aeris run` uses, plus the figure writer that fetches each figure back to disk.

        The measurement is read back from the checkpoint at the end rather than from anything this file
        accumulated, for the reason `run_handle.py` reads the confidence that way: the checkpoint is what a
        resumed run would see, and two sources for one number is how they come to disagree.
"""

import logging
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from app.cli.renderers.figure_writer import open_figure_writer
from app.cli.renderers.journal_writer import journal_path, open_journal
from app.cli.renderers.trace_renderer import TraceRenderer
from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
from app.constants.statuses import RunStatus
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.session import open_session
from app.services.spectral.indices import resolve_index_target

logger = logging.getLogger(__name__)


async def execute_analyse(
    *,
    scene_directory: Path,
    query: str,
    console: Console,
    declared_level: ProcessingLevel | None = None,
) -> RunStatus:
    """Resolve the question, run the graph, watch it, and print the measurement it checkpointed."""
    target = await resolve_index_target(query)
    console.print(
        f"\n  {escape(query)!s}  ->  {target.index.value.upper()}"
        + (
            f" in [{target.lower:.2f}, {target.upper:.2f}] ({escape(target.label)})"
            if target.has_range
            else " (map only)"
        )
    )

    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = GRAPH_BUILDERS[GraphName.INDEX_QUERY]().compile(checkpointer=checkpointer, store=store)

        async with open_session() as session:
            fanout = EventFanout()
            handle = await session.start(
                graph=graph,
                query=query,
                intent=Intent.INDEX_QUERY,
                fanout=fanout,
                extra_state={
                    "scene_directory": str(scene_directory),
                    "scene_id": scene_directory.name,
                    "declared_level": declared_level.value if declared_level else None,
                    "index": target.index.value,
                    "target_lower": target.lower,
                    "target_upper": target.upper,
                    "target_label": target.label,
                    "target_phrase": target.phrase,
                },
            )

            async with open_journal(handle.run_id) as journal, open_figure_writer(handle.run_id) as figures:
                with TraceRenderer(console) as renderer:
                    # Journal first: provenance before decoration (`services/sessions/fanout.py`).
                    fanout.register("journal", journal)
                    fanout.register("trace", renderer)
                    fanout.register("figures", figures)
                    status = await handle.wait()

            console.print(f"\n  journal  {escape(str(journal_path(handle.run_id)))}")
            for path in figures.written:
                console.print(f"  figure   {escape(str(path))}")

            if status is RunStatus.COMPLETE:
                snapshot = await read_thread_state(graph, handle.run_id)
                _print_measurement(snapshot.values, console)
            return status


def _print_measurement(values: dict[str, object], console: Console) -> None:
    """The numbers, from the checkpoint, in the units a report quotes them."""
    measurement = values.get("measurement")
    if not isinstance(measurement, dict):
        fractions = values.get("band_fractions") or {}
        for label, fraction in fractions.items():
            console.print(f"  {escape(str(label)):28s} {float(fraction):6.1%} of observed ground")
        return

    console.print(
        f"\n  {escape(str(values.get('target_label')))}: "
        f"[bold]{measurement['areaHectares']:,.2f} ha[/bold]"
        f"   {measurement['coverageFraction']:.2%} of {measurement['observedHectares']:,.2f} ha observed"
        f"   {measurement['regionCount']:,} regions"
        f"   {measurement['pixelCount']:,} px"
    )
    console.print(f"  measured in {escape(str(measurement['equalAreaCrs']))}")
