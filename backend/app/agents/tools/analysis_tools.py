"""The analysis tools the agent dispatches a plan step to - each a backend function with a typed schema, each returning claims.

what  : `run_graph_step`, `recall_evidence_step`, and `TOOLS`, the LangChain tool objects over them.
where : `agents/graph.py`'s execute node dispatches by intent -> tool from the routing table, never by a
        model's choice (PDF p.24: a table chooses the pipeline). The tools are declared with LangChain's
        `@tool` so their schemas exist for the model that *proposes* follow-ups (the interface tools bind
        the same way) - the schema is the contract, the dispatch is deterministic.
how   : From 1.10 every analysis step is a graph run (`services/pipeline/runner.py`): the index query,
        the count, the land cover, the perception question and the change question each run the graph
        the routing table names, with a journal, figures, a provenance record and a checkpoint - the
        agent's run and the operator's run are the same run. The `StepResult` carries the run's claims
        in wire form, so synthesis phrases a detector's count and an index engine's hectares through one
        guard. A run that ended in a refusal is a failed step whose detail is the refusal, word for word.
"""

import logging
import time
from typing import Any

from langchain_core.tools import tool

from app.agents.requests import InputPaths, analysis_request_for_step
from app.agents.state import StepRecord, StepResult
from app.constants.model_ids import ModelId
from app.constants.statuses import RunStatus, TraceStepState
from app.lib.exceptions import AerisError

logger = logging.getLogger(__name__)


async def run_graph_step(step: StepRecord, *, inputs: InputPaths) -> StepResult:
    """One plan step as one graph run: the routing table's graph, end to end, one run on disk."""
    from app.services.pipeline.runner import run_analysis

    started = time.perf_counter()
    try:
        request = await analysis_request_for_step(step, inputs)
    except AerisError as error:
        return StepResult(state=TraceStepState.SKIPPED.value, detail=str(error), claims=[], latency_ms=0)
    outcome = await run_analysis(request)
    latency = round((time.perf_counter() - started) * 1000)
    if outcome.status is not RunStatus.COMPLETE:
        return StepResult(
            state=TraceStepState.FAILED.value, detail=outcome.error or f"run {outcome.run_id} ended {outcome.status.value}", claims=[],
            run_id=outcome.run_id, journal=str(outcome.journal), figures=[str(p) for p in outcome.figures], latency_ms=latency,
        )
    evidence_ids = [item["id"] for item in outcome.values.get("evidence_items") or []]
    layer_ids = [layer["id"] for layer in outcome.values.get("layers") or []]
    return StepResult(
        state=TraceStepState.COMPLETED.value, detail=f"{len(outcome.claims)} claims from run {outcome.run_id} ({request.graph.value})",
        claims=outcome.claims, evidence_ids=evidence_ids, layer_ids=layer_ids, run_id=outcome.run_id, journal=str(outcome.journal),
        figures=[str(p) for p in outcome.figures], latency_ms=latency,
    )


async def recall_evidence_step(step: StepRecord, *, earlier: list[StepResult]) -> StepResult:
    """What this conversation found before: the claims and evidence ids of earlier steps, no model run."""
    prior = [result for result in earlier if result.get("claims")]
    if not prior:
        return StepResult(state=TraceStepState.SKIPPED.value, detail="nothing was found earlier in this conversation", claims=[], latency_ms=0)
    latest = prior[-1]
    # The recalled claims are the answer's content; where they came from is provenance and stays in the
    # record (review, 2026-09-13: "recalled 2 claims resting on 4 evidence items" is not an answer).
    claims = [dict(claim) for claim in latest["claims"]]
    where = f"run {latest['run_id']}" if latest.get("run_id") else "the previous step"
    provenance: dict[str, Any] = {
        "recalledFromRequest": latest.get("request_id"), "recalledFromRun": latest.get("run_id"), "recalledFromStep": latest.get("step_id"),
        "claimCount": len(claims), "evidenceCount": len(latest.get("evidence_ids") or []),
    }
    return StepResult(
        state=TraceStepState.COMPLETED.value, detail=f"recalled {where}", claims=claims, provenance=provenance,
        evidence_ids=list(latest.get("evidence_ids") or []), layer_ids=list(latest.get("layer_ids") or []), run_id=latest.get("run_id"),
        figures=list(latest.get("figures") or []), latency_ms=0,
    )


# --- The tool schemas, for a model that proposes a step. Dispatch stays with the table. -----------------


@tool
def run_index_query(phrase: str) -> str:
    """Measure a spectral quantity over the scene: vegetation health, water, built-up, burn. Returns hectares and a map."""
    return phrase


@tool
def count_objects(classes: list[str]) -> str:
    """Count or locate objects of the detector's classes (plane, ship, storage tank, vehicle, ...) in an image."""
    return ", ".join(classes)


@tool
def segment_land_cover(classes: list[str]) -> str:
    """Map land-cover classes (building, road, water, forest, agricultural, barren) and measure their area."""
    return ", ".join(classes)


@tool
def answer_visual_question(question: str) -> str:
    """Ask the vision-language model what a picture shows. Not a measurement; never a count."""
    return question


@tool
def detect_change(question: str) -> str:
    """Compare two dates of one place: the change mask, its area, and what changed."""
    return question


@tool
def recall_evidence(about: str) -> str:
    """Bring back what this conversation found earlier - claims, evidence and figures - without running a model."""
    return about


TOOLS = [run_index_query, count_objects, segment_land_cover, answer_visual_question, detect_change, recall_evidence]
TOOL_FOR_MODEL: dict[ModelId | None, str] = {
    ModelId.INDEX_ENGINE: run_index_query.name, ModelId.DOTA_DETECTOR: count_objects.name, ModelId.SEGFORMER_LANDCOVER: segment_land_cover.name,
    ModelId.REMOTE_SENSING_VLM: answer_visual_question.name, ModelId.CHANGEFORMER: detect_change.name, None: recall_evidence.name,
}
