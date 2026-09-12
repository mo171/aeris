"""The Phase 1.4-1.5 vertical slice as a graph: mask, index, evidence, answer, confidence, record - one optical scene, one question.

what  : `build_index_query_graph()` - S7 -> S12 -> S15 -> S14 -> S16 -> S18 -> S19 over `IndexQueryState`.
where : Registered in `graphs/__init__.py` as `GraphName.INDEX_QUERY`; run by `cli/analyse.py`. Phase
        1.10's `single_image` graph composes these nodes with S13 and S14 between S12 and S15.
how   : A straight line, on purpose. The order *is* the scientific rule: the mask exists (S7) before the
        arithmetic runs (S12); the arithmetic exists before anything is thresholded, measured and bound to
        ground (S15); the claims exist before a sentence mentions a number (S16); every stage has stated
        or declined a confidence before one is aggregated (S18); and everything exists before the record
        of it is written (S19). Every arrow is a checkpoint, so a run killed after S12 resumes at S15 and
        reads the index S12 retained rather than recomputing it.

        Returned uncompiled, like the probe graph: the caller supplies the checkpointer and the store.
"""

from langgraph.graph import END, START, StateGraph

from app.services.pipeline.nodes.answer_generation import generate_answer
from app.services.pipeline.nodes.cloud_handling import handle_clouds
from app.services.pipeline.nodes.confidence_estimation import estimate_confidence
from app.services.pipeline.nodes.evidence_localisation import localise_evidence
from app.services.pipeline.nodes.feature_extraction import extract_features
from app.services.pipeline.nodes.provenance_logging import log_provenance
from app.services.pipeline.nodes.vlm_reading import read_figure
from app.services.pipeline.state import IndexQueryState


def build_index_query_graph() -> StateGraph:
    """The uncompiled S7 -> S12 -> S15 -> S14 -> S16 -> S18 -> S19 graph. S14 reads the figure S15 drew, so it
    follows S15 here although its number is lower; the numbering is the PDF's, the order is the data's."""
    builder: StateGraph = StateGraph(IndexQueryState)
    builder.add_node("handle_clouds", handle_clouds)
    builder.add_node("extract_features", extract_features)
    builder.add_node("localise_evidence", localise_evidence)
    builder.add_node("read_figure", read_figure)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("estimate_confidence", estimate_confidence)
    builder.add_node("log_provenance", log_provenance)
    builder.add_edge(START, "handle_clouds")
    builder.add_edge("handle_clouds", "extract_features")
    builder.add_edge("extract_features", "localise_evidence")
    builder.add_edge("localise_evidence", "read_figure")
    builder.add_edge("read_figure", "generate_answer")
    builder.add_edge("generate_answer", "estimate_confidence")
    builder.add_edge("estimate_confidence", "log_provenance")
    builder.add_edge("log_provenance", END)
    return builder
