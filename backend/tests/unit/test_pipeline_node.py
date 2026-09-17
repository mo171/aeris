"""Unit tests for @pipeline_node metadata, graph edges, and parameter resolution."""

from unittest.mock import patch

import pytest

from app.constants.stages import PipelineStage
from app.constants.statuses import TraceStepState
from app.schemas.events.trace import TraceNodeRef, TraceStepEvent
from app.services.pipeline.node import (
    attach_artefact_layer,
    attach_artefact_uri,
    describe_trace_step,
    pipeline_node,
    record_step_inputs,
    record_step_outputs,
    record_step_parameters,
    record_step_rationale,
)


@pytest.mark.asyncio
async def test_pipeline_node_emits_graph_metadata_and_resolved_parameters() -> None:
    """A stage wrapped with @pipeline_node emits full graph edges, operationId, and resolved parameters."""

    @pipeline_node(
        PipelineStage.S13,
        detail="Detecting change between optical dates",
        operation_id="change-detection",
        depends_on=("stp_coregister_s9",),
    )
    async def sample_stage(state: dict[str, object]) -> dict[str, object]:
        record_step_inputs([TraceNodeRef(kind="scene", id="scene_t0"), TraceNodeRef(kind="scene", id="scene_t1")])
        record_step_outputs([TraceNodeRef(kind="layer", id="lyr_change_01")])
        record_step_rationale("Dual optical comparison at 10m")
        record_step_parameters({"local_param": "computed"})
        attach_artefact_layer("lyr_change_01")
        attach_artefact_uri("s3://artefacts/run_test/S13/probability.tif")
        describe_trace_step("Change detected over 42.5 ha")
        return {"result_key": "val"}

    events: list[TraceStepEvent] = []

    with patch("app.services.pipeline.node.emit") as mock_emit:
        mock_emit.side_effect = events.append
        state = {
            "run_id": "run_test_123",
            "parameter_overrides": {
                "change-detection": {"threshold": 0.45},
            },
        }
        update = await sample_stage(state)

    assert update is not None
    assert update.get("result_key") == "val"
    assert "trace_step_ids" in update

    trace_events = [e for e in events if isinstance(e, TraceStepEvent)]
    assert len(trace_events) == 2  # Once running, once completed

    running = trace_events[0].step
    assert running.state == TraceStepState.RUNNING
    assert running.operation_id == "change-detection"
    assert running.depends_on == ["stp_coregister_s9"]
    assert running.parameters.get("threshold") == 0.45

    completed = trace_events[1].step
    assert completed.state == TraceStepState.COMPLETED
    assert completed.operation_id == "change-detection"
    assert completed.depends_on == ["stp_coregister_s9"]
    assert completed.parameters.get("threshold") == 0.45
    assert completed.parameters.get("local_param") == "computed"
    assert len(completed.inputs) == 2
    assert completed.inputs[0].id == "scene_t0"
    assert len(completed.outputs) == 1
    assert completed.outputs[0].id == "lyr_change_01"
    assert completed.rationale == "Dual optical comparison at 10m"
    assert completed.artefact_layer_id == "lyr_change_01"
    assert completed.artefact_uri == "s3://artefacts/run_test/S13/probability.tif"
    assert completed.detail == "Change detected over 42.5 ha"
