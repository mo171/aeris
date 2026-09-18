"""The agent as a StateGraph: understand -> plan -> approve (interrupt) -> execute -> synthesise -> interface-control.
Plans, routes, dispatches and presentation proposals; computes nothing.

what  : `build_agent_graph()` and the six nodes.
where : `agents/run.py` compiles it with the run checkpointer and drives it from the CLI (and, in Phase 2,
        from `/assistant/stream`); tests call the nodes and the graph both.
how   : PDF pp.24-25: a deterministic router with constrained planning. `understand` is the 1.8 router
        (the language model arbitrates only an uncertain margin); `plan` turns its steps into the
        operator's plan, prose by the model, steps by the table; `approve` pauses at a checkpoint with
        LangGraph's `interrupt()` and comes back with the steps the operator kept; `execute` dispatches
        each enabled step to its tool by the routing table; `synthesise` phrases every claim through the
        1.7 numeral guard; `control_interface` asks a separately scoped model call for presentation-only
        proposals, resolving only opaque ids held by the run.

        Nothing here retries, streams or checkpoints by hand: the graph is compiled with the sqlite
        checkpointer, the pause is an interrupt, the resume is a `Command`. A node reads its dependencies
        through the modules that own them and writes data - the same rule as `services/pipeline/`.
"""

import logging
import time
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.legacy_planner import apply_approval, build_plan
from app.agents.requests import InputPaths
from app.agents.router import SceneFacts, route_plan, routing_arbiter, routing_resources
from app.agents.state import AgentState, StepRecord, StepResult, describe_step
from app.agents.tools.analysis_tools import (
    recall_evidence_step,
    run_graph_step,
)
from app.agents.tools.interface_tools import (
    INTERFACE_TOOLS,
    UI_CAPABILITIES,
    _active_report_id,
    _current_results,
    validate_ui_commands,
)
from app.config import settings
from app.constants.intents import Intent
from app.constants.raster import ProcessingLevel
from app.constants.routing import PAIR_INTENTS, Modality
from app.constants.statuses import TraceStepState
from app.lib.llm.chat_model import build_chat_model, chat_model_record
from app.schemas.agent import AgentTraceStep
from app.services.answer.constrained import phrase_claims
from app.services.prompts.agent import AGENT_SYSTEM_PROMPT, SYNTHESIS_TEMPLATE

logger = logging.getLogger(__name__)


def _trace(state: AgentState, label: str, detail: str | None, *, state_name: TraceStepState, started: float | None, model_id: str | None) -> dict[str, Any]:
    duration = round((time.perf_counter() - started) * 1000) if started is not None else None
    step = AgentTraceStep(
        id=f"{state['request_id']}-{label.lower().replace(' ', '-')}", label=label, detail=detail, state=state_name, duration_ms=duration, model_id=model_id,
    )
    return step.to_wire()


