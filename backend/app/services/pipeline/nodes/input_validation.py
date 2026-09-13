"""S1 - establishes what the run was handed and refuses, by name, what the question cannot be answered from.

what  : `validate_inputs`, the S1 node of the single-image and temporal graphs.
where : First node of every 1.10 graph. Everything after it reads the grid facts it writes
        (`georeferenced`, `crs`, `transform`, `resolution_metres`) rather than reopening the files.
how   : `services/imagery/frames.py` says what each input is; this node says whether that answers the
        question. The refusals are structural, not judgements: an index needs bands and a picture has
        none; a detector trained on optical imagery is not run over radar; a pair must share one grid,
        and a pair in different projections is refused with the command that fixes it rather than
        resampled in silence (§8 rule 2 - alignment is measured at S9, never assumed here); a class
        that spans fewer pixels than the detector can see is refused with both numbers, the same gate
        the router applies at planning, applied again here because a run can be started without a
        router. A refusal is raised - the run ends with `run-error` naming the reason - because a graph
        that continued past a wrong input would produce a plausible answer to a different question.

        The routing table names a graph per intent; this node names the *branch* the graph takes after
        it (`FIRST_STAGE_BY_INTENT` in `graphs/single_image.py`) only through the intent it records, so
        the edge function reads one key and no node decides where to go.
"""

import logging
from pathlib import Path

from app.constants.intents import Intent
from app.constants.routing import MIN_OBJECT_PIXELS, PAIR_INTENTS
from app.constants.scenes import SceneModality
from app.constants.stages import PipelineStage
from app.lib.exceptions import InvalidRequestError
from app.services.imagery.frames import AnalysisInput, InputKind, inspect_input
from app.services.pipeline.node import describe_trace_step, pipeline_node
from app.services.pipeline.state import AnalysisState
from app.services.query.entities import required_ground_sample_distance

logger = logging.getLogger(__name__)

# Intents whose specialist reads optical bands or an optical picture and nothing else.
OPTICAL_ONLY_INTENTS = frozenset({Intent.INDEX_QUERY, Intent.DETECT, Intent.GROUND, Intent.SEGMENT, Intent.CHANGE_DETECT})
# Intents that need a scene directory with named bands, because they compute from reflectance.
BAND_INTENTS = frozenset({Intent.INDEX_QUERY})
# The largest difference between two affine transforms that still counts as one grid: a tenth of a pixel
# in origin and a millionth in scale, because a pair that differs by less was cut from one product.
GRID_ORIGIN_TOLERANCE_PIXELS = 0.1
GRID_SCALE_TOLERANCE = 1e-6


@pipeline_node(PipelineStage.S1, detail="Reading what was handed in")
async def validate_inputs(state: AnalysisState) -> dict[str, object]:
    """S1. Inspect every input, refuse what the question cannot be answered from, record the grid."""
    intent = Intent(state["intent"])
    declared_gsd = state.get("declared_resolution_metres")
    primary = await inspect_input(Path(state["scene_directory"]), declared_resolution_metres=declared_gsd, is_sar=bool(state.get("is_sar")))
    inputs = [primary]
    if state.get("reference_directory"):
        reference = await inspect_input(
            Path(state["reference_directory"]), declared_resolution_metres=declared_gsd, is_sar=bool(state.get("reference_is_sar")),
        )
        inputs.insert(0, reference)
        _require_one_grid(reference, primary)
    elif intent in PAIR_INTENTS:
        raise InvalidRequestError(f"{intent.value} compares two acquisitions and one was given.", details={"intent": intent.value})

    _require_answerable(intent, primary, state)

    describe_trace_step(
        "; ".join(one.describe() for one in inputs)
        + (f"; {state['declared_level']} declared" if state.get("declared_level") else "")
        + (" - a picture: figures and pixel claims, nothing placed on the globe" if not primary.georeferenced else "")
    )
    return {
        "input_records": [one.to_wire() for one in inputs],
        "scene_id": primary.scene_id,
        "georeferenced": primary.georeferenced,
        "crs": primary.crs,
        "transform": list(primary.transform),
        "resolution_metres": primary.resolution_metres,
        "resolution_declared": primary.resolution_declared,
        "input_kind": primary.kind.value,
        "modality": primary.modality.value,
    }


