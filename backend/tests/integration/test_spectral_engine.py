"""Tests the Phase 1.4 service boundaries and the gate behind them, on a scene whose answers are known by construction.

what  : The query table, band reading with grid harmonisation and the two refusals, the SCL mask, the
        mask-before-arithmetic rule, the measurement, and the index-query graph end to end - including a
        run resumed after S12 whose local artefact has been deleted.
where : `tests/integration`, because rasterio file I/O and the figure storage path are part of what is
        asserted. The graph tests need MinIO (figures and artefacts) and are marked `integration`.
how   : One synthetic L2A scene: 64x64 at 10 m in UTM 43N, red 0.10 everywhere, near-infrared 0.50 on the
        left half and 0.20 on the right, so NDVI is 0.667 (dense) and 0.333 (sparse) with no rounding
        ambiguity. A 20 m SWIR band and a 20 m scene classification layer exercise resampling; the SCL
        carries a cloud block, a shadow block and a nodata block, all in the *left* half, so the sparse
        region on the right is exactly 32 x 64 = 2048 pixels and its area has an independent value from
        pyproj's geodesic integration. The demonstration on the real scene is `aeris analyse`, recorded at
        the bottom of this file.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import rasterio
from jsonschema import Draft202012Validator
from pyproj import CRS, Geod, Transformer
from rasterio.transform import from_origin

from app.cli.renderers.journal_writer import journal_path, open_journal
from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.events import EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.preprocessing import MASK_CLOUD, MASK_SHADOW, MASK_UNOBSERVED
from app.constants.raster import REFLECTANCE_OFFSET, REFLECTANCE_SCALE, BandRole, ProcessingLevel
from app.constants.spectral import SpectralIndex
from app.constants.stages import PipelineStage
from app.constants.statuses import RunStatus, TraceStepState
from app.lib.exceptions import ConflictError, InvalidRequestError
from app.schemas.events import AnalysisStreamEvent, FigureReadyEvent, RunCompleteEvent, TraceStepEvent
from app.services.evidence.spatial import measure_mask
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs.index_query import build_index_query_graph
from app.services.pipeline.memory_store import open_memory_store
from app.services.preprocessing.cloud_masking import (
    decode_mask_raster,
    encode_mask_raster,
    mask_from_scene_classification,
)
from app.services.sessions.fanout import EventFanout
from app.services.sessions.session import open_session
from app.services.spectral.indices import (
    compute_index,
    read_scene_bands,
    read_scene_classification,
    resolve_index_target,
)

SCENE_CRS = "EPSG:32643"
WEST, NORTH = 268410.0, 2113350.0
ROWS, COLUMNS = 64, 64
RED, NIR_DENSE, NIR_SPARSE, GREEN, BLUE, SWIR = 0.10, 0.50, 0.20, 0.08, 0.05, 0.30

# SCL blocks, in 20 m pixels, all on the left half of the scene.
CLOUD_BLOCK = (slice(0, 4), slice(0, 4))
SHADOW_BLOCK = (slice(8, 12), slice(0, 4))
NODATA_BLOCK = (slice(28, 32), slice(0, 4))
SCL_VEGETATION, SCL_SHADOW, SCL_CLOUD_HIGH, SCL_NODATA = 4, 3, 9, 0


def digital_numbers(reflectance: np.ndarray) -> np.ndarray:
    """Reflectance to stored integers, plus a one-count checkerboard so no band is constant - S6 refuses a
    flat raster as a failed download, correctly. One count is 0.0001 reflectance, below every tolerance."""
    counts = np.round(reflectance * REFLECTANCE_SCALE + REFLECTANCE_OFFSET).astype(np.uint16)
    rows, columns = np.indices(counts.shape)
    return counts + ((rows + columns) % 2).astype(np.uint16)


def write_band(path: Path, values: np.ndarray, resolution: float, nodata: int | None = 0) -> None:
    with rasterio.open(
        path, "w", driver="GTiff", height=values.shape[0], width=values.shape[1], count=1,
        dtype=values.dtype, crs=SCENE_CRS, transform=from_origin(WEST, NORTH, resolution, resolution),
        nodata=nodata,
    ) as destination:
        destination.write(values, 1)


@pytest.fixture
def scene(tmp_path: Path) -> Path:
    """A synthetic L2A scene directory whose name carries the level, as `aeris dataset fetch` writes it."""
    directory = tmp_path / "S2A_MSIL2A_20260101T000000_R000_T43QBB_SYNTHETIC"
    directory.mkdir()
    near_infrared = np.full((ROWS, COLUMNS), NIR_DENSE, dtype=np.float32)
    near_infrared[:, COLUMNS // 2:] = NIR_SPARSE
    for name, reflectance in (
        ("B02", np.full((ROWS, COLUMNS), BLUE, dtype=np.float32)),
        ("B03", np.full((ROWS, COLUMNS), GREEN, dtype=np.float32)),
        ("B04", np.full((ROWS, COLUMNS), RED, dtype=np.float32)),
        ("B08", near_infrared),
    ):
        write_band(directory / f"{name}.tif", digital_numbers(reflectance), 10.0)
    write_band(directory / "B11.tif", digital_numbers(np.full((ROWS // 2, COLUMNS // 2), SWIR, dtype=np.float32)), 20.0)

    classification = np.full((ROWS // 2, COLUMNS // 2), SCL_VEGETATION, dtype=np.uint8)
    classification[CLOUD_BLOCK] = SCL_CLOUD_HIGH
    classification[SHADOW_BLOCK] = SCL_SHADOW
    classification[NODATA_BLOCK] = SCL_NODATA
    write_band(directory / "SCL.tif", classification, 20.0, nodata=None)
    return directory


def copy_scene(scene: Path, destination: Path) -> Path:
    """The same bands under another directory name. Sync, so the test above it stays a coroutine that awaits."""
    destination.mkdir()
    for band in scene.glob("*.tif"):
        (destination / band.name).write_bytes(band.read_bytes())
    return destination


def geodesic_hectares(column_start: int, column_stop: int, row_start: int, row_stop: int) -> float:
    """Independent area of a pixel rectangle: pyproj's ellipsoidal integration, no projection involved."""
    x = np.array([column_start, column_stop, column_stop, column_start]) * 10.0 + WEST
    y = NORTH - np.array([row_start, row_start, row_stop, row_stop]) * 10.0
    longitude, latitude = Transformer.from_crs(
        CRS.from_user_input(SCENE_CRS), CRS.from_epsg(4326), always_xy=True
    ).transform(x, y)
    area, _ = Geod(ellps="WGS84").polygon_area_perimeter(longitude, latitude)
    return abs(area) / 10_000.0


