"""The analysis tools the agent dispatches a plan step to - each a backend function with a typed schema, each returning claims.

what  : `run_index_query_step`, `count_objects_step`, `answer_visual_question_step`, `recall_evidence_step`,
        and `TOOLS`, the LangChain tool objects over them.
where : `agents/graph.py`'s execute node dispatches by intent -> tool from the routing table, never by a
        model's choice (PDF p.24: a table chooses the pipeline). The tools are declared with LangChain's
        `@tool` so their schemas exist for the model that *proposes* follow-ups (the interface tools bind
        the same way) - the schema is the contract, the dispatch is deterministic.
how   : Every tool returns a `StepResult` whose findings are *claims in wire form* - the same shape S15
        produces - so synthesis phrases a detector's count and an index engine's hectares through one
        guard. A count is a claim with a metric; a VLM answer is a claim with no metric, its text
        labelled as the model's reading; a refusal is a step with no claims and a detail. The index query
        runs the real graph through `services/pipeline/runner.py`: journal, figures, provenance, checkpoint.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from app.agents.state import StepRecord, StepResult
from app.constants.evidence import ClaimKind, MetricDirection
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.raster import ProcessingLevel
from app.constants.statuses import RunStatus, TraceStepState
from app.services.spectral.indices import resolve_index_target

logger = logging.getLogger(__name__)


def _claim(text: str, *, model_id: str, version: str, metrics: list[dict[str, Any]] | None = None, primary: bool = True, kind: ClaimKind = ClaimKind.QUANTITATIVE) -> dict[str, Any]:
    """A claim in wire form (camelCase, as `Claim.to_wire()` writes it) for findings made outside a graph."""
    return {
        "text": text, "kind": kind.value, "isPrimary": primary, "metrics": metrics or [], "evidenceIds": [],
        "modelId": model_id, "modelVersion": version, "confidence": None,
    }


def _metric(label: str, value: float, unit: str = "", precision: int = 0) -> dict[str, Any]:
    return {"label": label, "value": value, "unit": unit, "direction": MetricDirection.NEUTRAL.value, "precision": precision}


async def run_index_query_step(step: StepRecord, *, scene_directory: Path, declared_level: ProcessingLevel | None) -> StepResult:
    """An index question over a scene: the index-query graph, end to end, one run on disk."""
    from app.services.pipeline.runner import run_index_query

    started = time.perf_counter()
    target = await resolve_index_target(step.get("spectral_phrase") or step["query"])
    outcome = await run_index_query(
        scene_directory=scene_directory, query=step["query"], target=target, intent=Intent(step["intent"]), declared_level=declared_level,
    )
    latency = round((time.perf_counter() - started) * 1000)
    if outcome.status is not RunStatus.COMPLETE:
        return StepResult(state=TraceStepState.FAILED.value, detail=f"run {outcome.run_id} ended {outcome.status.value}", claims=[], run_id=outcome.run_id, journal=str(outcome.journal), figures=[str(p) for p in outcome.figures], latency_ms=latency)
    evidence_ids = [item["id"] for item in outcome.values.get("evidence_items") or []]
    layer_ids = [layer["id"] for layer in outcome.values.get("layers") or []]
    return StepResult(
        state=TraceStepState.COMPLETED.value, detail=f"{len(outcome.claims)} claims from run {outcome.run_id}", claims=outcome.claims,
        evidence_ids=evidence_ids, layer_ids=layer_ids, run_id=outcome.run_id, journal=str(outcome.journal),
        figures=[str(p) for p in outcome.figures], latency_ms=latency,
    )


async def count_objects_step(step: StepRecord, *, image_path: Path) -> StepResult:
    """A count or a grounding of detector classes: the detector's boxes, one claim per class asked for."""
    from app.cli.ask import read_picture
    from app.models.manager import get_manager
    from app.services.detection.detector import detect_objects

    started = time.perf_counter()
    picture = await asyncio.to_thread(read_picture, image_path, False)
    result = await detect_objects(picture, manager=await get_manager())
    asked = tuple(step.get("objects") or ()) or tuple(name for name in result.class_names if result.count(name))
    claims = []
    for class_name in asked:
        count = result.count(class_name)
        plural = class_name if count == 1 else f"{class_name}s"
        text = f"The detector found {count} {plural} in the image."
        if step.get("wants_location") and count:
            wanted = result.class_names.index(class_name)
            centres = sorted((b for b in result.boxes if b.class_index == wanted), key=lambda b: -b.confidence)[:5]
            text += " Located at pixel " + "; ".join(f"({c.corners.mean(axis=0)[0]:.0f}, {c.corners.mean(axis=0)[1]:.0f}), score {c.confidence:.2f}" for c in centres) + "."
        claims.append(_claim(text, model_id=result.model_id.value, version=result.model_version, metrics=[_metric("Count", float(count))]))
    others = {name: result.count(name) for name in result.class_names if name not in asked and result.count(name)}
    if others:
        claims.append(_claim(
            "Also found: " + ", ".join(f"{count} {name}" for name, count in others.items()) + ".", model_id=result.model_id.value,
            version=result.model_version, metrics=[_metric(f"Count of {name}", float(count)) for name, count in others.items()], primary=False,
        ))
    return StepResult(
        state=TraceStepState.COMPLETED.value, detail=f"{len(result.boxes)} boxes kept, mean score {result.confidence:.2f}" if result.confidence is not None else "no boxes kept",
        claims=claims, latency_ms=round((time.perf_counter() - started) * 1000),
    )


