"""Optical/SAR late fusion: validate, gate, independent branches, then one ledger."""

from langgraph.graph import END, START, StateGraph

from app.services.pipeline.nodes.answer_generation import generate_answer
from app.services.pipeline.nodes.confidence_estimation import estimate_confidence
from app.services.pipeline.nodes.cross_modal import (
    analyse_optical,
    analyse_radar,
    coregister_modalities,
    fuse_modalities,
    validate_cross_modal_inputs,
)
from app.services.pipeline.nodes.provenance_logging import log_provenance
from app.services.pipeline.state import AnalysisState


def build_cross_modal_graph() -> StateGraph:
    builder: StateGraph = StateGraph(AnalysisState)
    builder.add_node("validate_inputs", validate_cross_modal_inputs)
    builder.add_node("coregister_modalities", coregister_modalities)
    builder.add_node("analyse_optical", analyse_optical)
    builder.add_node("analyse_radar", analyse_radar)
    builder.add_node("fuse_modalities", fuse_modalities)
    builder.add_node("generate_answer", generate_answer)
    builder.add_node("estimate_confidence", estimate_confidence)
    builder.add_node("log_provenance", log_provenance)
    builder.add_edge(START, "validate_inputs")
    builder.add_edge("validate_inputs", "coregister_modalities")
    builder.add_edge("coregister_modalities", "analyse_optical")
    builder.add_edge("coregister_modalities", "analyse_radar")
    builder.add_edge("analyse_optical", "fuse_modalities")
    builder.add_edge("analyse_radar", "fuse_modalities")
    builder.add_edge("fuse_modalities", "generate_answer")
    builder.add_edge("generate_answer", "estimate_confidence")
    builder.add_edge("estimate_confidence", "log_provenance")
    builder.add_edge("log_provenance", END)
    return builder