# ── The query table ──────────────────────────────────────────────────────────────────────────────


async def test_the_longest_phrase_wins_so_unhealthy_is_not_answered_as_vegetation() -> None:
    target = await resolve_index_target("Show me the unhealthy vegetation in the north")

    assert target.index is SpectralIndex.NDVI
    assert (target.lower, target.upper) == (0.2, 0.4)
    assert target.label == "Sparse vegetation"
    assert target.phrase == "unhealthy vegetation"


async def test_a_bare_index_name_asks_for_the_map_and_no_range() -> None:
    target = await resolve_index_target("what does the NDWI look like here")

    assert target.index is SpectralIndex.NDWI
    assert not target.has_range


async def test_a_question_no_index_answers_is_refused_with_the_phrases_it_knows() -> None:
    with pytest.raises(InvalidRequestError, match="unhealthy vegetation"):
        await resolve_index_target("how many ships are in the harbour")


async def test_phrases_match_whole_words_only() -> None:
    # "urbanisation" contains "urban"; it is not the phrase, and matching it would route by accident.
    with pytest.raises(InvalidRequestError):
        await resolve_index_target("rate of urbanisation")


# ── Reading bands ────────────────────────────────────────────────────────────────────────────────


async def test_bands_are_read_as_reflectance_on_the_finest_grid(scene: Path) -> None:
    bands = await read_scene_bands(scene, (BandRole.NEAR_INFRARED, BandRole.RED))

    assert bands.processing_level is ProcessingLevel.L2A
    assert bands.reference.path.name == "B08.tif"
    assert bands.bands[BandRole.RED].reflectance[0, 0] == pytest.approx(RED, abs=2e-4)
    assert bands.bands[BandRole.NEAR_INFRARED].reflectance[0, 0] == pytest.approx(NIR_DENSE, abs=2e-4)
    assert bands.bands[BandRole.NEAR_INFRARED].reflectance[0, -1] == pytest.approx(NIR_SPARSE, abs=2e-4)
    assert not any(band.resampled for band in bands.bands.values())


