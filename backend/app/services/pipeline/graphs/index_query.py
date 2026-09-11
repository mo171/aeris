"""The Phase 1.4 vertical slice as a graph: mask, index, region, answer - one optical scene, one question.

what  : `build_index_query_graph()` - S7 -> S12 -> S15 -> S16 over `IndexQueryState`.
where : Registered in `graphs/__init__.py` as `GraphName.INDEX_QUERY`; run by `cli/analyse.py`. Phase
        1.10's `single_image` graph composes these four nodes with S13 and S14 between them.
how   : A straight line, on purpose. The order *is* the scientific rule: the mask exists (S7) before the
        arithmetic runs (S12), the arithmetic exists before anything is thresholded and measured (S15), and
        the measurement exists before a sentence mentions a number (S16). Every arrow is a checkpoint, so a
        run killed after S12 resumes at S15 and reads the index S12 retained rather than recomputing it.

        Returned uncompiled, like the probe graph: the caller supplies the checkpointer and the store.
"""

from langgraph.graph import END, START, StateGraph

from app.services.pipeline.nodes.answer_generation import generate_answer
from app.services.pipeline.nodes.cloud_handling import handle_clouds
from app.services.pipeline.nodes.evidence_localisation import localise_evidence
from app.services.pipeline.nodes.feature_extraction import extract_features
from app.services.pipeline.state import IndexQueryState


def build_index_query_graph() -> StateGraph:
    """The uncompiled S7 -> S12 -> S15 -> S16 graph."""
    builder: StateGraph = StateGraph(IndexQueryState)
    builder.add_node("handle_clouds", handle_clouds)
    builder.add_node("extract_features", extract_features)
    builder.add_node("localise_evidence", localise_evidence)
    builder.add_node("generate_answer", generate_answer)
    builder.add_edge(START, "handle_clouds")
    builder.add_edge("handle_clouds", "extract_features")
    builder.add_edge("extract_features", "localise_evidence")
    builder.add_edge("localise_evidence", "generate_answer")
    builder.add_edge("generate_answer", END)
    return builder
