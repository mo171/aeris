"""What the agent carries from understanding a request to answering it - data only, checkpointed between nodes.

what  : `AgentState`, `StepRecord`, `StepResult`, and `describe_step()` / `restore_step()` between a
        `RoutingDecision` and its checkpointable form.
where : `agents/graph.py`. The same rule as `services/pipeline/state.py`: a checkpoint holds data, never
        Python objects, so a routing decision is stored as the dictionary the CLI would print and rebuilt
        from it when a tool needs the pieces.
how   : One thread per conversation (`agent_id`, a `ses_` identifier). `results` accumulate across every
        request on the thread - that is the evidence store EVIDENCE_RECALL reads: what this conversation
        found earlier, by request, with the run ids that hold the record on disk. Everything else is per
        request and overwritten when the next one arrives.
"""

from operator import add
from typing import Annotated, Any, TypedDict

from app.agents.router import RoutingDecision


class StepRecord(TypedDict, total=False):
    """A routing decision as data: what the plan node shows and the execute node dispatches on."""

    id: str
    query: str
    intent: str
    tool: str | None
    graph: str | None
    method: str
    rule: str | None
    refusal: str | None
    objects: list[str]
    unknown_objects: list[str]
    spectral_phrase: str | None
    wants_count: bool
    wants_location: bool
    wants_area: bool


class StepResult(TypedDict, total=False):
    """What one executed step produced - claims in wire form, so synthesis phrases them like S16 does."""

    request_id: str
    step_id: str
    intent: str
    tool: str | None
    query: str
    state: str
    detail: str | None
    claims: list[dict[str, Any]]
    # Where recalled claims came from - the record, not the answer: run id, claim and evidence counts.
    provenance: dict[str, Any]
    evidence_ids: list[str]
    layer_ids: list[str]
    run_id: str | None
    journal: str | None
    figures: list[str]
    latency_ms: int


class AgentState(TypedDict, total=False):
    agent_id: str
    request_id: str
    request: str
    # Inputs the operator gave with the request. Paths as strings.
    scene_directory: str | None
    # The earlier date of a scene pair (1.10), and the operator's word that the pair is co-registered.
    reference_directory: str | None
    declared_registered: bool
    image_paths: list[str]
    sar: list[bool]
    declared_level: str | None
    ground_sample_distance: float | None

    # understand
    clauses: list[str]
    steps: list[StepRecord]
    encoder_loaded: bool
    # plan (the `analysisPlanSchema` wire object) and who wrote its prose
    plan: dict[str, Any]
    plan_source: str
    approved_step_ids: list[str] | None
    # execute: every request's results on this thread, newest last
    results: Annotated[list[StepResult], add]
    # synthesise
    answer: str
    answer_source: str
    ui_commands: list[dict[str, Any]]
    # the assistant stream's trace, `executionTraceStepSchema` in wire form
    trace: Annotated[list[dict[str, Any]], add]


def describe_step(index: int, decision: RoutingDecision) -> StepRecord:
    entities = decision.entities
    return StepRecord(
        id=f"step-{index}", query=decision.query, intent=decision.intent.value, tool=decision.tool.value if decision.tool else None,
        graph=decision.graph.value if decision.graph else None, method=decision.decision.method, rule=decision.decision.rule,
        refusal=decision.refusal, objects=list(entities.objects), unknown_objects=list(entities.unknown_objects),
        spectral_phrase=entities.spectral_phrase, wants_count=entities.wants_count, wants_location=entities.wants_location,
        wants_area=entities.wants_area,
    )