async def test_a_twenty_metre_band_is_resampled_onto_the_ten_metre_grid_before_it_is_used(scene: Path) -> None:
    """§8 rule 6 and rule 10. MNDWI needs green at 10 m and SWIR at 20 m; they meet on one grid or not at all."""
    bands = await read_scene_bands(scene, (BandRole.GREEN, BandRole.SHORTWAVE_INFRARED_1))

    swir = bands.bands[BandRole.SHORTWAVE_INFRARED_1]
    assert swir.resampled
    assert swir.band_id == "B11"
    assert swir.reflectance.shape == (ROWS, COLUMNS)
    assert swir.reflectance[10, 10] == pytest.approx(SWIR, abs=2e-4)
    assert bands.bands[BandRole.GREEN].reflectance.shape == (ROWS, COLUMNS)


async def test_a_missing_band_is_refused_by_name(scene: Path) -> None:
    with pytest.raises(InvalidRequestError, match="swir-2"):
        await read_scene_bands(scene, (BandRole.NEAR_INFRARED, BandRole.SHORTWAVE_INFRARED_2))


async def test_an_unknown_level_is_refused_unless_a_human_declares_it(scene: Path, tmp_path: Path) -> None:
    """§8 rule 5. The same bands under a name that says nothing about the level."""
    anonymous = copy_scene(scene, tmp_path / "research_subset")

    with pytest.raises(ConflictError, match="unknown"):
        await read_scene_bands(anonymous, (BandRole.NEAR_INFRARED, BandRole.RED))

    declared = await read_scene_bands(
        anonymous, (BandRole.NEAR_INFRARED, BandRole.RED), declared_level=ProcessingLevel.L2A
    )
    assert declared.processing_level is ProcessingLevel.L2A


async def test_top_of_atmosphere_is_refused_even_when_the_path_says_so(scene: Path, tmp_path: Path) -> None:
    level_one = copy_scene(scene, tmp_path / "S2A_MSIL1C_20260101T000000_R000_T43QBB_SYNTHETIC")

    with pytest.raises(ConflictError, match="L1C"):
        await read_scene_bands(level_one, (BandRole.NEAR_INFRARED, BandRole.RED))


# ── S7 from the scene classification ─────────────────────────────────────────────────────────────


async def test_the_scene_classification_arrives_on_the_analysis_grid_with_nearest_neighbour(scene: Path) -> None:
    bands = await read_scene_bands(scene, (BandRole.NEAR_INFRARED, BandRole.RED))

    classification = await read_scene_classification(scene, bands.reference)

    assert classification is not None
    assert classification.shape == (ROWS, COLUMNS)
    # Every value is a class that exists; an interpolated 6.5 would be a class that does not.
    assert set(np.unique(classification).tolist()) == {SCL_NODATA, SCL_SHADOW, SCL_VEGETATION, SCL_CLOUD_HIGH}
    assert classification[0, 0] == SCL_CLOUD_HIGH and classification[7, 7] == SCL_CLOUD_HIGH
    assert classification[8, 8] == SCL_VEGETATION


