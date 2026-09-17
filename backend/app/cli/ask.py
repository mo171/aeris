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

        The picture is read by `services/imagery/frames.py` - the one door every specialist's picture
        comes through (1.10): PNG and JPEG as they are, a (Geo)TIFF's first three bands stretched with
        the fixed Sentinel-2 window when they are reflectance. `--sar` marks a picture as radar so the
        model is told what it is looking at.
"""

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
from app.services.imagery.frames import inspect_input, read_rgb_frame
from app.services.prompts.vlm import SAR_IMAGE_NOTE
from app.services.vlm.reading import Reading, answer_question, describe_image, read_pair

# What `ask` can do without a scene. Everything else is named with where it is answered.
ASK_INTENTS = frozenset({Intent.SCENE_VQA, Intent.GROUND, Intent.DETECT, Intent.CHANGE_VQA})


async def execute_ask(
    *, images: list[Path], question: str | None, sar: list[bool], console: Console, force_vlm: bool = False
) -> bool:
    """One or two pictures and a question - or no question, for a caption."""
    pictures = [await read_picture(path, is_sar) for path, is_sar in zip(images, sar, strict=True)]
    manager = await get_manager()
    if not question:
        _print_reading(await describe_image(pictures[0], manager=manager, is_sar=sar[0]), console)
        return True
    if force_vlm:
        console.print("  [yellow]router bypassed (--force-vlm): whatever this says is the model's word, not a measurement[/yellow]")
        return await _ask_vlm(pictures, question, sar, manager, console)

    encoder, bank = await routing_resources()
    modalities = tuple(Modality.SAR if flag else Modality.OPTICAL for flag in sar)
    facts = SceneFacts(None, len(pictures), modalities)
    
    from app.lib.llm.chat_model import build_chat_model
    llm = build_chat_model()
    
    from app.agents.harness.agent import run_harness
    console.print("\n  [bold yellow]Using Phase 1.14 Agent Harness...[/bold yellow]")
    try:
        final_answer = await run_harness(question, facts=facts, model=llm, pictures=pictures, sar=sar, manager=manager)
        console.print(f"\n  [bold green]Agent Synthesis:[/bold green]\n  {escape(final_answer)}\n")
        return True
    except Exception as e:
        console.print(f"\n  [bold red]Agent Harness Failed:[/bold red] {escape(str(e))}")
        return False


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


async def read_picture(path: Path, is_sar: bool) -> np.ndarray:
    """An (H, W, 3) 8-bit RGB array of a picture, a (Geo)TIFF or a scene directory - through `frames.py`."""
    frame = await read_rgb_frame(await inspect_input(path, is_sar=is_sar))
    return frame.rgb
