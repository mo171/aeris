"""Two dates, one ground: the graph that measures alignment, refuses above tolerance, and only then asks what changed.

what  : `build_temporal_graph()` and `AFTER_CHANGE_BY_INTENT`, the table that decides whether the pair's
        S14 reads the comparison figure or answers the operator's question over the two pictures.
where : Registered in `graphs/__init__.py` as `GraphName.TEMPORAL`; run by `services/pipeline/runner.py`
        for CHANGE_DETECT and CHANGE_VQA.
how   : S1 -> (S7) -> S9 -> S13 -> S15 -> [S14 read | S14 answer] -> S16 -> S18 -> S19.

        **S9 stands between the inputs and the model, always.** `architecture-context.md` §8 rule 2: the
        co-registration residual gates the comparison, and a residual above tolerance ends the run with
        the number in the error rather than lowering a confidence. The stage is in the graph, not
        inside S13, so the trace shows the measurement as its own row and a resumed run after S9 does
        not re-measure.

        **The two intents share the measurement.** "What changed" (CHANGE_DETECT) reads the comparison
        figure the measurement drew; "has the port expanded?" (CHANGE_VQA) puts the question to the model
        over both pictures *and* keeps the measured change as supporting claims, so the model's yes or no
        sits beside hectares it did not invent. The table `AFTER_CHANGE_BY_INTENT` is that choice.

        The radar pair is refused by name at S13 (`CHANGE_DETECTORS_BY_MODALITY`); the graph shape is the
        same when 1.11 fills the entry.
"""

from typing import Final

from langgraph.graph import END, START, StateGraph

from app.constants.intents import Intent
from app.constants.scenes import SceneModality
from app.services.imagery.frames import InputKind
from app.services.pipeline.nodes.answer_generation import generate_answer
from app.services.pipeline.nodes.change_detection import coregister_pair, detect_change_node, localise_change
from app.services.pipeline.nodes.cloud_handling import handle_clouds
from app.services.pipeline.nodes.confidence_estimation import estimate_confidence
from app.services.pipeline.nodes.input_validation import validate_inputs
from app.services.pipeline.nodes.provenance_logging import log_provenance
from app.services.pipeline.nodes.vlm_reading import answer_question_node, read_figure
from app.services.pipeline.state import AnalysisState

# Intent -> the S14 that follows the measured change.
AFTER_CHANGE_BY_INTENT: Final[dict[Intent, str]] = {
    Intent.CHANGE_DETECT: "read_figure",
    Intent.CHANGE_VQA: "answer_question",
}
CLOUD_STAGE: Final[str] = "handle_clouds"
GATE_STAGE: Final[str] = "coregister_pair"


def after_inputs(state: AnalysisState) -> str:
    if state.get("input_kind") == InputKind.SCENE_DIRECTORY.value and state.get("modality") == SceneModality.OPTICAL.value:
        return CLOUD_STAGE
    return GATE_STAGE


def after_change(state: AnalysisState) -> str:
    return AFTER_CHANGE_BY_INTENT[Intent(state["intent"])]


def build_temporal_graph() -> StateGraph:
    """The uncompiled graph; the caller compiles it with its checkpointer and store."""
    builder: StateGraph = StateGraph(AnalysisState)
    builder.add_node("validate_inputs", validate_inputs)
    builder.add_node(CLOUD_STAGE, handle_clouds)
    builder.add_node(GATE_STAGE, coregister_pair)
    builder.add_node("detect_change", detect_change_node)
    builder.add_node("localise_change", localise_change)
    builder.add_node("read_figure", read_figure)
    builder.add_node("answer_question", answer_question_node)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("estimate_confidence", estimate_confidence)
    builder.add_node("log_provenance", log_provenance)

    builder.add_edge(START, "validate_inputs")
    builder.add_conditional_edges("validate_inputs", after_inputs, {CLOUD_STAGE: CLOUD_STAGE, GATE_STAGE: GATE_STAGE})
    builder.add_edge(CLOUD_STAGE, GATE_STAGE)
    builder.add_edge(GATE_STAGE, "detect_change")
    builder.add_edge("detect_change", "localise_change")
    builder.add_conditional_edges("localise_change", after_change, {name: name for name in sorted(set(AFTER_CHANGE_BY_INTENT.values()))})
    builder.add_edge("read_figure", "generate_answer")
    builder.add_edge("answer_question", "generate_answer")
    builder.add_edge("generate_answer", "estimate_confidence")
    builder.add_edge("estimate_confidence", "log_provenance")
    builder.add_edge("log_provenance", END)
    return builder