async def test_a_scene_without_a_classification_layer_reports_none_rather_than_a_guess(scene: Path) -> None:
    (scene / "SCL.tif").unlink()
    bands = await read_scene_bands(scene, (BandRole.NEAR_INFRARED, BandRole.RED))

    assert await read_scene_classification(scene, bands.reference) is None


async def test_scl_classes_become_cloud_shadow_and_unobserved() -> None:
    classification = np.array([[4, 9, 3, 0], [8, 10, 1, 7]], dtype=np.uint8)

    mask = await mask_from_scene_classification(classification)

    assert mask.cloud_mask.tolist() == [[False, True, False, False], [True, True, False, False]]
    assert mask.shadow_mask.tolist() == [[False, False, True, False], [False, False, False, False]]
    assert np.isnan(mask.cloud_probability[0, 3]) and np.isnan(mask.cloud_probability[1, 2])
    # Unclassified (7) was seen by the sensor and is observed; nodata (0) and saturated (1) are not.
    assert mask.exclusion_mask.tolist() == [[False, True, True, True], [True, True, True, False]]
    assert mask.obscured_fraction == pytest.approx(6 / 8)


async def test_the_mask_raster_round_trips_through_its_encoding() -> None:
    mask = await mask_from_scene_classification(np.array([[4, 9, 3, 0]], dtype=np.uint8))

    encoded = await encode_mask_raster(mask)
    decoded = await decode_mask_raster(encoded)

    assert encoded.tolist() == [[0, MASK_CLOUD, MASK_SHADOW, MASK_UNOBSERVED]]
    assert np.array_equal(decoded.exclusion_mask, mask.exclusion_mask)
    assert np.array_equal(decoded.cloud_mask, mask.cloud_mask)
    assert np.array_equal(decoded.shadow_mask, mask.shadow_mask)


# ── S12: the mask reaches the bands before the formula ───────────────────────────────────────────


async def test_the_index_is_nan_wherever_the_mask_excluded_before_the_arithmetic(scene: Path) -> None:
    """§8 rule 1. Under cloud, shadow and nodata the index is not a low value; it is no value."""
    bands = await read_scene_bands(scene, (BandRole.NEAR_INFRARED, BandRole.RED))
    mask = await mask_from_scene_classification(await read_scene_classification(scene, bands.reference))

    masked = await compute_index(bands, SpectralIndex.NDVI, mask=mask)
    unmasked = await compute_index(bands, SpectralIndex.NDVI, mask=None)

    assert np.isnan(masked.values[0, 0]), "cloud"
    assert np.isnan(masked.values[16, 0]), "shadow"
    assert np.isnan(masked.values[56, 0]), "SCL nodata"
    assert unmasked.values[0, 0] == pytest.approx((NIR_DENSE - RED) / (NIR_DENSE + RED), abs=1e-3)
    assert masked.values[20, 20] == pytest.approx((NIR_DENSE - RED) / (NIR_DENSE + RED), abs=1e-3)
    assert masked.values[20, 50] == pytest.approx((NIR_SPARSE - RED) / (NIR_SPARSE + RED), abs=1e-3)

    assert masked.mask_applied and masked.obscured_fraction == pytest.approx(3 * 64 / (ROWS * COLUMNS))
    assert not unmasked.mask_applied and unmasked.obscured_fraction is None
    assert masked.band_ids == ["B08", "B04"]


