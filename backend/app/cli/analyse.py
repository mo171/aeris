"""Everything `aeris analyse` does - route the question, run the graph each step names over the input, and show what it found.

what  : `execute_analyse()`, the async function behind the one Typer command in `cli/main.py`.
where : Called from `cli/main.py`. The router decides first (1.8): the intent, the specialist and the
        graph, or a refusal that names what the input cannot answer (a car on a 10 m pixel). From 1.10
        the input is a scene directory, a GeoTIFF or a picture, `--before` adds the earlier date of a
        pair, and every step with a graph is run through it.
how   : An adapter and nothing more: the question is routed by `agents/router.py`, the request is built
        by `agents/requests.py`, the work is the graph `services/pipeline/runner.py` runs - the same
        function the agent's tools call, so an operator's run and an agent's run are the same run.

        The measurement is read back from the checkpoint at the end rather than from anything this file
        accumulated, for the reason `run_handle.py` reads the confidence that way: the checkpoint is what
        a resumed run would see, and two sources for one number is how they come to disagree.
"""

import logging
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from app.agents.requests import InputPaths, analysis_request
from app.agents.router import RoutingDecision, SceneFacts, route_plan, routing_resources
from app.cli.route import render_plan
from app.constants.raster import ProcessingLevel
from app.constants.routing import Modality
from app.constants.statuses import RunStatus
from app.lib.exceptions import AerisError
from app.services.imagery.frames import inspect_input
from app.services.pipeline.runner import run_analysis

logger = logging.getLogger(__name__)


async def execute_analyse(
    *,
    scene_directory: Path,
    query: str,
    console: Console,
    declared_level: ProcessingLevel | None = None,
    reference: Path | None = None,
    declared_resolution_metres: float | None = None,
    is_sar: bool = False,
    reference_is_sar: bool = False,
    declared_registered: bool = False,
) -> RunStatus:
    """Route the request, run a graph per step that has one, watch each, and print what it found.

    A request of several questions is several runs, in order, each with its own journal and record; a
    step that is refused is named and skipped, and the status is COMPLETE only if every step ran.
    """
    inputs = InputPaths(
        scene=scene_directory, reference=reference, declared_level=declared_level, declared_resolution_metres=declared_resolution_metres,
        is_sar=is_sar, reference_is_sar=reference_is_sar, declared_registered=declared_registered,
    )
    facts = await _facts(inputs)
    encoder, bank = await routing_resources()
    plan = await route_plan(query, encoder=encoder, bank=bank, facts=facts)
    render_plan(plan, console, encoder is not None)
    status = RunStatus.COMPLETE
    for index, decision in enumerate(plan.steps, start=1):
        if len(plan.steps) > 1:
            console.print(f"\n  [dim]run {index}/{len(plan.steps)}: {escape(decision.query)}[/dim]")
        if decision.refusal:
            status = RunStatus.FAILED
            continue
        if await _run_step(decision, inputs, console) is not RunStatus.COMPLETE:
            status = RunStatus.FAILED
    return status


async def _facts(inputs: InputPaths) -> SceneFacts:
    """What the router may know before a run: the finest resolution, how many inputs, which sensors."""
    paths = [path for path in (inputs.reference, inputs.scene) if path is not None]
    flags = [inputs.reference_is_sar, inputs.is_sar] if inputs.reference is not None else [inputs.is_sar]
    resolution: float | None = None
    modalities: list[Modality] = []
    for path, flag in zip(paths, flags, strict=True):
        try:
            inspected = await inspect_input(path, declared_resolution_metres=inputs.declared_resolution_metres, is_sar=flag)
        except AerisError:
            # The graph refuses an unreadable input with its own message; routing only needs a hint.
            modalities.append(Modality.SAR if flag else Modality.OPTICAL)
            continue
        modalities.append(Modality.SAR if inspected.modality.value == "sar" else Modality.OPTICAL)
        if inspected.resolution_metres is not None:
            resolution = inspected.resolution_metres if resolution is None else min(resolution, inspected.resolution_metres)
    return SceneFacts(resolution, len(paths), tuple(modalities))


async def _run_step(decision: RoutingDecision, inputs: InputPaths, console: Console) -> RunStatus:
    try:
        request = await analysis_request(decision, inputs)
    except AerisError as error:
        console.print(f"\n  [yellow]{escape(str(error))}[/yellow]")
        return RunStatus.FAILED
    console.print(
        f"\n  {escape(decision.query)}  ->  {request.graph.value} / {decision.intent.value}"
        + (f"  {request.target.index.value.upper()}" + (f" in [{request.target.lower:.2f}, {request.target.upper:.2f}] ({escape(request.target.label)})" if request.target.has_range else " (map only)") if request.target else "")
        + (f"  classes {', '.join(request.objects)}" if request.objects else "")
        + (f"  land cover {', '.join(request.classes)}" if request.classes else "")
    )
    outcome = await run_analysis(request, console=console)
    console.print(f"\n  journal  {escape(str(outcome.journal))}")
    for path in outcome.figures:
        console.print(f"  figure   {escape(str(path))}")
    if outcome.status is RunStatus.COMPLETE:
        _print_measurement(outcome.values, console)
        _print_evidence(outcome.values, console)
        if outcome.answer:
            console.print(f"\n  [bold]answer[/bold]  {escape(outcome.answer)}")
    elif outcome.error:
        console.print(f"\n  [red]{outcome.status.value}[/red]  {escape(outcome.error)}")
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
                f"{len(item['featureIds'])} features on {escape(layer['title'])}" if layer else f"{escape(item['kind'])}, no layer"
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
        fractions = values.get("band_fractions") or values.get("class_fractions") or {}
        for label, fraction in fractions.items():
            console.print(f"  {escape(str(label)):28s} {float(fraction):6.1%} of observed ground")
        counts = values.get("detection_counts") or {}
        for label, count in sorted(counts.items(), key=lambda item: -item[1]):
            console.print(f"  {escape(str(label)):28s} {int(count):6d} boxes")
        return

    label = values.get("target_label") or "Change"
    area = measurement.get("areaHectares")
    observed = measurement.get("observedHectares")
    if area is not None and observed is not None:
        console.print(
            f"\n  {escape(str(label))}: [bold]{area:,.2f} ha[/bold]   {measurement['coverageFraction']:.2%} of {observed:,.2f} ha observed"
            f"   {measurement['regionCount']:,} regions   {measurement['pixelCount']:,} px"
        )
    else:
        console.print(
            f"\n  {escape(str(label))}: [bold]{measurement['pixelCount']:,} px[/bold]   {measurement['coverageFraction']:.2%} of observed pixels"
            f"   {measurement['regionCount']:,} regions   (no ground size known)"
        )
    console.print(f"  measured in {escape(str(measurement['equalAreaCrs']))}")