async def understand(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    encoder, bank = await routing_resources()
    arbiter = routing_arbiter()
    images = state.get("image_paths") or []
    modalities = tuple(Modality.SAR if flag else Modality.OPTICAL for flag in (state.get("sar") or [False] * len(images)))
    resolution = state.get("ground_sample_distance")
    if resolution is None and state.get("scene_directory"):
        from app.services.spectral.indices import finest_resolution

        resolution = await finest_resolution(Path(state["scene_directory"]))
    # Two dates of one scene are two acquisitions, whatever the picture count says.
    acquisitions = 2 if state.get("reference_directory") else max(len(images), 1)
    facts = SceneFacts(resolution, acquisitions, modalities)
    plan = await route_plan(state["request"], encoder=encoder, bank=bank, facts=facts, arbiter=arbiter)
    steps = [describe_step(index, decision) for index, decision in enumerate(plan.steps, start=1)]
    detail = f"{len(plan.clauses)} clause{'s' if len(plan.clauses) != 1 else ''} -> " + " -> ".join(step["intent"] for step in steps)
    if arbiter is not None and arbiter.calls:
        detail += f"; the language model arbitrated {arbiter.calls}"
    return {
        "clauses": [clause.text for clause in plan.clauses], "steps": steps, "encoder_loaded": encoder is not None,
        "trace": [_trace(state, "Understanding the request", detail, state_name=TraceStepState.COMPLETED, started=started, model_id=None)],
    }


async def plan(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    model = build_chat_model()
    proposed, source = await build_plan(state["request"], state["steps"], model=model)
    record = chat_model_record()
    return {
        "plan": proposed.to_wire(), "plan_source": source,
        "trace": [_trace(state, "Planning", f"{len(proposed.steps)} steps, prose by {source}", state_name=TraceStepState.COMPLETED, started=started, model_id=record.version if record and source == "llm" else None)],
    }


async def approve(state: AgentState) -> dict[str, Any]:
    """The pause. `interrupt()` returns whatever the operator resumed with: `None` keeps every step;
    `{"enabledStepIds": [...]}` keeps those. The run waits at this checkpoint until then."""
    decision = interrupt({"plan": state["plan"], "planSource": state.get("plan_source", "template")})
    enabled = None if not isinstance(decision, dict) else decision.get("enabledStepIds")
    from app.schemas.agent import AnalysisPlan

    approved = apply_approval(AnalysisPlan.model_validate(state["plan"]), enabled)
    kept = [step.id for step in approved.steps if step.is_enabled]
    return {
        "plan": approved.to_wire(), "approved_step_ids": kept,
        "trace": [_trace(state, "Plan approved", f"{len(kept)} of {len(approved.steps)} steps enabled", state_name=TraceStepState.COMPLETED, started=None, model_id=None)],
    }


async def execute(state: AgentState) -> dict[str, Any]:
    enabled = set(state.get("approved_step_ids") or [])
    earlier = [result for result in state.get("results") or [] if result.get("request_id") != state["request_id"]]
    results: list[StepResult] = []
    trace: list[dict[str, Any]] = []
    for step in state["steps"]:
        started = time.perf_counter()
        label = f"Step {step['id'].split('-')[-1]}: {step['intent']}"
        if step.get("refusal"):
            result = StepResult(state=TraceStepState.SKIPPED.value, detail=step["refusal"], claims=[], latency_ms=0)
        elif step["id"] not in enabled:
            result = StepResult(state=TraceStepState.SKIPPED.value, detail="struck out by the operator", claims=[], latency_ms=0)
        else:
            try:
                result = await _dispatch(step, state, earlier)
            except Exception as error:  # noqa: BLE001 - one failed step is reported; the others still run
                logger.exception("agent step failed")
                result = StepResult(state=TraceStepState.FAILED.value, detail=f"{type(error).__name__}: {error}", claims=[], latency_ms=round((time.perf_counter() - started) * 1000))
        result.update(request_id=state["request_id"], step_id=step["id"], intent=step["intent"], tool=step.get("tool"), query=step["query"])
        results.append(result)
        trace.append(_trace(state, label, result.get("detail"), state_name=TraceStepState(result["state"]), started=started, model_id=step.get("tool")))
    return {"results": results, "trace": trace}


async def _dispatch(step: StepRecord, state: AgentState, earlier: list[StepResult]) -> StepResult:
    """Intent -> graph, from the routing table the step already carries. No model chooses here.

    The inputs a step runs over are chosen by what it needs, from what the operator gave: an index needs
    the scene directory; a pair needs two pictures (the earlier one first); anything else takes the
    picture when one was given and the scene otherwise. A step whose inputs are missing is skipped with
    the reason, and the answer says so.
    """
    intent = Intent(step["intent"])
    if intent == Intent.EVIDENCE_RECALL:
        return await recall_evidence_step(step, earlier=earlier)
    images = [Path(p) for p in state.get("image_paths") or []]
    sar = list(state.get("sar") or [False] * len(images))
    sar += [False] * (len(images) - len(sar))
    scene = Path(state["scene_directory"]) if state.get("scene_directory") else None
    reference = Path(state["reference_directory"]) if state.get("reference_directory") else None
    registered = bool(state.get("declared_registered"))
    level = ProcessingLevel(state["declared_level"]) if state.get("declared_level") else None
    gsd = state.get("ground_sample_distance")
    if intent in PAIR_INTENTS:
        if scene is not None and reference is not None:
            inputs = InputPaths(scene=scene, reference=reference, declared_level=level, declared_resolution_metres=gsd, declared_registered=registered)
        elif len(images) >= 2:
            inputs = InputPaths(
                scene=images[1], reference=images[0], declared_level=level, declared_resolution_metres=gsd, is_sar=sar[1], reference_is_sar=sar[0],
                declared_registered=registered,
            )
        else:
            return StepResult(
                state=TraceStepState.SKIPPED.value, claims=[], latency_ms=0,
                detail=f"{intent.value} compares two dates: give two pictures (--image, earlier first) or a scene and --before",
            )
    elif intent == Intent.INDEX_QUERY:
        if scene is None:
            return StepResult(state=TraceStepState.SKIPPED.value, detail="an index question needs a scene directory (--scene)", claims=[], latency_ms=0)
        inputs = InputPaths(scene=scene, declared_level=level, declared_resolution_metres=gsd)
    elif images:
        inputs = InputPaths(scene=images[0], declared_level=level, declared_resolution_metres=gsd, is_sar=sar[0])
    elif scene is not None:
        inputs = InputPaths(scene=scene, declared_level=level, declared_resolution_metres=gsd)
    else:
        return StepResult(state=TraceStepState.SKIPPED.value, detail=f"{intent.value} needs a picture (--image) or a scene (--scene)", claims=[], latency_ms=0)
    return await run_graph_step(step, inputs=inputs)


async def synthesise(state: AgentState) -> dict[str, Any]:
    started = time.perf_counter()
    own = [result for result in state.get("results") or [] if result.get("request_id") == state["request_id"]]
    claims, notes = synthesis_facts(own, state["steps"])
    model = build_chat_model() if settings.synthesis_generator == "llm" else None
    manager = None
    if settings.synthesis_generator == "vlm" or (settings.synthesis_generator == "llm" and model is None):
        from app.models.manager import get_manager

        manager = await get_manager()
    phrased = await phrase_claims(state["request"], claims, manager=manager, model=model, template=SYNTHESIS_TEMPLATE, notes=notes)
    record = chat_model_record()
    detail = f"{len(claims)} claims phrased by {phrased.source}" + (f" - model phrasing rejected: {phrased.rejection_reason}" if phrased.rejected_phrasing else "")
    return {
        "answer": phrased.text, "answer_source": phrased.source,
        "trace": [_trace(state, "Answering", detail, state_name=TraceStepState.COMPLETED, started=started, model_id=record.version if record and phrased.source == "llm" else phrased.model_version)],
    }


def synthesis_facts(results: list[StepResult], steps: list[StepRecord]) -> tuple[list[dict[str, Any]], list[str]]:
    """What the answer is phrased from: every step's claims, **each claim id once**, and a step that did
    not run stated in the operator's own words; plus notes for the wording that are not findings (a
    recall is said to be one, once). Structure, not a prompt, is what keeps the answer from repeating
    itself (review, 2026-09-13)."""
    queries = {step["id"]: step["query"] for step in steps}
    facts: list[dict[str, Any]] = []
    notes: list[str] = []
    seen: set[str] = set()
    for result in results:
        if result.get("intent") == Intent.EVIDENCE_RECALL.value and result.get("claims") and not notes:
            notes.append("These findings were recalled from earlier in this conversation; no new measurement was made.")
        for claim in result.get("claims") or []:
            identifier = claim.get("id")
            if identifier and identifier in seen:
                continue
            if identifier:
                seen.add(identifier)
            facts.append(claim)
        if result.get("state") != TraceStepState.COMPLETED.value and result.get("detail"):
            asked = queries.get(result.get("step_id", ""), result.get("query") or "this step")
            reason = "it was struck out of the plan" if result["detail"] == "struck out by the operator" else result["detail"]
            facts.append({"text": f"The request to {asked} was not done: {reason}", "isPrimary": False, "metrics": [], "kind": "negative"})
    return facts, notes


def _interface_resources(state: AgentState) -> str:
    """Render only opaque ids for the controller prompt; numeric values stay behind resolvers."""
    current = _current_results(state)
    raw_claim_ids = [str(claim["id"]) for result in current for claim in result.get("claims") or [] if claim.get("id")]
    claims = [
        f"id='{claim['id']}' finding='{claim.get('text', '')}'"
        for result in current
        for claim in result.get("claims") or []
        if claim.get("id")
    ]
    evidence = [str(identifier) for result in current for identifier in result.get("evidence_ids") or []]
    evidence.extend(
        str(identifier)
        for result in current
        for claim in result.get("claims") or []
        for identifier in claim.get("evidenceIds") or claim.get("evidence_ids") or []
    )
    layers = [str(identifier) for result in current for identifier in result.get("layer_ids") or result.get("layerIds") or []]
    target_sources: list[str] = []
    if isinstance(state.get("camera_targets"), dict):
        target_sources.extend(f"{identifier}" for identifier in state["camera_targets"])
    for result in current:
        target_sources.extend(f"{identifier}" for identifier in (result.get("camera_targets") or {}))
    targets = target_sources
    active_report_id = _active_report_id(state)
    associations = [
        f"{identifier}: {resource}"
        for result in current
        for identifier, resource in (result.get("evidence_resources") or {}).items()
    ]
    return (
        f"availableClaimIds={raw_claim_ids}; claimsSummary={claims}; availableEvidenceIds={list(dict.fromkeys(evidence))}; "
        f"availableLayerIds={list(dict.fromkeys(layers))}; cameraTargetIds={list(dict.fromkeys(targets))}; activeReportId={active_report_id}"
    )


async def control_interface(state: AgentState) -> dict[str, Any]:
    """Ask the model for safe presentation proposals after synthesis; never substitute a deterministic action."""
    started = time.perf_counter()
    budget = settings.voice_ui_command_budget_per_run
    try:
        model = build_chat_model()
    except Exception as error:  # noqa: BLE001 - provider construction is also an AI failure, with no safe fallback
        logger.warning("interface model construction failed; no command emitted", extra={"reason": str(error)})
        record = chat_model_record()
        return {
            "ui_commands": [],
            "trace": [_trace(state, "Interface control", f"AI interface selection failed: {type(error).__name__}", state_name=TraceStepState.FAILED, started=started, model_id=record.version if record else None)],
        }
    fixture = state.get("ui_command_fixture")
    if model is None:
        if fixture is None:
            commands: list[dict[str, Any]] = []
            detail = "AI-disabled interface control; no fixture supplied"
            # The established template-only agent trace ends at Answering. Keep that deliberate dev path
            # byte-compatible while the controller remains available for explicit fixtures and AI runs.
            trace: list[dict[str, Any]] = []
        else:
            commands = validate_ui_commands(list(fixture), state=state, budget=budget)
            detail = f"AI-disabled interface-control fixture; {len(commands)} validated commands"
            trace = [_trace(state, "Interface control", detail, state_name=TraceStepState.COMPLETED, started=started, model_id=None)]
        return {
            "ui_commands": commands,
            "trace": trace,
        }
    capability_text = "\n".join(
        f"- {capability.tool_name}: {capability.description}; opaque resource kind={capability.resource_kind.value}"
        for capability in UI_CAPABILITIES
    )
    prompt = (
        f"The operator asked: {state.get('request', '')!r}\n"
        f"Validated interface resources:\n{_interface_resources(state)}\n"
        f"Allowed presentation capabilities:\n{capability_text}\n"
        "Select presentation capabilities to present the validated findings or progress to the operator.\n"
        "Instructions:\n"
        "1. If there is a validated finding claim in availableClaimIds, invoke spotlight_claim passing the exact claim ID from availableClaimIds.\n"
        "2. Pass ONLY the exact opaque id (e.g. from availableClaimIds, availableEvidenceIds, availableLayerIds) as the tool argument without any descriptions, labels, or colons.\n"
        "3. Never provide coordinates, measurements, counts, report paths, or invented values.\n"
        "4. Every tool call must include a concise reason with words only (no numerals)."
    )
    try:
        reply = await model.bind_tools(INTERFACE_TOOLS).ainvoke([("system", AGENT_SYSTEM_PROMPT), ("human", prompt)])
    except Exception as error:  # noqa: BLE001 - no deterministic UI action is safe after model failure
        logger.warning("interface tool call failed; no command emitted", extra={"reason": str(error)})
        record = chat_model_record()
        return {
            "ui_commands": [],
            "trace": [_trace(state, "Interface control", f"AI interface selection failed: {type(error).__name__}", state_name=TraceStepState.FAILED, started=started, model_id=record.version if record else None)],
        }
    commands = validate_ui_commands(list(getattr(reply, "tool_calls", []) or []), state=state, budget=budget)
    record = chat_model_record()
    return {
        "ui_commands": commands,
        "trace": [_trace(state, "Interface control", f"{len(commands)} validated presentation commands", state_name=TraceStepState.COMPLETED, started=started, model_id=record.version if record else None)],
    }


def build_agent_graph() -> StateGraph:
    builder: StateGraph = StateGraph(AgentState)
    builder.add_node("understand", understand)
    builder.add_node("plan", plan)
    builder.add_node("approve", approve)
    builder.add_node("execute", execute)
    builder.add_node("synthesise", synthesise)
    builder.add_node("interface-control", control_interface)
    builder.add_edge(START, "understand")
    builder.add_edge("understand", "plan")
    builder.add_edge("plan", "approve")
    builder.add_edge("approve", "execute")
    builder.add_edge("execute", "synthesise")
    builder.add_edge("synthesise", "interface-control")
    builder.add_edge("interface-control", END)
    return builder
