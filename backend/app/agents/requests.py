"""Turns a routing decision and the operator's inputs into the one request a graph is run with.

what  : `InputPaths`; `analysis_request()` - a `RoutingDecision` + paths -> `AnalysisRequest`;
        `analysis_request_for_step()` - the same from the agent's `StepRecord`, which is the decision in
        wire form.
where : `cli/analyse.py` and `agents/tools/analysis_tools.py`, so the CLI's run and the agent's run are
        built from the decision the same way.
how   : The decision already names the graph and the intent (tables, `constants/routing.py`); this
        function resolves what the graph's nodes read from the state and nothing decides again: the index
        target from the spectral phrase (INDEX_QUERY), the detector classes and the properties wanted
        (DETECT, GROUND), the land-cover classes from the words (SEGMENT). A SEGMENT question naming a
        thing no class draws ("segment the runways") is refused here by name, before a run starts - the
        same shape as the router's refusals, applied to the vocabulary the router does not hold.
"""

from dataclasses import dataclass
from pathlib import Path

from app.agents.router import RoutingDecision
from app.agents.state import StepRecord
from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
from app.constants.routing import UNBUILT_GRAPH_PHASE
from app.constants.segmentation import LOVEDA_CLASS_NAMES, SEGMENTATION_IGNORE_LABEL
from app.lib.exceptions import InvalidRequestError
from app.services.pipeline.runner import AnalysisRequest
from app.services.segmentation.classes import resolve_landcover_classes, unresolved_landcover_words
from app.services.spectral.indices import resolve_index_target


@dataclass(frozen=True, slots=True)
class InputPaths:
    """Where the operator's inputs are: the primary (or later) one, and the earlier one for a pair."""

    scene: Path
    reference: Path | None = None
    declared_level: ProcessingLevel | None = None
    declared_resolution_metres: float | None = None
    is_sar: bool = False
    reference_is_sar: bool = False
    declared_registered: bool = False


async def analysis_request(decision: RoutingDecision, inputs: InputPaths) -> AnalysisRequest:
    """The request for one routed step. Raises `InvalidRequestError` when the step cannot be built."""
    entities = decision.entities
    return await _build(
        graph=decision.graph, intent=decision.intent, query=decision.query, graph_note=decision.graph_note,
        spectral_phrase=entities.spectral_phrase, objects=tuple(entities.objects), wants_location=entities.wants_location,
        tool=decision.tool.value if decision.tool else None, inputs=inputs,
    )


async def analysis_request_for_step(step: StepRecord, inputs: InputPaths) -> AnalysisRequest:
    """The same request from the agent's step record - the decision as the plan carries it."""
    return await _build(
        graph=GraphName(step["graph"]) if step.get("graph") else None, intent=Intent(step["intent"]), query=step["query"],
        graph_note=None, spectral_phrase=step.get("spectral_phrase"), objects=tuple(step.get("objects") or ()),
        wants_location=bool(step.get("wants_location")), tool=step.get("tool"), inputs=inputs,
    )


async def _build(
    *, graph: GraphName | None, intent: Intent, query: str, graph_note: str | None, spectral_phrase: str | None,
    objects: tuple[str, ...], wants_location: bool, tool: str | None, inputs: InputPaths,
) -> AnalysisRequest:
    if graph is None:
        raise InvalidRequestError(
            f"{intent.value} has no graph: {graph_note or UNBUILT_GRAPH_PHASE.get(intent, 'not planned')}.", details={"intent": intent.value},
        )
    target = None
    classes: tuple[str, ...] = ()
    if intent is Intent.INDEX_QUERY:
        target = await resolve_index_target(spectral_phrase or query)
    if intent is Intent.SEGMENT:
        classes = resolve_landcover_classes(query)
        unresolved = unresolved_landcover_words(query)
        if unresolved and not classes:
            drawable = ", ".join(name.lower() for index, name in enumerate(LOVEDA_CLASS_NAMES) if index != SEGMENTATION_IGNORE_LABEL)
            raise InvalidRequestError(
                f"No land-cover class covers {', '.join(unresolved)}. segformer-landcover draws: {drawable}.",
                details={"unresolved": list(unresolved)},
            )
    return AnalysisRequest(
        graph=graph, query=query, intent=intent, scene=inputs.scene, reference=inputs.reference, declared_level=inputs.declared_level,
        declared_resolution_metres=inputs.declared_resolution_metres, is_sar=inputs.is_sar, reference_is_sar=inputs.reference_is_sar,
        declared_registered=inputs.declared_registered, tool=tool, target=target, objects=objects, classes=classes,
        wants_location=wants_location,
    )
