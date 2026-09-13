"""The agent's wire objects: the plan the operator approves and the trace steps the assistant stream carries.

what  : `AnalysisPlanStep`, `AnalysisPlan` (`analysisPlanSchema`), `AgentTraceStep` (`executionTraceStepSchema`).
where : `agents/planner.py` builds the plan; `agents/graph.py` returns it through `interrupt()`; the CLI
        prints it; Phase 2's `/plan` route returns it as is. `tests/contracts/test_wire_payloads.py`
        validates each against the frontend's schema.
how   : Transcribed from `features/investigation/schemas/analysis.schema.ts` and
        `features/missionCommand/schemas/assistant.schema.ts`, field for field. A plan step is one
        specialist run: its `modelId` is the fleet member and `stageCode` the stage that runs it, so the
        frontend can draw the plan on the S1-S20 spine it already renders. `isEnabled` is the operator's
        to change, and only that - a plan comes back with the same steps, some struck out.
"""

from typing import Literal

from app.constants.stages import PipelineStage
from app.constants.statuses import TraceStepState
from app.lib.responses import CamelCaseModel


class AnalysisPlanStep(CamelCaseModel):
    id: str
    title: str
    description: str
    model_id: str
    stage_code: PipelineStage
    is_enabled: bool = True


class AnalysisPlan(CamelCaseModel):
    id: str
    summary: str
    steps: list[AnalysisPlanStep]


class AgentTraceStep(CamelCaseModel):
    """`executionTraceStepSchema`: the assistant stream's trace step - a label, not an S-code."""

    id: str
    label: str
    detail: str | None
    state: TraceStepState
    duration_ms: int | None
    model_id: str | None


# The stage each intent's specialist runs at, for the plan the frontend draws on its S1-S20 spine.
PLAN_STAGES: dict[str, PipelineStage] = {
    "INDEX_QUERY": PipelineStage.S12,
    "DETECT": PipelineStage.S13,
    "SEGMENT": PipelineStage.S13,
    "CHANGE_DETECT": PipelineStage.S13,
    "CROSS_MODAL": PipelineStage.S13,
    "SCENE_VQA": PipelineStage.S14,
    "GROUND": PipelineStage.S14,
    "CHANGE_VQA": PipelineStage.S14,
    "EVIDENCE_RECALL": PipelineStage.S15,
}

# What the plan says a step with no fleet model runs on: evidence recall reads the record, no inference.
NO_MODEL: Literal["evidence-store"] = "evidence-store"

