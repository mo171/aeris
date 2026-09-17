"""Unit tests for DAG dependency-aware invalidation and checkpoint reuse."""

import pytest

from app.constants.pipeline import GraphName
from app.constants.stages import PipelineStage
from app.services.pipeline.invalidation import compute_invalidation_plan


def test_threshold_parameter_change_invalidates_only_downstream_nodes() -> None:
    """Changing 'threshold' from 0.35 to 0.45 preserves preprocessing (S1, S7, S9) and raw model inference."""
    plan = compute_invalidation_plan(
        GraphName.TEMPORAL,
        changed_parameters={"change-detection": {"threshold": 0.45}},
    )

    # Preprocessing is preserved
    assert PipelineStage.S1 in plan.reused_stages
    assert PipelineStage.S7 in plan.reused_stages
    assert PipelineStage.S9 in plan.reused_stages

    # S13 is invalidated for slicing, but raw inference can be reused
    assert PipelineStage.S13 in plan.invalidated_stages
    assert plan.reuse_inference is True

    # S15 (vectorization/measurement), S14 (VLM), S16 (answer), S18 (confidence), S19 (provenance) are invalidated
    assert PipelineStage.S15 in plan.invalidated_stages
    assert PipelineStage.S14 in plan.invalidated_stages
    assert PipelineStage.S16 in plan.invalidated_stages
    assert PipelineStage.S18 in plan.invalidated_stages
    assert PipelineStage.S19 in plan.invalidated_stages


def test_rerun_from_stage_s15_preserves_s1_through_s13() -> None:
    """A re-run explicitly requested from S15 (e.g. region measurement) preserves S1, S7, S9, and full S13."""
    plan = compute_invalidation_plan(
        GraphName.TEMPORAL,
        rerun_from_stage=PipelineStage.S15,
    )

    assert PipelineStage.S1 in plan.reused_stages
    assert PipelineStage.S9 in plan.reused_stages
    assert PipelineStage.S13 in plan.reused_stages
    assert plan.reuse_inference is True

    assert PipelineStage.S15 in plan.invalidated_stages
    assert PipelineStage.S16 in plan.invalidated_stages


def test_model_version_change_invalidates_inference_downwards() -> None:
    """Changing the model version requires re-running model inference (cannot reuse probability tensor)."""
    plan = compute_invalidation_plan(
        GraphName.TEMPORAL,
        changed_parameters={"change-detection": {"model_version": "v2"}},
    )

    # Alignment and preprocessing are still preserved
    assert PipelineStage.S1 in plan.reused_stages
    assert PipelineStage.S9 in plan.reused_stages

    # But inference cannot be reused
    assert plan.reuse_inference is False
    assert PipelineStage.S13 in plan.invalidated_stages
