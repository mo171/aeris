"""Carries one S1-S20 stage's progress, which is the product's credibility signal rather than a progress bar.

what  : `AnalysisTraceStep`, the payload of a `trace-step` event, and `TraceStepEvent` itself.
where : Emitted twice per stage by `services/pipeline/node.py` - once `running`, once terminal - and drawn
        live by `cli/renderers/trace_renderer.py`.
how   : `api-contract.md` §3.1: "Emit every trace step twice - once `running`, then again `completed` with
        `durationMs`. That transition *is* the execution-trace UI, and it is the product's credibility
        signal." A step that only appears once it is finished shows an operator a list of things that
        already happened; a step that appears `running` and then completes shows them a system working.

        The step **id is stable across both emissions** - the frontend keys on it to replace the row rather
        than append a second one. That is why the id is minted before the node runs and carried through,
        instead of being generated at each emission.

        Every field the frontend marks required is required here, including the four nullable ones. Zod's
        `.nullable()` means "present and possibly null", so `exclude_none=True` would drop the keys and the
        frontend would reject the event (0.7 pinned this against `nextCursor`; the same rule applies here).
"""

from typing import Literal

from pydantic import Field

from app.constants.events import AnalysisEventType
from app.constants.stages import PipelineStage
from app.constants.statuses import TraceStepState
from app.schemas.events.base import StreamEvent


class AnalysisTraceStep(StreamEvent):
    """One stage of the pipeline, as the execution trace shows it."""

    id: str
    stage_code: PipelineStage
    state: TraceStepState

    # Free text for the operator - "co-registering 2 scenes at 10 m". Null while a step is still `pending`.
    detail: str | None = None

    # Null until the step reaches a terminal state. Set from a monotonic clock, never from wall time: a
    # duration measured across an NTP correction is how a stage comes to report a negative number of
    # milliseconds.
    duration_ms: int | None = Field(default=None, ge=0)

    # Which specialist produced this step's output, where one did. `api-contract.md` §1 rule 4 - the wire
    # carries the code (`changeformer`), never the display name.
    model_id: str | None = None
    model_version: str | None = None

    # The artefact this stage left behind, for the stages that leave one (`ARTEFACT_PRODUCING_STAGES`).
    # `api-contract.md` §1 rule 10: an operator can click it, so a missing URI is a dead end in the
    # interface rather than a silent omission.
    artefact_layer_id: str | None = None


class TraceStepEvent(StreamEvent):
    """`trace-step` on the analysis stream."""

    type: Literal[AnalysisEventType.TRACE_STEP] = AnalysisEventType.TRACE_STEP
    run_id: str
    step: AnalysisTraceStep
