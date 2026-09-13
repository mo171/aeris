"""One picture, one question: the graph that routes an intent to its specialist and every branch through the same evidence, answer and record.

what  : `build_single_image_graph()` and the two routing tables, `FIRST_STAGE_BY_INTENT` and
        `LOCALISER_BY_STAGE`.
where : Registered in `graphs/__init__.py` as `GraphName.SINGLE_IMAGE`; run by `services/pipeline/runner.py`
        for the CLI and the agent. Replaces the 1.4 index-query graph, which is now the INDEX_QUERY branch
        of this one.
how   : S1 -> (S7) -> [S12 -> S15 | S13 -> S15 | S13 -> S15 | S14] -> S14 -> S16 -> S18 -> S19.

        **Routing is a table, expressed as conditional edges** (PDF p.24; `constants/routing.py` chooses
        the graph, this file chooses the branch inside it). `add_conditional_edges` is given a function
        that reads one key of the state and a dictionary from what it returns to a node name; the
        function decides nothing that is not already in the state, and the dictionary is the whole
        vocabulary of where a run can go. An intent with no entry fails at graph construction, not at
        the operator's question.

        **S7 runs when there is a scene to mask and is not announced when there is not.** A picture has
        no classification layer; the edge after S1 sends it straight to its specialist rather than
        through a stage that would report "no mask" about a file that never had one.

        **Every branch converges on S14 -> S16 -> S18 -> S19.** The reading, the answer, the confidence
        and the record are one code path for a count, a hectare and a caption, which is what lets the
        agent phrase all three through one guard and the report cite all three the same way. The
        perception branch (SCENE_VQA) has S14 as its specialist and skips the second reading: its
        claim *is* the model's words.

        Every arrow is a checkpoint, so a run killed after S13 resumes at S15 and reads the artefact S13
        retained rather than recomputing it. Returned uncompiled, like the probe graph: the caller
        supplies the checkpointer and the store.
"""

from typing import Final

from langgraph.graph import END, START, StateGraph

from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.scenes import SceneModality
from app.services.imagery.frames import InputKind
from app.services.pipeline.nodes.answer_generation import generate_answer
from app.services.pipeline.nodes.cloud_handling import handle_clouds
from app.services.pipeline.nodes.confidence_estimation import estimate_confidence
from app.services.pipeline.nodes.evidence_localisation import localise_evidence
from app.services.pipeline.nodes.feature_extraction import extract_features
from app.services.pipeline.nodes.input_validation import validate_inputs
from app.services.pipeline.nodes.object_detection import detect_objects_node, localise_detections
from app.services.pipeline.nodes.provenance_logging import log_provenance
from app.services.pipeline.nodes.segmentation import localise_classes, segment_land_cover
from app.services.pipeline.nodes.vlm_reading import answer_question_node, read_figure
from app.services.pipeline.state import AnalysisState

# Intent -> the node that starts its specialist branch. Every intent this graph answers is listed; the
# routing table in `constants/routing.py` sends nothing else here. GROUND is the one intent with two
# specialists - the detector for a class it knows, the VLM for a phrase it does not ("where is the
# stadium?") - and the router's choice travels in the state as `tool`.
FIRST_STAGE_BY_INTENT: Final[dict[Intent, str]] = {
    Intent.INDEX_QUERY: "extract_features",
    Intent.DETECT: "detect_objects",
    Intent.GROUND: "detect_objects",
    Intent.SEGMENT: "segment_land_cover",
    Intent.SCENE_VQA: "answer_question",
}
GROUND_STAGE_BY_TOOL: Final[dict[str, str]] = {
    ModelId.DOTA_DETECTOR.value: "detect_objects",
    ModelId.REMOTE_SENSING_VLM.value: "answer_question",
}
# Specialist node -> the S15 that binds its output to ground. The perception branch has none.
LOCALISER_BY_STAGE: Final[dict[str, str]] = {
    "extract_features": "localise_evidence",
    "detect_objects": "localise_detections",
    "segment_land_cover": "localise_classes",
}
CLOUD_STAGE: Final[str] = "handle_clouds"


def first_stage(state: AnalysisState) -> str:
    """The branch the intent names. Reads the state; decides nothing the router did not."""
    intent = Intent(state["intent"])
    if intent is Intent.GROUND and state.get("tool") in GROUND_STAGE_BY_TOOL:
        return GROUND_STAGE_BY_TOOL[str(state["tool"])]
    return FIRST_STAGE_BY_INTENT[intent]


def after_inputs(state: AnalysisState) -> str:
    """S7 for an optical scene directory - the only input with a mask source - else the branch itself."""
    if state.get("input_kind") == InputKind.SCENE_DIRECTORY.value and state.get("modality") == SceneModality.OPTICAL.value:
        return CLOUD_STAGE
    return first_stage(state)


def build_single_image_graph() -> StateGraph:
    """The uncompiled graph. Compiling is the caller's job, because that is where the checkpointer is."""
    builder: StateGraph = StateGraph(AnalysisState)
    builder.add_node("validate_inputs", validate_inputs)
    builder.add_node(CLOUD_STAGE, handle_clouds)
    builder.add_node("extract_features", extract_features)
    builder.add_node("localise_evidence", localise_evidence)
    builder.add_node("detect_objects", detect_objects_node)
    builder.add_node("localise_detections", localise_detections)
    builder.add_node("segment_land_cover", segment_land_cover)
    builder.add_node("localise_classes", localise_classes)
    builder.add_node("answer_question", answer_question_node)
    builder.add_node("read_figure", read_figure)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("estimate_confidence", estimate_confidence)
    builder.add_node("log_provenance", log_provenance)

    branches = sorted(set(FIRST_STAGE_BY_INTENT.values()) | set(GROUND_STAGE_BY_TOOL.values()))
    builder.add_edge(START, "validate_inputs")
    builder.add_conditional_edges("validate_inputs", after_inputs, {name: name for name in (CLOUD_STAGE, *branches)})
    builder.add_conditional_edges(CLOUD_STAGE, first_stage, {name: name for name in branches})
    for specialist, localiser in LOCALISER_BY_STAGE.items():
        builder.add_edge(specialist, localiser)
        builder.add_edge(localiser, "read_figure")
    builder.add_edge("answer_question", "generate_answer")
    builder.add_edge("read_figure", "generate_answer")
    builder.add_edge("generate_answer", "estimate_confidence")
    builder.add_edge("estimate_confidence", "log_provenance")
    builder.add_edge("log_provenance", END)
    return builder
