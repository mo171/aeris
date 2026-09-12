"""Everything `aeris ask` does - route the question, then put the picture in front of the specialist the router chose.

what  : `execute_ask()`, the async function behind the Typer command in `cli/main.py`; `read_picture()`.
where : Called from `cli/main.py`. The 1.7 gate (*single-image question and answer in the CLI*) and, from
        1.8, the place the routing decision is exercised without a scene: `aeris ask` is the router plus
        one model, no run, no claims, and says so. 1.10's single-image graph wraps the same services with
        a trace and a provenance record.
how   : The router (`agents/router.py`) decides first. A count or a detection goes to `dota-detector`,
        which counts the boxes it kept and states its mean score - the VLM is not asked, because its
        counts are not measurements (0.23 accuracy, 1.7). A perception question goes to the VLM; a
        two-image change question goes to the VLM over the pair. Anything that needs a scene or a graph
        (an index, a segmentation, a change map, cross-modal) is named as such with the command or phase
        that answers it, rather than being answered badly here. `--force-vlm` bypasses the router so the
        two answers can be put side by side; the output says the router was bypassed.

        PNG and JPEG are read as they are; a TIFF or GeoTIFF is read through rasterio, its first three
        bands taken as red, green, blue, and stretched with the fixed Sentinel-2 window when the values
        are reflectance rather than bytes - the same stretch the training renders used. `--sar` marks a
        picture as radar so the model is told what it is looking at.
"""

import asyncio
from pathlib import Path

import numpy as np
from rich.console import Console
from rich.markup import escape

from app.agents.router import RoutingDecision, SceneFacts, route_plan, routing_resources
from app.cli.route import render_plan
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.routing import Modality
from app.models.manager import ModelManager, get_manager
from app.services.detection.detector import ObjectDetectionResult, detect_objects
from app.services.prompts.vlm import SAR_IMAGE_NOTE
from app.services.vlm.math.rendering import S2_REFLECTANCE_WINDOW, render_s1_false_colour, render_s2_true_colour
from app.services.vlm.reading import Reading, answer_question, describe_image, read_pair

# What `ask` can do without a scene. Everything else is named with where it is answered.
ASK_INTENTS = frozenset({Intent.SCENE_VQA, Intent.GROUND, Intent.DETECT, Intent.CHANGE_VQA})


async def execute_ask(
    *, images: list[Path], question: str | None, sar: list[bool], console: Console, force_vlm: bool = False
) -> bool:
    """One or two pictures and a question - or no question, for a caption."""
    pictures = [await asyncio.to_thread(read_picture, path, is_sar) for path, is_sar in zip(images, sar, strict=True)]
    manager = await get_manager()
    if not question:
        _print_reading(await describe_image(pictures[0], manager=manager, is_sar=sar[0]), console)
        return True
    if force_vlm:
        console.print("  [yellow]router bypassed (--force-vlm): whatever this says is the model's word, not a measurement[/yellow]")
        return await _ask_vlm(pictures, question, sar, manager, console)

    encoder, bank = await routing_resources()
    modalities = tuple(Modality.SAR if flag else Modality.OPTICAL for flag in sar)
    plan = await route_plan(question, encoder=encoder, bank=bank, facts=SceneFacts(None, len(pictures), modalities))
    render_plan(plan, console, encoder is not None)

    # Every step is answered in order; one that cannot be is said so, and the rest still run. The command
    # exits non-zero if any step was refused or needs a graph, so a script sees a partial answer as partial.
    answered = True
    for index, decision in enumerate(plan.steps, start=1):
        if len(plan.steps) > 1:
            console.print(f"\n  [dim]answer {index}/{len(plan.steps)}: {escape(decision.query)}[/dim]")
        answered &= await _answer_step(decision, pictures, sar, manager, console)
    return answered