async def answer_visual_question_step(step: StepRecord, *, image_paths: list[Path], sar: list[bool]) -> StepResult:
    """A perception question: the VLM's words, as a claim with no metric, labelled as its reading."""
    from app.cli.ask import read_picture
    from app.models.manager import get_manager
    from app.services.prompts.vlm import SAR_IMAGE_NOTE
    from app.services.vlm.reading import answer_question, read_pair

    started = time.perf_counter()
    pictures = [await asyncio.to_thread(read_picture, path, flag) for path, flag in zip(image_paths, sar, strict=True)]
    manager = await get_manager()
    question = step["query"] if step["query"].endswith("?") else f"{step['query']}?"
    if len(pictures) == 2:
        notes = tuple(SAR_IMAGE_NOTE if flag else None for flag in sar)
        reading = await read_pair(pictures[0], pictures[1], question, manager=manager, notes=notes)  # type: ignore[arg-type]
    else:
        reading = await answer_question(pictures[0], question, manager=manager, is_sar=sar[0])
    text = f"Asked \"{question}\", the vision-language model's reading (not a measurement) is: {reading.text.strip().rstrip('.')}."
    return StepResult(
        state=TraceStepState.COMPLETED.value, detail=f"{reading.model_version}, wording certainty {reading.confidence:.2f}",
        claims=[_claim(text, model_id=reading.model_id.value, version=reading.model_version, kind=ClaimKind.CATEGORICAL)],
        latency_ms=round((time.perf_counter() - started) * 1000),
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
    provenance = {
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
def answer_visual_question(question: str) -> str:
    """Ask the vision-language model what a picture shows. Not a measurement; never a count."""
    return question


@tool
def recall_evidence(about: str) -> str:
    """Bring back what this conversation found earlier - claims, evidence and figures - without running a model."""
    return about


TOOLS = [run_index_query, count_objects, answer_visual_question, recall_evidence]
TOOL_FOR_MODEL: dict[ModelId | None, str] = {
    ModelId.INDEX_ENGINE: run_index_query.name, ModelId.DOTA_DETECTOR: count_objects.name,
    ModelId.REMOTE_SENSING_VLM: answer_visual_question.name, None: recall_evidence.name,
}