def _require_answerable(intent: Intent, primary: AnalysisInput, state: AnalysisState) -> None:
    if intent in BAND_INTENTS and primary.kind is not InputKind.SCENE_DIRECTORY:
        raise InvalidRequestError(
            f"{intent.value} computes from named bands (red, near-infrared, ...) and {primary.path.name} is a "
            f"{primary.kind.value} with none. Point --scene at a scene directory.",
            details={"intent": intent.value, "kind": primary.kind.value},
        )
    if intent in OPTICAL_ONLY_INTENTS and primary.modality is SceneModality.SAR:
        raise InvalidRequestError(
            f"{intent.value}'s specialist reads optical imagery and {primary.scene_id} is radar. The radar branch is "
            "1.11's; a perception question (SCENE_VQA) can be asked of a radar picture now.",
            details={"intent": intent.value, "modality": primary.modality.value},
        )
    if intent in (Intent.DETECT, Intent.GROUND) and primary.resolution_metres is not None:
        for class_name in state.get("objects") or []:
            needed = required_ground_sample_distance(class_name)
            if primary.resolution_metres > needed:
                raise InvalidRequestError(
                    f"A {class_name} spans fewer than {MIN_OBJECT_PIXELS} pixels at {primary.resolution_metres:g} m per pixel; "
                    f"detecting one needs {needed:.2g} m or finer. The detector would run and report zero, which is not an answer.",
                    details={"class": class_name, "resolutionMetres": primary.resolution_metres, "neededMetres": needed},
                )


def _require_one_grid(reference: AnalysisInput, primary: AnalysisInput) -> None:
    if reference.shape != primary.shape:
        raise InvalidRequestError(
            f"The two dates are {reference.width}x{reference.height} and {primary.width}x{primary.height}; a comparison "
            "needs one grid. Reproject the earlier date onto the later one first (aeris preprocess reproject).",
            details={"referenceShape": list(reference.shape), "primaryShape": list(primary.shape)},
        )
    if reference.modality is not primary.modality:
        raise InvalidRequestError(
            f"The two dates are {reference.modality.value} and {primary.modality.value}; a change model compares one sensor "
            "with itself. Two sensors over one ground is CROSS_MODAL (1.11).",
            details={"referenceModality": reference.modality.value, "primaryModality": primary.modality.value},
        )
    if reference.georeferenced != primary.georeferenced:
        raise InvalidRequestError(
            "One date is georeferenced and the other is a picture; a comparison needs both on one grid or neither.",
            details={"referenceCrs": reference.crs, "primaryCrs": primary.crs},
        )
    if reference.georeferenced and primary.georeferenced:
        if reference.crs != primary.crs:
            raise InvalidRequestError(
                f"The two dates are in {reference.crs} and {primary.crs}; reproject the earlier date onto the later "
                "one first (aeris preprocess reproject). Nothing is resampled silently here.",
                details={"referenceCrs": reference.crs, "primaryCrs": primary.crs},
            )
        a, b, c, d, e, f = reference.transform
        a2, b2, c2, d2, e2, f2 = primary.transform
        scale = max(abs(a), abs(e))
        if any(abs(x - y) > GRID_SCALE_TOLERANCE * max(1.0, abs(x)) for x, y in ((a, a2), (b, b2), (d, d2), (e, e2))) or (
            abs(c - c2) > GRID_ORIGIN_TOLERANCE_PIXELS * scale or abs(f - f2) > GRID_ORIGIN_TOLERANCE_PIXELS * scale
        ):
            raise InvalidRequestError(
                "The two dates share a CRS and a shape but not a grid origin or pixel size; reproject the earlier date "
                "onto the later one first (aeris preprocess reproject).",
                details={"referenceTransform": list(reference.transform), "primaryTransform": list(primary.transform)},
            )