async def test_masked_ground_is_neither_detected_nor_observed_in_the_measurement(scene: Path) -> None:
    bands = await read_scene_bands(scene, (BandRole.NEAR_INFRARED, BandRole.RED))
    mask = await mask_from_scene_classification(await read_scene_classification(scene, bands.reference))
    result = await compute_index(bands, SpectralIndex.NDVI, mask=mask)

    dense = np.nan_to_num(result.values, nan=-2.0) >= 0.4
    statistics = await measure_mask(dense, result.observed, transform=result.transform, crs=result.crs)

    # Left half is dense (2048 px) minus the three 8x8 blocks the mask removed (192 px).
    assert statistics.detected.pixel_count == 2048 - 3 * 64
    assert statistics.observed.pixel_count == ROWS * COLUMNS - 3 * 64
    # A ratio of areas, not of counts: pixel footprints differ across the scene at the sixth digit.
    assert statistics.coverage_fraction == pytest.approx((2048 - 192) / (4096 - 192), rel=1e-5)


async def test_a_detection_over_unobserved_ground_is_refused(scene: Path) -> None:
    """The structural check that S12 masked before it computed: S15 cannot be handed the opposite."""
    bands = await read_scene_bands(scene, (BandRole.NEAR_INFRARED, BandRole.RED))
    result = await compute_index(bands, SpectralIndex.NDVI, mask=None)
    observed = result.observed.copy()
    observed[0, 0] = False
    detected = np.ones_like(observed)

    with pytest.raises(ValueError, match="never observed"):
        await measure_mask(detected, observed, transform=result.transform, crs=result.crs)


# ── The graph, end to end ────────────────────────────────────────────────────────────────────────

CONTRACTS: dict[str, dict[str, Any]] = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
UNION_VALIDATOR = Draft202012Validator(
    CONTRACTS["features/investigation/schemas/analysis.schema.ts"]["analysisStreamEventSchema"],
    format_checker=Draft202012Validator.FORMAT_CHECKER,
)


class Recorder:
    def __init__(self) -> None:
        self.events: list[AnalysisStreamEvent] = []

    async def __call__(self, event: AnalysisStreamEvent) -> None:
        self.events.append(event)

    def steps(self, state: TraceStepState) -> list[TraceStepEvent]:
        return [e for e in self.events if isinstance(e, TraceStepEvent) and e.step.state is state]

    def figures(self) -> list[FigureReadyEvent]:
        return [e for e in self.events if isinstance(e, FigureReadyEvent)]


def initial_state(scene: Path) -> dict[str, Any]:
    return {
        "scene_directory": str(scene), "scene_id": scene.name, "declared_level": None,
        "index": SpectralIndex.NDVI.value, "target_lower": 0.2, "target_upper": 0.4,
        "target_label": "Sparse vegetation", "target_phrase": "unhealthy vegetation",
    }


async def run_index_query(scene: Path, graph: Any) -> tuple[str, Recorder, RunStatus]:
    recorder = Recorder()
    fanout = EventFanout()
    async with open_session() as session:
        handle = await session.start(
            graph=graph, query="unhealthy vegetation", intent=Intent.INDEX_QUERY, fanout=fanout,
            extra_state=initial_state(scene),
        )
        async with open_journal(handle.run_id) as journal:
            fanout.register("journal", journal)
            fanout.register("recorder", recorder)
            status = await handle.wait()
    return handle.run_id, recorder, status


