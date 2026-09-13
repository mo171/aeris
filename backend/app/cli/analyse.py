"""Everything `aeris analyse` does - resolve the question to an index, run the index-query graph over a scene, and show what it measured.

what  : `execute_analyse()`, the async function behind the one Typer command in `cli/main.py`.
where : Called from `cli/main.py`. From 1.8 the router decides first: the intent, the specialist and the
        graph, or a refusal that names what the scene cannot answer (a car on a 10 m pixel). 1.10 points
        the same command at the `single_image` graph; the flags do not change.
how   : The 1.4 gate, exactly: *"`aeris analyse --scene <id> --query "unhealthy vegetation"` produces an
        NDVI map, a stressed-region mask and an area in hectares"*. This is an adapter and nothing more -
        the question is resolved by `services/spectral/indices.py`, the work is the graph in
        `services/pipeline/graphs/index_query.py`, run by `services/pipeline/runner.py` - the same
        function the agent's tools call, so an operator's run and an agent's run are the same run.

        The measurement is read back from the checkpoint at the end rather than from anything this file
        accumulated, for the reason `run_handle.py` reads the confidence that way: the checkpoint is what a
        resumed run would see, and two sources for one number is how they come to disagree.
"""

import logging
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from app.agents.router import RoutingDecision, SceneFacts, route_plan, routing_resources
from app.cli.route import render_plan
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
from app.constants.statuses import RunStatus
from app.services.pipeline.runner import run_index_query
from app.services.spectral.indices import finest_resolution, resolve_index_target

logger = logging.getLogger(__name__)


async def execute_analyse(
    *,
    scene_directory: Path,
    query: str,
    console: Console,
    declared_level: ProcessingLevel | None = None,
) -> RunStatus:
    """Route the request, run a graph per step that has one, watch each, and print what it measured.

    A request of several questions is several runs, in order, each with its own journal and record; a
    step whose graph is not built is named and skipped, and the status is COMPLETE only if every step ran.
    """
    encoder, bank = await routing_resources()
    plan = await route_plan(query, encoder=encoder, bank=bank, facts=SceneFacts(await finest_resolution(scene_directory)))
    render_plan(plan, console, encoder is not None)
    status = RunStatus.COMPLETE
    for index, decision in enumerate(plan.steps, start=1):
        if len(plan.steps) > 1:
            console.print(f"\n  [dim]run {index}/{len(plan.steps)}: {escape(decision.query)}[/dim]")
        if decision.refusal:
            status = RunStatus.FAILED
            continue
        if decision.graph is not GraphName.INDEX_QUERY:
            console.print(f"\n  {decision.intent.value} is routed to a graph this phase has not built ({escape(decision.graph_note or '')}).")
            status = RunStatus.FAILED
            continue
        if await _run_index_query(decision, scene_directory, declared_level, console) is not RunStatus.COMPLETE:
            status = RunStatus.FAILED
    return status


async def _run_index_query(decision: RoutingDecision, scene_directory: Path, declared_level: ProcessingLevel | None, console: Console) -> RunStatus:
    query = decision.query
    target = await resolve_index_target(decision.entities.spectral_phrase or query)
    console.print(
        f"\n  {escape(query)!s}  ->  {target.index.value.upper()}"
        + (f" in [{target.lower:.2f}, {target.upper:.2f}] ({escape(target.label)})" if target.has_range else " (map only)")
    )
    outcome = await run_index_query(
        scene_directory=scene_directory, query=query, target=target, intent=decision.intent, declared_level=declared_level, console=console
    )
    console.print(f"\n  journal  {escape(str(outcome.journal))}")
    for path in outcome.figures:
        console.print(f"  figure   {escape(str(path))}")
    if outcome.status is RunStatus.COMPLETE:
        _print_measurement(outcome.values, console)
        _print_evidence(outcome.values, console)
    return outcome.status


def _print_evidence(values: dict[str, object], console: Console) -> None:
    """The claims, what each rests on, and where the run's record went."""
    claims = values.get("claims") or []
    layers = {layer["id"]: layer for layer in values.get("layers") or []}
    evidence = {item["id"]: item for item in values.get("evidence_items") or []}
    if claims:
        console.print()
    for claim in claims:
        marker = "primary" if claim["isPrimary"] else "supporting"
        console.print(f"  [bold]claim[/bold] {escape(claim['id'])}  {marker}  {escape(claim['kind'])}")
        console.print(f"    {escape(claim['text'])}")
        for evidence_id in claim["evidenceIds"]:
            item = evidence.get(evidence_id)
            if item is None:
                continue
            layer = layers.get(item["layerId"] or "")
            where = (
                f"{len(item['featureIds'])} features on {escape(layer['title'])}" if layer else "a statistic, no layer"
            )
            console.print(f"    evidence {escape(evidence_id)}  {escape(item['kind'])}  {where}")
    for key, label in (("provenance_path", "provenance"), ("evidence_graph_path", "evidence")):
        path = values.get(key)
        if path:
            console.print(f"  {label:10s} {escape(str(path))}")


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
