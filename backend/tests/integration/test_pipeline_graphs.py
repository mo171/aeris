"""The 1.10 gate: the single-image and temporal graphs run end to end on real inputs, resume from a checkpoint, refuse by name, and write journals the contracts accept.

what  : Every branch of `graphs/single_image.py` (index over the synthetic scene is
        `test_spectral_engine.py`'s; here the detector, the segmenter and the VLM over real pictures and
        the real scene) and `graphs/temporal.py` over a LEVIR-CD pair, each checked for the trace it
        emits, the claims it makes, the record it writes and the contract its journal validates against;
        a resume after an interruption for each graph; and the S1/S9 refusals, word for word.
where : Integration suite. Needs the DOTA8 crop, the LEVIR-CD test split, the Mumbai subset, MinIO and
        Redis; the specialists' weights are fetched on first use. Skips, by name, what is not on disk.
how   : The runs are the real `run_analysis` the CLI and the agent use, so what is asserted here is what
        an operator gets. The change run is scored against the dataset's own label - an F1 the 1.6
        harness measured at 0.82 over the split - because a graph that ran is not a graph that measured.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from PIL import Image

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.datasets import DatasetId, DatasetSplit
from app.constants.events import EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND
from app.constants.evidence import ClaimKind, EvidenceKind
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
from app.constants.stages import PipelineStage
from app.constants.statuses import RunStatus
from app.services.datasets.loader import split_directory
from app.services.evidence.trace import evidence_graph_path, provenance_path
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.pipeline.runner import AnalysisRequest, RunOutcome, run_analysis
from app.services.sessions.fanout import EventFanout
from app.services.sessions.journal_writer import journal_path, open_journal
from app.services.sessions.session import open_session
from app.services.spectral.indices import resolve_index_target

pytestmark = pytest.mark.integration

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
UNION = Draft202012Validator(
    CONTRACTS["features/investigation/schemas/analysis.schema.ts"]["analysisStreamEventSchema"], format_checker=Draft202012Validator.FORMAT_CHECKER,
)
EVIDENCE_GRAPH = Draft202012Validator(CONTRACTS["features/investigation/schemas/evidence.schema.ts"]["evidenceGraphSchema"])

CROP = "P1470__1024__3296___1648"
SCENE = Path("data/datasets/sentinel2-l2a/mumbai_gate")
LEVIR = Path("data/datasets/levir-cd/test")
# A pair the dataset labels as 42% changed: a field that became a subdivision.
LEVIR_PAIR = "0271.png"


def crop_path() -> Path:
    path = split_directory(DatasetId.DOTA8, DatasetSplit.VALIDATION) / "images" / "val" / f"{CROP}.jpg"
    if not path.exists():
        pytest.skip(f"{path} is not on disk")
    return path


def scene_path() -> Path:
    if not (SCENE / "B08.tif").exists():
        pytest.skip(f"{SCENE} is not on disk")
    return SCENE


def levir_pair() -> tuple[Path, Path, Path]:
    before, after, label = (LEVIR / part / LEVIR_PAIR for part in ("A", "B", "label"))
    if not label.exists():
        pytest.skip(f"{LEVIR} is not on disk")
    return before, after, label


def journal_events(run_id: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in journal_path(run_id).read_text(encoding="utf-8").splitlines()]


def completed_stages(events: list[dict[str, Any]]) -> list[str]:
    return [e["step"]["stageCode"] for e in events if e["type"] == "trace-step" and e["step"]["state"] == "completed"]


def assert_journal_validates(run_id: str) -> None:
    not_yet = {event_type.value for event_type in EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND}
    for index, payload in enumerate(journal_events(run_id)):
        if payload["type"] in not_yet:
            continue
        errors = [error.message for error in UNION.iter_errors(payload)]
        assert not errors, f"line {index + 1} ({payload['type']}): {errors[:1]}"
    graph = json.loads(evidence_graph_path(run_id).read_text(encoding="utf-8"))
    assert not list(EVIDENCE_GRAPH.iter_errors(graph))


def assert_every_claim_resolves(outcome: RunOutcome) -> None:
    """Claims -> evidence -> (layer, features) as `api-contract.md` requires; a picture's evidence has no layer."""
    evidence = {item["id"]: item for item in outcome.values.get("evidence_items") or []}
    layers = {layer["id"]: layer for layer in outcome.values.get("layers") or []}
    for claim in outcome.claims:
        assert claim["evidenceIds"], claim["text"]
        for evidence_id in claim["evidenceIds"]:
            item = evidence[evidence_id]
            if item["layerId"] is not None:
                feature_ids = {feature["id"] for feature in layers[item["layerId"]]["features"]}
                assert set(item["featureIds"]) <= feature_ids
    trace_steps = set(outcome.values["trace_step_ids"])
    assert all(claim["traceStepId"] in trace_steps for claim in outcome.claims)