@pytest.mark.integration
async def test_the_gate_the_graph_measures_the_sparse_region_and_says_so(
    scene: Path, isolated_pipeline_paths: Path
) -> None:
    """**The 1.4 gate on a scene whose answer is known.** Map, mask, hectares - and the hectares agree with
    an ellipsoidal integration that shares no code with the measurement."""
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = build_index_query_graph().compile(checkpointer=checkpointer, store=store)
        run_id, recorder, status = await run_index_query(scene, graph)
        snapshot = await read_thread_state(graph, run_id)

    assert status is RunStatus.COMPLETE
    assert [s.step.stage_code for s in recorder.steps(TraceStepState.COMPLETED)] == [
        PipelineStage.S7, PipelineStage.S12, PipelineStage.S15, PipelineStage.S16,
        PipelineStage.S18, PipelineStage.S19,
    ]
    assert len(recorder.steps(TraceStepState.RUNNING)) == 6

    by_stage = {s.step.stage_code: s.step for s in recorder.steps(TraceStepState.COMPLETED)}
    assert "SCL mask" in (by_stage[PipelineStage.S7].detail or "")
    assert by_stage[PipelineStage.S12].model_id == ModelId.INDEX_ENGINE.value
    assert by_stage[PipelineStage.S15].model_id == ModelId.GEOSPATIAL_ENGINE.value
    assert "mask applied" in (by_stage[PipelineStage.S12].detail or "")

    measurement = snapshot.values["measurement"]
    expected_hectares = geodesic_hectares(COLUMNS // 2, COLUMNS, 0, ROWS)
    assert measurement["pixelCount"] == 32 * 64
    assert measurement["areaHectares"] == pytest.approx(expected_hectares, rel=1e-6)
    assert measurement["regionCount"] == 1
    assert measurement["coverageFraction"] == pytest.approx(2048 / (4096 - 192), rel=1e-5)
    assert measurement["equalAreaCrs"].startswith("+proj=laea")

    answer = " ".join(snapshot.values["answer_tokens"])
    assert f"{expected_hectares:,.1f} hectares" in answer
    assert "masked before the arithmetic" in answer
    completion = recorder.events[-1]
    assert isinstance(completion, RunCompleteEvent) and completion.confidence is None


@pytest.mark.integration
async def test_every_figure_resolves_to_a_trace_step_of_this_run_and_one_is_primary(
    scene: Path, isolated_pipeline_paths: Path
) -> None:
    """`api-contract.md` §6 rules 1 and 8, on figures a real run produced rather than hand-built ones."""
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = build_index_query_graph().compile(checkpointer=checkpointer, store=store)
        _, recorder, _ = await run_index_query(scene, graph)

    figures = recorder.figures()
    step_ids = {s.step.id: s.step.stage_code for s in recorder.steps(TraceStepState.COMPLETED)}
    assert [f.kind.value for f in figures] == ["index-map", "rgb-composite", "mask-overlay"]
    assert step_ids[figures[0].trace_step_id] is PipelineStage.S12
    assert step_ids[figures[1].trace_step_id] is PipelineStage.S15
    assert step_ids[figures[2].trace_step_id] is PipelineStage.S15
    assert [f.is_primary for f in figures] == [False, False, True]
    assert figures[0].render_spec.mask_applied is True
    assert figures[0].render_spec.bands == ["B08", "B04"]
    # Figures arrive as they exist, before the run completes - never batched at the end (§6 rule 5).
    types = [e.type for e in recorder.events]
    assert types.index("figure-ready") < types.index("answer-token")


@pytest.mark.integration
async def test_the_journal_validates_against_the_frontend_union(scene: Path, isolated_pipeline_paths: Path) -> None:
    """Every line the frontend can parse today validates; the ones it cannot yet are exactly the agreed set."""
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = build_index_query_graph().compile(checkpointer=checkpointer, store=store)
        run_id, _, _ = await run_index_query(scene, graph)

    lines = [json.loads(line) for line in journal_path(run_id).read_text(encoding="utf-8").splitlines()]
    not_yet = {event_type.value for event_type in EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND}
    for index, payload in enumerate(lines):
        if payload["type"] in not_yet:
            continue
        errors = [error.message for error in UNION_VALIDATOR.iter_errors(payload)]
        assert not errors, f"line {index + 1} ({payload['type']}): {errors}"
    assert {payload["type"] for payload in lines} >= {
        "run-start", "trace-step", "layer-ready", "claim", "figure-ready", "answer-token", "run-complete"
    }


@pytest.mark.integration
async def test_a_run_resumed_after_s12_reads_the_retained_index_rather_than_memory(
    scene: Path, isolated_pipeline_paths: Path
) -> None:
    """§8 rule 12 and the 1.0 resume gate together: S15 in a *new* process would only have the artefact.

    The first graph stops after S12. The local copy of the index artefact is then deleted, so the resumed
    S15 can only proceed by fetching it back from storage - which is what a resume on another machine does.
    """
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        paused = build_index_query_graph().compile(
            checkpointer=checkpointer, store=store, interrupt_after=["extract_features"]
        )
        run_id, first, _ = await run_index_query(scene, paused)
        snapshot = await read_thread_state(paused, run_id)
        assert snapshot.next == ("localise_evidence",)
        assert [s.step.stage_code for s in first.steps(TraceStepState.COMPLETED)] == [PipelineStage.S7, PipelineStage.S12]

        index_path = Path(snapshot.values["index_path"])
        assert await asyncio.to_thread(index_path.exists)
        await asyncio.to_thread(index_path.unlink)

        graph = build_index_query_graph().compile(checkpointer=checkpointer, store=store)
        recorder = Recorder()
        fanout = EventFanout()
        fanout.register("recorder", recorder)
        async with open_session() as session:
            handle = await session.resume(graph=graph, run_id=run_id, intent=Intent.INDEX_QUERY, fanout=fanout)
            status = await handle.wait()
        resumed = await read_thread_state(graph, run_id)

    assert status is RunStatus.COMPLETE
    assert [s.step.stage_code for s in recorder.steps(TraceStepState.COMPLETED)] == [
        PipelineStage.S15, PipelineStage.S16, PipelineStage.S18, PipelineStage.S19
    ]
    assert await asyncio.to_thread(index_path.exists), "the artefact was restored from storage through S15"
    assert resumed.values["measurement"]["pixelCount"] == 32 * 64


@pytest.mark.integration
async def test_a_scene_without_a_mask_source_runs_and_says_it_was_unmasked(
    scene: Path, isolated_pipeline_paths: Path
) -> None:
    (scene / "SCL.tif").unlink()
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = build_index_query_graph().compile(checkpointer=checkpointer, store=store)
        run_id, recorder, status = await run_index_query(scene, graph)
        snapshot = await read_thread_state(graph, run_id)

    assert status is RunStatus.COMPLETE
    by_stage = {s.step.stage_code: s.step for s in recorder.steps(TraceStepState.COMPLETED)}
    assert "no cloud mask" in (by_stage[PipelineStage.S7].detail or "")
    assert snapshot.values["obscured_fraction"] is None
    assert recorder.figures()[0].render_spec.mask_applied is False
    assert "No cloud mask was available" in " ".join(snapshot.values["answer_tokens"])
    # With nothing masked, all 4096 pixels are observed and the sparse half is still exactly 2048.
    assert snapshot.values["measurement"]["coverageFraction"] == pytest.approx(0.5, rel=1e-5)


@pytest.mark.integration
async def test_a_map_only_question_measures_nothing_and_draws_no_mask(scene: Path, isolated_pipeline_paths: Path) -> None:
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = build_index_query_graph().compile(checkpointer=checkpointer, store=store)
        recorder = Recorder()
        fanout = EventFanout()
        fanout.register("recorder", recorder)
        async with open_session() as session:
            handle = await session.start(
                graph=graph, query="ndvi", intent=Intent.INDEX_QUERY, fanout=fanout,
                extra_state={**initial_state(scene), "target_lower": None, "target_upper": None, "target_label": "NDVI"},
            )
            status = await handle.wait()
        snapshot = await read_thread_state(graph, handle.run_id)

    assert status is RunStatus.COMPLETE
    assert snapshot.values["measurement"] is None
    assert [f.kind.value for f in recorder.figures()] == ["index-map"]
    fractions = snapshot.values["band_fractions"]
    # Left half dense, right half sparse, less the three masked blocks on the left.
    assert fractions["Dense healthy vegetation"] == pytest.approx((2048 - 192) / (4096 - 192))
    assert fractions["Sparse vegetation"] == pytest.approx(2048 / (4096 - 192))
