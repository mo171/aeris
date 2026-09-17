"""Dependency-aware DAG invalidation for pipeline checkpoint reuse.

what  : Computes which stages in a pipeline DAG must re-execute vs which stages can be skipped
        and reused from a parent checkpoint when parameters change or a re-run from a stage is requested.
where : Called by `services/pipeline/runner.py` before executing an analysis re-run.
how   : Instead of a naive "skip before step N", this module determines the exact invalidation closure:
        - A threshold change (e.g. 0.35 -> 0.45) does not invalidate S1-S9 preprocessing or the raw
          model inference tensor (`change-probability.tif`). It reuses the probability array and only
          re-executes mask slicing, spatial vectorization, area measurement, and answer synthesis.
        - A model or sensor change invalidates model inference and everything downstream.
"""

from dataclasses import dataclass
from typing import Any

from app.constants.pipeline import GraphName
from app.constants.stages import PipelineStage

# The topological order of stages for each standard graph
GRAPH_STAGE_SEQUENCES: dict[GraphName, list[PipelineStage]] = {
    GraphName.TEMPORAL: [
        PipelineStage.S1,
        PipelineStage.S7,
        PipelineStage.S9,
        PipelineStage.S13,
        PipelineStage.S15,
        PipelineStage.S14,
        PipelineStage.S16,
        PipelineStage.S18,
        PipelineStage.S19,
    ],
    GraphName.SINGLE_IMAGE: [
        PipelineStage.S1,
        PipelineStage.S7,
        PipelineStage.S8,
        PipelineStage.S12,
        PipelineStage.S13,
        PipelineStage.S15,
        PipelineStage.S14,
        PipelineStage.S16,
        PipelineStage.S18,
        PipelineStage.S19,
    ],
    GraphName.CROSS_MODAL: [
        PipelineStage.S1,
        PipelineStage.S7,
        PipelineStage.S8,
        PipelineStage.S9,
        PipelineStage.S10,
        PipelineStage.S11,
        PipelineStage.S15,
        PipelineStage.S16,
        PipelineStage.S18,
        PipelineStage.S19,
    ],
}


@dataclass(frozen=True, slots=True)
class InvalidationPlan:
    """The computed invalidation boundary for a pipeline execution."""

    reused_stages: frozenset[PipelineStage]
    invalidated_stages: frozenset[PipelineStage]
    reuse_inference: bool


def compute_invalidation_plan(
    graph: GraphName,
    *,
    rerun_from_stage: PipelineStage | None = None,
    changed_parameters: dict[str, Any] | None = None,
) -> InvalidationPlan:
    """Compute the set of stages to reuse vs re-execute based on DAG dependencies and parameter semantics."""
    sequence = GRAPH_STAGE_SEQUENCES.get(graph, GRAPH_STAGE_SEQUENCES[GraphName.TEMPORAL])
    params = changed_parameters or {}

    # Check for threshold-only changes
    is_threshold_only = False
    all_changed_keys: set[str] = set()
    for stage_or_op, pdict in params.items():
        if isinstance(pdict, dict):
            all_changed_keys.update(pdict.keys())
        else:
            all_changed_keys.add(stage_or_op)

    if all_changed_keys and all_changed_keys.issubset({"threshold", "score_threshold", "confidence_threshold"}):
        is_threshold_only = True

    # Check for model changes
    has_model_change = bool(all_changed_keys.intersection({"model", "model_id", "model_version", "classes"}))

    # If rerun_from_stage is specified, find its position
    if rerun_from_stage is not None and rerun_from_stage in sequence:
        split_idx = sequence.index(rerun_from_stage)
        reused = frozenset(sequence[:split_idx])
        invalidated = frozenset(sequence[split_idx:])
        return InvalidationPlan(
            reused_stages=reused,
            invalidated_stages=invalidated,
            reuse_inference=True,
        )

    if is_threshold_only:
        # Preprocessing (S1, S7, S8, S9) is fully reused
        # S13 is invalidated for slicing, but inference tensor is reused
        # S15 downwards are invalidated
        reused_set: set[PipelineStage] = set()
        invalidated_set: set[PipelineStage] = set()

        for stage in sequence:
            if stage in (PipelineStage.S1, PipelineStage.S7, PipelineStage.S8, PipelineStage.S9):
                reused_set.add(stage)
            else:
                invalidated_set.add(stage)

        return InvalidationPlan(
            reused_stages=frozenset(reused_set),
            invalidated_stages=frozenset(invalidated_set),
            reuse_inference=True,
        )

    if has_model_change:
        # Model change invalidates S13/S12 downwards; preprocessing is kept
        reused_set = set()
        invalidated_set = set()
        for stage in sequence:
            if stage in (PipelineStage.S1, PipelineStage.S7, PipelineStage.S8, PipelineStage.S9):
                reused_set.add(stage)
            else:
                invalidated_set.add(stage)

        return InvalidationPlan(
            reused_stages=frozenset(reused_set),
            invalidated_stages=frozenset(invalidated_set),
            reuse_inference=False,
        )

    # Default fallback: if no overrides, all stages run normally
    return InvalidationPlan(
        reused_stages=frozenset(),
        invalidated_stages=frozenset(sequence),
        reuse_inference=False,
    )