# ── Single image: the detector ───────────────────────────────────────────────────────────────────


async def test_a_count_over_a_picture_runs_s1_s13_s15_and_claims_the_boxes(isolated_pipeline_paths: Path) -> None:
    outcome = await run_analysis(AnalysisRequest(
        GraphName.SINGLE_IMAGE, "count the basketball courts", Intent.DETECT, crop_path(), objects=("basketball court",), tool=ModelId.DOTA_DETECTOR.value,
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    events = journal_events(outcome.run_id)
    # No S7 for a picture; S14 ran and said it was off (the fixture turns VLM reading off).
    assert completed_stages(events) == ["S1", "S13", "S15", "S14", "S16", "S18", "S19"]
    primary = next(claim for claim in outcome.claims if claim["isPrimary"])
    assert primary["text"].startswith("The detector found") and "basketball court" in primary["text"]
    assert primary["modelId"] == ModelId.DOTA_DETECTOR.value and primary["confidence"] is not None
    assert {metric["label"] for metric in primary["metrics"]} == {"Count", "Mean score"}
    figures = [e for e in events if e["type"] == "figure-ready"]
    assert [f["kind"] for f in figures] == ["rgb-composite", "detection-overlay"]
    assert figures[1]["isPrimary"] and figures[1]["claimIds"] == [claim["id"] for claim in outcome.claims]
    assert not [e for e in events if e["type"] == "layer-ready"], "a picture has no ground to place a layer on"
    record = json.loads(provenance_path(outcome.run_id).read_text(encoding="utf-8"))
    assert [artefact["stage"] for artefact in record["artefacts"]] == ["S13"] and record["parameters"]["objects"] == ["basketball court"]
    assert record["parameters"]["inputs"][0]["georeferenced"] is False and len(record["inputs"]) == 1
    assert_every_claim_resolves(outcome)
    assert_journal_validates(outcome.run_id)
    # The run's confidence is S13's stated one - the mean score over every box kept - which S18 took as
    # the minimum of the stages that stated one; the claim's is the mean over its own class.
    s13 = next(record for record in outcome.values["stage_models"] if record["stage"] == "S13")
    assert outcome.values["confidence"] == pytest.approx(s13["confidence"])
    assert "The detector found" in outcome.answer and "cloud" not in outcome.answer.lower()


async def test_a_count_resumes_after_s13_without_running_the_detector_again(isolated_pipeline_paths: Path) -> None:
    """The 1.0 resume gate on the new graph: stop after S13, resume in a fresh graph, S15 reads the state."""
    request = AnalysisRequest(GraphName.SINGLE_IMAGE, "count the basketball courts", Intent.DETECT, crop_path(), objects=("basketball court",))
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        paused = GRAPH_BUILDERS[GraphName.SINGLE_IMAGE]().compile(checkpointer=checkpointer, store=store, interrupt_after=["detect_objects"])
        async with open_session() as session:
            handle = await session.start(graph=paused, query=request.query, intent=request.intent, fanout=EventFanout(), extra_state=request.initial_state())
            await handle.wait()
        snapshot = await read_thread_state(paused, handle.run_id)
        assert snapshot.next == ("localise_detections",)
        boxes_before = snapshot.values["detections"]

        graph = GRAPH_BUILDERS[GraphName.SINGLE_IMAGE]().compile(checkpointer=checkpointer, store=store)
        fanout = EventFanout()
        async with open_session() as session, open_journal(handle.run_id) as journal:
            fanout.register("journal", journal)
            resumed = await session.resume(graph=graph, run_id=handle.run_id, intent=request.intent, fanout=fanout)
            status = await resumed.wait()
        final = await read_thread_state(graph, handle.run_id)
    assert status is RunStatus.COMPLETE
    assert completed_stages(journal_events(handle.run_id)) == ["S15", "S14", "S16", "S18", "S19"]
    assert final.values["detections"] == boxes_before, "S13 was not re-run; S15 read what it had retained"
    assert final.values["claims"] and final.values["provenance_path"]


# ── Single image: the segmenter ──────────────────────────────────────────────────────────────────


async def test_land_cover_over_a_scene_measures_the_class_asked_for_with_layers_and_a_table(isolated_pipeline_paths: Path) -> None:
    outcome = await run_analysis(AnalysisRequest(
        GraphName.SINGLE_IMAGE, "segment the buildings", Intent.SEGMENT, scene_path(), declared_level=ProcessingLevel.L2A, classes=("Building",),
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    events = journal_events(outcome.run_id)
    assert completed_stages(events) == ["S1", "S7", "S13", "S15", "S14", "S16", "S18", "S19"]
    kinds = [claim["kind"] for claim in outcome.claims]
    assert ClaimKind.QUANTITATIVE.value in kinds
    primary = next(claim for claim in outcome.claims if claim["isPrimary"])
    assert primary["text"].startswith("Building (segformer-landcover class) covers") and "hectares of mumbai_gate" in primary["text"]
    assert primary["modelId"] == ModelId.SEGFORMER_LANDCOVER.value and 0.0 < primary["confidence"] <= 1.0
    table = next(claim for claim in outcome.claims if claim["text"].startswith("Land cover over the observed ground"))
    assert not table["isPrimary"] and all(0.0 <= metric["value"] <= 100.0 for metric in table["metrics"])
    layers = {layer["kind"] for layer in outcome.values["layers"]}
    assert layers == {"raster-tiles", "raster-mask", "polygon-vector"}
    record = json.loads(provenance_path(outcome.run_id).read_text(encoding="utf-8"))
    assert {artefact["name"] for artefact in record["artefacts"]} >= {"S13_landcover-classes.tif", "S13_landcover-confidence.tif", "S15_landcover-building.tif"}
    assert set(record["parameters"]["classFractions"]) >= {"Building", "Water", "Background"}
    assert {item["bandId"] for item in record["inputs"]} == {"B04", "B03", "B02"}
    assert_every_claim_resolves(outcome)
    assert_journal_validates(outcome.run_id)


async def test_land_cover_over_a_picture_with_a_declared_pixel_size_is_nominal_hectares_and_no_layers(isolated_pipeline_paths: Path) -> None:
    before, _, _ = levir_pair()
    outcome = await run_analysis(AnalysisRequest(
        GraphName.SINGLE_IMAGE, "classify the land cover", Intent.SEGMENT, before, declared_resolution_metres=0.5,
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    assert outcome.values["layers"] == []
    regional = [claim for claim in outcome.claims if "(segformer-landcover class) covers" in claim["text"]]
    assert regional and all("(nominal, at 0.5 m per pixel)" in claim["text"] for claim in regional)
    table = next(claim for claim in outcome.claims if claim["text"].startswith("Land cover over the observed ground"))
    assert table["isPrimary"], "with no class named, the land-cover table is the answer"
    assert_journal_validates(outcome.run_id)


# ── Single image: the VLM ────────────────────────────────────────────────────────────────────────


async def test_a_perception_question_is_the_models_words_as_a_labelled_claim(isolated_pipeline_paths: Path) -> None:
    outcome = await run_analysis(AnalysisRequest(
        GraphName.SINGLE_IMAGE, "is this a sports complex", Intent.SCENE_VQA, crop_path(), tool=ModelId.REMOTE_SENSING_VLM.value,
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    assert completed_stages(journal_events(outcome.run_id)) == ["S1", "S14", "S16", "S18", "S19"]
    [claim] = outcome.claims
    assert claim["kind"] == ClaimKind.CATEGORICAL.value and claim["metrics"] == [] and claim["confidence"] is None
    assert claim["text"].startswith('Asked "is this a sports complex?", the vision-language model\'s reading (not a measurement) is:')
    [item] = outcome.values["evidence_items"]
    assert item["kind"] == EvidenceKind.SCENE_CROP.value and item["layerId"] is None
    assert outcome.values["confidence"] is None, "a wording certainty is not a claim's confidence"
    assert "not a measurement" in outcome.answer and outcome.answer.count("reading") == 1
    assert_journal_validates(outcome.run_id)


async def test_grounding_a_phrase_the_detector_has_no_class_for_goes_to_the_vlm(isolated_pipeline_paths: Path) -> None:
    outcome = await run_analysis(AnalysisRequest(
        GraphName.SINGLE_IMAGE, "where is the stadium", Intent.GROUND, crop_path(), tool=ModelId.REMOTE_SENSING_VLM.value,
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    assert completed_stages(journal_events(outcome.run_id)) == ["S1", "S14", "S16", "S18", "S19"]
    assert outcome.claims[0]["modelId"] == ModelId.REMOTE_SENSING_VLM.value


# ── S1 refuses by name ───────────────────────────────────────────────────────────────────────────


async def test_an_index_over_a_picture_is_refused_at_s1_with_the_reason(isolated_pipeline_paths: Path) -> None:
    target = await resolve_index_target("water")
    outcome = await run_analysis(AnalysisRequest(GraphName.SINGLE_IMAGE, "water", Intent.INDEX_QUERY, crop_path(), target=target))
    assert outcome.status is RunStatus.FAILED
    assert outcome.error and "computes from named bands" in outcome.error and "picture" in outcome.error
    assert completed_stages(journal_events(outcome.run_id)) == []
    failed = [e for e in journal_events(outcome.run_id) if e["type"] == "trace-step" and e["step"]["state"] == "failed"]
    assert failed and failed[0]["step"]["stageCode"] == PipelineStage.S1.value


async def test_a_class_too_small_for_the_scene_is_refused_at_s1_with_both_numbers(isolated_pipeline_paths: Path) -> None:
    outcome = await run_analysis(AnalysisRequest(
        GraphName.SINGLE_IMAGE, "count the cars", Intent.DETECT, scene_path(), declared_level=ProcessingLevel.L2A, objects=("small vehicle",),
    ))
    assert outcome.status is RunStatus.FAILED
    assert outcome.error and "10 m per pixel" in outcome.error and "0.56 m or finer" in outcome.error


async def test_boxes_of_a_class_the_scene_cannot_resolve_are_not_claimed(isolated_pipeline_paths: Path) -> None:
    """Bridges at 10 m pass the gate; planes at three pixels a side do not, whatever the detector drew."""
    outcome = await run_analysis(AnalysisRequest(
        GraphName.SINGLE_IMAGE, "find the bridges", Intent.GROUND, scene_path(), declared_level=ProcessingLevel.L2A, objects=("bridge",),
        tool=ModelId.DOTA_DETECTOR.value, wants_location=True,
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    claimed = " ".join(claim["text"] for claim in outcome.claims)
    assert "plane" not in claimed and "storage tank" not in claimed
    record = json.loads(provenance_path(outcome.run_id).read_text(encoding="utf-8"))
    below = record["parameters"]["detectionsBelowResolution"]
    kept = record["parameters"]["detectionCounts"]
    assert all(name in kept for name in below), "the artefact keeps what the model said; the claims do not"
    assert outcome.values["layers"] and outcome.values["layers"][0]["kind"] == "polygon-vector"
    located = [claim for claim in outcome.claims if claim["kind"] == ClaimKind.SPATIAL.value]
    assert not located or "latitude" in located[0]["text"]


async def test_a_pair_of_different_shapes_is_refused_at_s1(isolated_pipeline_paths: Path, tmp_path: Path) -> None:
    before, after, _ = levir_pair()
    smaller = tmp_path / "smaller.png"
    Image.open(before).crop((0, 0, 128, 128)).save(smaller)
    outcome = await run_analysis(AnalysisRequest(GraphName.TEMPORAL, "what changed", Intent.CHANGE_DETECT, after, reference=smaller, declared_resolution_metres=0.5))
    assert outcome.status is RunStatus.FAILED and outcome.error and "needs one grid" in outcome.error


# ── Temporal ─────────────────────────────────────────────────────────────────────────────────────


async def test_a_pair_the_gate_cannot_measure_is_refused_with_every_number_and_the_way_out(isolated_pipeline_paths: Path) -> None:
    before, after, _ = levir_pair()
    outcome = await run_analysis(AnalysisRequest(GraphName.TEMPORAL, "what changed", Intent.CHANGE_DETECT, after, reference=before, declared_resolution_metres=0.5))
    assert outcome.status is RunStatus.FAILED
    assert outcome.error and "residual" in outcome.error and "10.00 px = 5 m" in outcome.error and "--registered" in outcome.error
    events = journal_events(outcome.run_id)
    assert completed_stages(events) == ["S1"]
    s9 = next(e["step"] for e in events if e["type"] == "trace-step" and e["step"]["stageCode"] == "S9" and e["step"]["state"] != "running")
    assert s9["state"] == "failed" and s9["model"]["id"] == ModelId.CO_REGISTRATION.value


async def test_a_declared_pair_is_compared_measured_drawn_and_scores_against_its_label(isolated_pipeline_paths: Path) -> None:
    before, after, label = levir_pair()
    outcome = await run_analysis(AnalysisRequest(
        GraphName.TEMPORAL, "what changed between the two images", Intent.CHANGE_DETECT, after, reference=before,
        declared_resolution_metres=0.5, declared_registered=True,
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    events = journal_events(outcome.run_id)
    assert completed_stages(events) == ["S1", "S9", "S13", "S15", "S14", "S16", "S18", "S19"]
    primary = next(claim for claim in outcome.claims if claim["isPrimary"])
    assert primary["text"].startswith("Change (changeformer probability >= 0.50) covers") and "(nominal, at 0.5 m per pixel)" in primary["text"]
    assert primary["modelId"] == ModelId.CHANGEFORMER.value and primary["confidence"] is not None
    figures = [e for e in events if e["type"] == "figure-ready"]
    assert [f["kind"] for f in figures] == ["rgb-composite", "rgb-composite", "index-map", "comparison"]
    assert figures[-1]["isPrimary"] and figures[-1]["width"] > 3 * 256
    record = json.loads(provenance_path(outcome.run_id).read_text(encoding="utf-8"))
    registration = record["parameters"]["registration"]
    assert registration["verdict"] == "declared-by-operator" and registration["declaredRegistered"] and registration["accepted"]
    assert {artefact["name"] for artefact in record["artefacts"]} == {"S13_change-probability.tif", "S13_change-mask.tif"}
    assert len(record["inputs"]) == 2
    assert_every_claim_resolves(outcome)
    assert_journal_validates(outcome.run_id)

    # The mask the run retained, scored against the dataset's own label: the 1.6 harness's F1 over the
    # split is 0.82, and a single pair with 42% change should not be far from it.
    import rasterio

    truth = np.asarray(Image.open(label).convert("L")) > 127
    with rasterio.open(outcome.values["change_mask_path"]) as dataset:
        predicted = dataset.read(1) == 1
    intersection = (predicted & truth).sum()
    f1 = 2 * intersection / (predicted.sum() + truth.sum())
    assert f1 > 0.7, f"F1 against the label was {f1:.3f}"
    assert outcome.values["measurement"]["pixelCount"] == int(predicted.sum())


async def test_a_change_run_resumes_after_s13_without_running_the_model_again(isolated_pipeline_paths: Path) -> None:
    before, after, _ = levir_pair()
    request = AnalysisRequest(GraphName.TEMPORAL, "what changed", Intent.CHANGE_DETECT, after, reference=before, declared_resolution_metres=0.5, declared_registered=True)
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        paused = GRAPH_BUILDERS[GraphName.TEMPORAL]().compile(checkpointer=checkpointer, store=store, interrupt_after=["detect_change"])
        async with open_session() as session:
            handle = await session.start(graph=paused, query=request.query, intent=request.intent, fanout=EventFanout(), extra_state=request.initial_state())
            await handle.wait()
        snapshot = await read_thread_state(paused, handle.run_id)
        assert snapshot.next == ("localise_change",)
        # The local copy of the mask goes; S15 in a new process would only have storage.
        mask_path = Path(snapshot.values["change_mask_path"])
        await asyncio.to_thread(mask_path.unlink)

        graph = GRAPH_BUILDERS[GraphName.TEMPORAL]().compile(checkpointer=checkpointer, store=store)
        fanout = EventFanout()
        async with open_session() as session, open_journal(handle.run_id) as journal:
            fanout.register("journal", journal)
            resumed = await session.resume(graph=graph, run_id=handle.run_id, intent=request.intent, fanout=fanout)
            status = await resumed.wait()
    assert status is RunStatus.COMPLETE
    assert completed_stages(journal_events(handle.run_id)) == ["S15", "S14", "S16", "S18", "S19"]
    assert await asyncio.to_thread(mask_path.exists), "the artefact was restored from storage through S15"


async def test_a_change_question_keeps_the_measurement_beside_the_models_answer(isolated_pipeline_paths: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    before, after, _ = levir_pair()
    outcome = await run_analysis(AnalysisRequest(
        GraphName.TEMPORAL, "were new buildings constructed", Intent.CHANGE_VQA, after, reference=before,
        declared_resolution_metres=0.5, declared_registered=True, tool=ModelId.REMOTE_SENSING_VLM.value,
    ))
    assert outcome.status is RunStatus.COMPLETE, outcome.error
    assert completed_stages(journal_events(outcome.run_id)) == ["S1", "S9", "S13", "S15", "S14", "S16", "S18", "S19"]
    kinds = {claim["modelId"]: claim["kind"] for claim in outcome.claims}
    assert kinds[ModelId.CHANGEFORMER.value] == ClaimKind.QUANTITATIVE.value
    assert kinds[ModelId.REMOTE_SENSING_VLM.value] == ClaimKind.CATEGORICAL.value
    reading = next(claim for claim in outcome.claims if claim["modelId"] == ModelId.REMOTE_SENSING_VLM.value)
    assert reading["text"].startswith('Asked "were new buildings constructed?"')
    assert_journal_validates(outcome.run_id)