async def _answer_step(decision: RoutingDecision, pictures: list[np.ndarray], sar: list[bool], manager: ModelManager, console: Console) -> bool:
    if decision.intent not in ASK_INTENTS:
        hint = "`aeris analyse --scene <dir> --query ...`" if decision.intent == Intent.INDEX_QUERY else decision.graph_note
        console.print(f"\n  {decision.intent.value} needs a scene and a graph, not a picture: {escape(hint or '')}")
        return False
    if decision.refusal:
        if decision.intent == Intent.DETECT and decision.entities.unknown_objects:
            # The count is refused; presence is what the VLM can say (0.85 on RSVQA-LR presence, 1.7).
            named = " and ".join(decision.entities.unknown_objects)
            reading = await answer_question(pictures[0], f"Are there any {named} in this image?", manager=manager, is_sar=sar[0])
            console.print(f"\n  presence only, not a count - the model says: [bold]{escape(reading.text)}[/bold]  ({escape(reading.model_version)})")
        return False
    if decision.tool == ModelId.DOTA_DETECTOR:
        result = await detect_objects(pictures[0], manager=manager)
        _print_detection(decision, result, console)
        return True
    return await _ask_vlm(pictures, decision.query, sar, manager, console)


async def _ask_vlm(pictures: list[np.ndarray], question: str, sar: list[bool], manager: ModelManager, console: Console) -> bool:
    if len(pictures) == 2:
        notes = tuple(SAR_IMAGE_NOTE if flag else None for flag in sar)
        reading = await read_pair(pictures[0], pictures[1], question, manager=manager, notes=notes)  # type: ignore[arg-type]
    else:
        reading = await answer_question(pictures[0], question, manager=manager, is_sar=sar[0])
    _print_reading(reading, console)
    return True


def _print_reading(reading: Reading, console: Console) -> None:
    console.print(f"\n  [bold]{escape(reading.text)}[/bold]\n")
    console.print(
        f"  model {escape(reading.model_version)}   {reading.latency_ms} ms   "
        f"model-stated certainty in its wording {reading.confidence:.2f}   images {reading.image_count}"
    )
    if "unadapted" in reading.model_version:
        console.print("  [yellow]no remote-sensing adapter is attached (VLM_ADAPTER_REPOSITORY); this is the base model[/yellow]")


def _print_detection(decision: RoutingDecision, result: ObjectDetectionResult, console: Console) -> None:
    """Counts per asked-for class - every class when none was named - and, for a grounding, the boxes."""
    asked = decision.entities.objects or tuple(name for name in result.class_names if result.count(name))
    console.print()
    for class_name in asked:
        console.print(f"  [bold]{result.count(class_name)}[/bold] {class_name}" + ("s" if result.count(class_name) != 1 else ""))
    # What else the detector saw, so a zero is read beside the four things it did find.
    others = {name: result.count(name) for name in result.class_names if name not in asked and result.count(name)}
    if others:
        console.print("  also found: " + ", ".join(f"{count} {name}" for name, count in others.items()))
    if decision.intent == Intent.GROUND or decision.entities.wants_location:
        wanted = {result.class_names.index(name) for name in asked}
        for box in sorted((b for b in result.boxes if b.class_index in wanted), key=lambda b: -b.confidence)[:10]:
            centre = box.corners.mean(axis=0)
            console.print(f"    {result.class_names[box.class_index]:18s} score {box.confidence:.2f}  centre ({centre[0]:.0f}, {centre[1]:.0f}) px")
    scored = f"mean score {result.confidence:.2f}" if result.confidence is not None else "nothing found, so no score"
    console.print(f"\n  model {escape(result.model_version)}   {result.latency_ms} ms   {len(result.boxes)} boxes kept   {scored}")
    console.print("  a count of boxes the detector kept, each with its own score - the VLM was not asked")


def read_picture(path: Path, is_sar: bool) -> np.ndarray:
    """An (H, W, 3) 8-bit RGB array from a PNG/JPEG, or from the first bands of a (Geo)TIFF."""
    if path.suffix.lower() in {".tif", ".tiff"}:
        import rasterio

        with rasterio.open(path) as dataset:
            bands = dataset.read(list(range(1, min(dataset.count, 3) + 1))).astype(np.float32)
        if is_sar:
            vv = bands[0]
            vh = bands[1] if bands.shape[0] > 1 else bands[0]
            return render_s1_false_colour(vv, vh, already_decibels=bool(np.nanmax(vv) <= 0))
        if bands.shape[0] < 3:
            bands = np.repeat(bands[:1], 3, axis=0)
        if np.nanmax(bands) > 255 or np.nanmax(bands) <= S2_REFLECTANCE_WINDOW[1] / 10_000:
            scale = 10_000.0 if np.nanmax(bands) <= 1.0 else 1.0
            return render_s2_true_colour(bands[0] * scale, bands[1] * scale, bands[2] * scale)
        return np.moveaxis(bands, 0, -1).clip(0, 255).astype(np.uint8)
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))
