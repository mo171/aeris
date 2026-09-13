"""The Phase 1.5 gate: every claim resolves to pixels, every artefact stage names its layer, every figure a step, and the records validate.

what  : The builder on a known mask, and the index-query graph end to end with its layers, claims,
        evidence graph and provenance record walked back to the raster.
where : `tests/integration`, on the synthetic scene `test_spectral_engine.py` defines (imported, not
        copied). The graph tests need MinIO for figures and artefacts and are marked `integration`.
how   : The gate is four statements, and each has a test whose name says which:

        1. every claim in a run resolves to pixels - walked claim -> evidence -> layer -> feature -> ring
           -> rasterised back onto the S15 mask, where every pixel the region measured lies inside it;
        2. every trace step that produced an intermediate carries its artefact - S12 and S15 name the
           layer that draws theirs, and the provenance record carries their object keys;
        3. every figure resolves to a trace step, and the primary figure carries the claims it draws;
        4. the run's JSONL and its evidence graph validate against the vendored contracts.

        The synthetic scene's sparse region is one solid rectangle, so the ring and the region coincide
        exactly and the containment check has no holes to forgive. The real scene - with 658 holes in its
        largest region - is `aeris analyse`, recorded at the bottom of this file.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import pytest_asyncio
import rasterio
from jsonschema import Draft202012Validator
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from shapely.geometry import Polygon
from shapely.ops import transform as transform_geometry

from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.events import EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND
from app.constants.evidence import (
    CONFIDENCE_AGGREGATION_RULE,
    DETECTION_MASK_DETECTED,
    ClaimKind,
    EvidenceKind,
)
from app.constants.layers import LayerKind
from app.constants.model_ids import ModelId
from app.constants.stages import PipelineStage
from app.constants.statuses import RunStatus, TraceStepState
from app.schemas.events import ClaimEvent, FigureReadyEvent, LayerReadyEvent
from app.services.evidence.builder import build_region_evidence
from app.services.evidence.spatial import measure_mask
from app.services.evidence.trace import evidence_graph_path, provenance_path
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs.single_image import build_single_image_graph
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.journal_writer import journal_path
from tests.integration.test_spectral_engine import (
    COLUMNS,
    NORTH,
    ROWS,
    SCENE_CRS,
    WEST,
    Recorder,
    geodesic_hectares,
    run_index_query,
    scene,  # noqa: F401 - the fixture, re-exported for this module
)

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
EVIDENCE_GRAPH_SCHEMA = CONTRACTS["features/investigation/schemas/evidence.schema.ts"]["evidenceGraphSchema"]
UNION = CONTRACTS["features/investigation/schemas/analysis.schema.ts"]["analysisStreamEventSchema"]
TRANSFORM = (10.0, 0.0, WEST, 0.0, -10.0, NORTH)


def validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


# ── The builder on a known mask ──────────────────────────────────────────────────────────────────


async def test_the_builder_produces_both_representations_and_a_primary_claim() -> None:
    detected = np.zeros((ROWS, COLUMNS), dtype=bool)
    detected[:, COLUMNS // 2:] = True
    values = np.where(detected, 0.3, 0.7).astype(np.float32)
    statistics = await measure_mask(detected, np.ones_like(detected), transform=TRANSFORM, crs=SCENE_CRS)

    evidence = await build_region_evidence(
        detected, values, statistics=statistics, transform=TRANSFORM, crs=SCENE_CRS, resolution_metres=10.0,
        run_id="run_test", trace_step_id="stp_test", scene_id="scene", mask_storage_uri="s3://bucket/mask.tif",
        index_label="NDVI", quantity_label="NDVI 0.20 to 0.40", region_label="Sparse vegetation",
        lower=0.2, upper=0.4, obscured_fraction=0.05, unphysical_fraction=0.0,
    )

    assert evidence.raster_layer.kind is LayerKind.RASTER_MASK
    assert evidence.raster_layer.tile_url_template is not None and "{z}/{x}/{y}" in evidence.raster_layer.tile_url_template
    assert evidence.vector_layer.kind is LayerKind.POLYGON_VECTOR
    assert evidence.regions_total == 1 and evidence.regions_drawn == 1
    feature = evidence.vector_layer.features[0]
    assert feature.area_hectares == pytest.approx(geodesic_hectares(COLUMNS // 2, COLUMNS, 0, ROWS), rel=1e-6)
    assert feature.value == pytest.approx(0.3, abs=1e-6)
    assert feature.magnitude == 1.0 and feature.confidence is None

    primary = [claim for claim in evidence.claims if claim.is_primary]
    assert len(primary) == 1
    assert primary[0].kind is ClaimKind.QUANTITATIVE
    assert primary[0].model_id is ModelId.GEOSPATIAL_ENGINE
    assert {metric.label for metric in primary[0].metrics} == {
        "Area", "Share of observed ground", "Regions", "Observed ground", "Obscured by cloud and shadow"
    }
    area_metric = next(metric for metric in primary[0].metrics if metric.label == "Area")
    assert area_metric.value == pytest.approx(statistics.detected.hectares)
    assert area_metric.precision == 1
    assert all(claim.trace_step_id == "stp_test" for claim in evidence.claims)
    for layer in (evidence.raster_layer, evidence.vector_layer):
        assert layer.provenance.trace_step_id == "stp_test"
        assert layer.provenance.model_id == ModelId.GEOSPATIAL_ENGINE.value


async def test_an_empty_mask_is_a_negative_claim_with_evidence_not_silence() -> None:
    detected = np.zeros((ROWS, COLUMNS), dtype=bool)
    statistics = await measure_mask(detected, np.ones_like(detected), transform=TRANSFORM, crs=SCENE_CRS)

    evidence = await build_region_evidence(
        detected, np.full(detected.shape, 0.7, dtype=np.float32), statistics=statistics, transform=TRANSFORM,
        crs=SCENE_CRS, resolution_metres=10.0, run_id="run_test", trace_step_id="stp_test", scene_id="scene",
        mask_storage_uri="s3://bucket/mask.tif", index_label="NDVI", quantity_label="NDVI 0.20 to 0.40",
        region_label="Sparse vegetation", lower=0.2, upper=0.4, obscured_fraction=None, unphysical_fraction=0.0,
    )

    assert len(evidence.claims) == 1
    claim = evidence.claims[0]
    assert claim.kind is ClaimKind.NEGATIVE and claim.is_primary
    assert claim.text.startswith("No sparse vegetation")
    assert claim.evidence_ids, "an asserted absence still points at what was searched"
    assert evidence.vector_layer.features == []


async def test_small_regions_are_measured_but_not_drawn() -> None:
    detected = np.zeros((ROWS, COLUMNS), dtype=bool)
    detected[0:10, 0:10] = True  # 100 px, drawn
    detected[40, 40] = True  # 1 px, counted, not drawn
    statistics = await measure_mask(detected, np.ones_like(detected), transform=TRANSFORM, crs=SCENE_CRS)

    evidence = await build_region_evidence(
        detected, np.full(detected.shape, 0.3, dtype=np.float32), statistics=statistics, transform=TRANSFORM,
        crs=SCENE_CRS, resolution_metres=10.0, run_id="run_test", trace_step_id="stp_test", scene_id="scene",
        mask_storage_uri="s3://bucket/mask.tif", index_label="NDVI", quantity_label="NDVI 0.20 to 0.40",
        region_label="Sparse vegetation", lower=0.2, upper=0.4, obscured_fraction=None, unphysical_fraction=0.0,
    )

    assert evidence.regions_total == 2 and evidence.regions_drawn == 1
    regions_item = next(item for item in evidence.evidence if item.title == "Sparse vegetation regions")
    # The claim's hectares are the whole mask, 101 pixels; the drawing is the one region large enough.
    assert regions_item.area_hectares == pytest.approx(statistics.detected.hectares)
    assert statistics.detected.pixel_count == 101
    assert "1 of 2 drawn" in evidence.vector_layer.title


# ── The graph, end to end ────────────────────────────────────────────────────────────────────────


# `loop_scope="session"`, because the storage client is a process-wide singleton bound to the loop that
# opened it (`tests/conftest.py`). An async fixture on its own function loop would open the client there,
# and the second test would find it bound to a loop that has since closed.
@pytest_asyncio.fixture(loop_scope="session")
async def completed_run(scene: Path, isolated_pipeline_paths: Path):  # noqa: F811 - pytest fixture injection
    """One real run of the six-node graph, with its recorder and checkpoint values."""
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = build_single_image_graph().compile(checkpointer=checkpointer, store=store)
        run_id, recorder, status = await run_index_query(scene, graph)
        snapshot = await read_thread_state(graph, run_id)
    assert status is RunStatus.COMPLETE
    return run_id, recorder, snapshot.values


@pytest.mark.integration
async def test_gate_1_every_claim_resolves_to_pixels(completed_run: tuple[str, Recorder, dict[str, Any]]) -> None:
    run_id, recorder, values = completed_run
    graph = json.loads(evidence_graph_path(run_id).read_text(encoding="utf-8"))
    layers = {layer["id"]: layer for layer in graph["layers"]}
    evidence = {item["id"]: item for item in graph["evidence"]}
    features = {feature["id"]: feature for layer in graph["layers"] for feature in layer["features"]}

    with rasterio.open(Path(values["mask_path"])) as dataset:
        detected = dataset.read(1) == DETECTION_MASK_DETECTED
        transform = dataset.transform
    to_scene = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_user_input(SCENE_CRS), always_xy=True)

    assert graph["claims"], "the run made no claims"
    walked = 0
    for claim in graph["claims"]:
        assert claim["evidenceIds"]
        for evidence_id in claim["evidenceIds"]:
            item = evidence[evidence_id]
            if item["kind"] == EvidenceKind.STATISTIC.value:
                assert item["layerId"] is None
                continue
            layer = layers[item["layerId"]]
            assert layer["provenance"]["traceStepId"] == claim["traceStepId"]
            for feature_id in item["featureIds"]:
                ring = [(p["longitude"], p["latitude"]) for p in features[feature_id]["geometry"]["ring"]]
                polygon = transform_geometry(to_scene.transform, Polygon(ring))
                footprint = rasterize([(polygon, 1)], out_shape=detected.shape, transform=transform, dtype=np.uint8) == 1
                # The sparse half is one solid rectangle: the ring is the region, pixel for pixel.
                assert np.array_equal(footprint, detected), f"feature {feature_id} is not the pixels it claims"
                walked += 1
    assert walked >= 2, "the primary and the largest-region claims both reach the raster"


@pytest.mark.integration
async def test_gate_2_artefact_producing_steps_name_their_layer_and_the_record_their_uri(
    completed_run: tuple[str, Recorder, dict[str, Any]],
) -> None:
    run_id, recorder, values = completed_run
    completed = {s.step.stage_code: s.step for s in recorder.steps(TraceStepState.COMPLETED)}
    emitted_layers = {e.layer.id: e.layer for e in recorder.events if isinstance(e, LayerReadyEvent)}

    assert emitted_layers[completed[PipelineStage.S12].artefact_layer_id].kind is LayerKind.RASTER_TILES
    assert emitted_layers[completed[PipelineStage.S15].artefact_layer_id].kind is LayerKind.POLYGON_VECTOR
    # S7's SCL mask has no fleet model to attribute a layer to; the artefact is still recorded (below).
    assert completed[PipelineStage.S7].artefact_layer_id is None

    record = json.loads(provenance_path(run_id).read_text(encoding="utf-8"))
    by_stage = {artefact["stage"]: artefact for artefact in record["artefacts"]}
    assert set(by_stage) == {"S7", "S12", "S15"}
    for artefact in record["artefacts"]:
        assert artefact["storageUri"].startswith("s3://") and artefact["objectKey"].startswith(run_id)
    assert by_stage["S12"]["layerId"] == completed[PipelineStage.S12].artefact_layer_id
    assert by_stage["S7"]["layerId"] is None
    # Every file the run read: the two index bands (S12) and the classification layer the mask came from
    # (S7, recorded from 1.10) - the record names what the numbers depend on, and the mask is one of those.
    assert {record["bandId"] for record in record["inputs"]} == {"B08", "B04", "SCL"}
    assert all(len(record["sha256"]) == 64 for record in record["inputs"])
    assert record["confidenceAggregationRule"] == CONFIDENCE_AGGREGATION_RULE
    assert record["confidence"] is None
    assert {model["modelId"] for model in record["models"]} == {"index-engine", "geospatial-engine"}
    assert set(record["claimIds"]) == {claim["id"] for claim in json.loads(evidence_graph_path(run_id).read_text(encoding="utf-8"))["claims"]}


@pytest.mark.integration
async def test_gate_3_every_figure_resolves_to_a_step_and_the_primary_carries_its_claims(
    completed_run: tuple[str, Recorder, dict[str, Any]],
) -> None:
    _, recorder, _ = completed_run
    steps = {s.step.id for s in recorder.steps(TraceStepState.COMPLETED)}
    figures = [e for e in recorder.events if isinstance(e, FigureReadyEvent)]
    claims = [e.claim.id for e in recorder.events if isinstance(e, ClaimEvent)]

    assert figures and all(figure.trace_step_id in steps for figure in figures)
    primary = [figure for figure in figures if figure.is_primary]
    assert len(primary) == 1
    assert set(primary[0].claim_ids) == set(claims)
    # Layers and claims arrive before the answer that speaks them, and claims after the layers they cite.
    types = [e.type for e in recorder.events]
    assert types.index("layer-ready") < types.index("claim") < types.index("answer-token")


@pytest.mark.integration
async def test_gate_4_the_journal_and_the_evidence_graph_validate_against_the_contracts(
    completed_run: tuple[str, Recorder, dict[str, Any]],
) -> None:
    run_id, _, _ = completed_run
    graph = json.loads(evidence_graph_path(run_id).read_text(encoding="utf-8"))
    assert not list(validator(EVIDENCE_GRAPH_SCHEMA).iter_errors(graph))

    not_yet = {event_type.value for event_type in EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND}
    union = validator(UNION)
    lines = [json.loads(line) for line in journal_path(run_id).read_text(encoding="utf-8").splitlines()]
    for index, payload in enumerate(lines):
        if payload["type"] in not_yet:
            continue
        errors = [error.message for error in union.iter_errors(payload)]
        assert not errors, f"line {index + 1} ({payload['type']}): {errors[:1]}"
    assert {payload["type"] for payload in lines} >= {"layer-ready", "claim"}


@pytest.mark.integration
async def test_the_answer_speaks_the_claims_and_nothing_a_claim_does_not_carry(
    completed_run: tuple[str, Recorder, dict[str, Any]],
) -> None:
    _, _, values = completed_run
    answer = " ".join(values["answer_tokens"])
    claim_texts = [claim["text"] for claim in values["claims"]]

    for text in claim_texts:
        assert text in answer
    # What is left once the claims are removed is the caveat about the mask - and its number is on the
    # primary claim as a metric, so nothing the answer says is a figure no claim carries (invariant 15).
    remainder = answer
    for text in claim_texts:
        remainder = remainder.replace(text, "")
    assert "masked before the arithmetic" in remainder
    primary = next(claim for claim in values["claims"] if claim["isPrimary"])
    obscured = next(metric for metric in primary["metrics"] if metric["label"] == "Obscured by cloud and shadow")
    assert f"{obscured['value'] / 100:.1%}" in remainder
    assert obscured["value"] == pytest.approx(values["obscured_fraction"] * 100)


@pytest.mark.integration
async def test_the_confidence_is_declined_by_every_deterministic_stage_and_so_by_the_run(
    completed_run: tuple[str, Recorder, dict[str, Any]],
) -> None:
    _, recorder, values = completed_run
    assert values["confidence"] is None
    assert values["confidence_aggregation_rule"] == CONFIDENCE_AGGREGATION_RULE
    assert all(record["confidence"] is None for record in values["stage_models"])
    s18 = next(s.step for s in recorder.steps(TraceStepState.COMPLETED) if s.step.stage_code is PipelineStage.S18)
    assert "none stated" in (s18.detail or "")
