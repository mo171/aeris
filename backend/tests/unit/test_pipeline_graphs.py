"""The 1.10 pieces that need no model: what an input is, how a picture is measured, how the graphs route, and how a detector's boxes become claims.

what  : Unit tests for `services/imagery/frames.py`, `services/evidence/builder.py` (detections, a
        picture's regions), `services/evidence/spatial.py` (nominal and pixel statistics),
        `services/segmentation/classes.py`, `services/preprocessing/coregistration.py` (tolerance and
        tile size), and the routing tables of the two graphs.
where : Unit suite; synthetic pictures and rasters written to `tmp_path`, no model, no storage.
how   : Each test names the wrong answer it holds off: a picture claimed as georeferenced, hectares
        invented for a photograph, a class the detector could not see at this resolution reported as
        found, a branch a graph cannot reach, a tolerance in pixels where the rule is in metres.
"""

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from app.constants.evidence import ClaimKind, EvidenceKind
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.pipeline import GraphName
from app.constants.preprocessing import MAXIMUM_COREGISTRATION_RESIDUAL_METRES, MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS
from app.constants.routing import INTENT_GRAPHS
from app.constants.scenes import SceneModality
from app.lib.exceptions import InvalidRequestError
from app.services.detection.math.oriented_boxes import OrientedBox
from app.services.evidence.builder import build_detection_evidence, build_region_evidence, hectares_precision_for
from app.services.evidence.spatial import measure_mask_nominal, measure_mask_on_grid, measure_mask_pixels
from app.services.imagery.frames import FrameStretch, InputKind, inspect_input, read_rgb_frame
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.graphs.cross_modal import build_cross_modal_graph
from app.services.pipeline.graphs.single_image import (
    FIRST_STAGE_BY_INTENT,
    GROUND_STAGE_BY_TOOL,
    LOCALISER_BY_STAGE,
    after_inputs,
    first_stage,
)
from app.services.pipeline.graphs.temporal import AFTER_CHANGE_BY_INTENT, after_change
from app.services.preprocessing.coregistration import tile_size_for, tolerance_for
from app.services.segmentation.classes import resolve_landcover_classes, unresolved_landcover_words

IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
UTM = "EPSG:32643"
# A 10 m grid near Mumbai, as the real subset is placed.
UTM_TRANSFORM = (10.0, 0.0, 268410.0, 0.0, -10.0, 2113350.0)


@pytest.fixture
def picture(tmp_path):
    path = tmp_path / "crop.png"
    Image.fromarray(np.random.default_rng(1).integers(0, 255, (64, 96, 3), dtype=np.uint8)).save(path)
    return path


@pytest.fixture
def raster(tmp_path):
    path = tmp_path / "drone.tif"
    data = np.random.default_rng(2).integers(0, 255, (3, 40, 50), dtype=np.uint8)
    with rasterio.open(
        path, "w", driver="GTiff", width=50, height=40, count=3, dtype="uint8", crs=UTM, transform=from_origin(268410.0, 2113350.0, 2.0, 2.0),
    ) as dataset:
        dataset.write(data)
    return path


# ── What an input is ─────────────────────────────────────────────────────────────────────────────


async def test_a_picture_is_a_picture_and_nothing_is_guessed_about_its_ground(picture) -> None:
    source = await inspect_input(picture)
    assert source.kind is InputKind.PICTURE and not source.georeferenced and source.crs is None
    assert source.resolution_metres is None and not source.resolution_declared
    assert source.modality is SceneModality.OPTICAL and (source.height, source.width) == (64, 96)
    assert source.files == (picture,)


async def test_a_declared_pixel_size_is_carried_as_a_declaration(picture) -> None:
    source = await inspect_input(picture, declared_resolution_metres=0.5)
    assert source.resolution_metres == 0.5 and source.resolution_declared
    assert "0.5 m (declared)" in source.describe()
    with pytest.raises(InvalidRequestError, match="positive"):
        await inspect_input(picture, declared_resolution_metres=0.0)


async def test_a_projected_raster_states_its_own_resolution_and_a_declaration_does_not_override_it(raster) -> None:
    source = await inspect_input(raster, declared_resolution_metres=0.5)
    assert source.kind is InputKind.RASTER and source.georeferenced and source.crs == UTM
    assert source.resolution_metres == 2.0 and not source.resolution_declared


async def test_a_missing_path_is_refused_by_name(tmp_path) -> None:
    with pytest.raises(InvalidRequestError, match="neither a scene directory nor an image"):
        await inspect_input(tmp_path / "nowhere.png")


async def test_the_frame_is_the_picture_bytes_and_the_model_sees_nan_where_nothing_was_observed(picture) -> None:
    frame = await read_rgb_frame(await inspect_input(picture))
    assert frame.stretch is FrameStretch.BYTES and frame.rgb.dtype == np.uint8 and frame.observed.all()
    assert np.array_equal(frame.rgb, np.asarray(Image.open(picture).convert("RGB")))
    records = await frame.input_records()
    assert len(records) == 1 and records[0]["bandId"] == "rgb" and len(records[0]["sha256"]) == 64


# ── Measuring a picture ──────────────────────────────────────────────────────────────────────────


def test_hectares_precision_follows_the_pixel() -> None:
    assert hectares_precision_for(10.0) == 1
    assert hectares_precision_for(20.0) == 1
    assert hectares_precision_for(1.0) == 3
    assert hectares_precision_for(0.5) == 4
    assert hectares_precision_for(0.3) == 4  # the contract's ceiling
    assert hectares_precision_for(None) == 1


async def test_nominal_statistics_are_count_times_declared_pixel_and_say_so() -> None:
    detected = np.zeros((8, 8), dtype=bool)
    detected[:2, :4] = True
    observed = np.ones((8, 8), dtype=bool)
    statistics = await measure_mask_nominal(detected, observed, resolution_metres=0.5)
    assert statistics.has_area and statistics.detected.square_metres == pytest.approx(8 * 0.25)
    assert statistics.coverage_fraction == pytest.approx(8 / 64) and "nominal" in statistics.equal_area_crs


async def test_pixel_statistics_have_no_area_and_a_share_of_pixels() -> None:
    detected = np.zeros((8, 8), dtype=bool)
    detected[0, :4] = True
    observed = np.ones((8, 8), dtype=bool)
    observed[7] = False
    statistics = await measure_mask_pixels(detected, observed)
    assert not statistics.has_area and np.isnan(statistics.detected.square_metres)
    assert statistics.coverage_fraction == pytest.approx(4 / 56)


async def test_measure_on_grid_chooses_by_what_the_input_is() -> None:
    detected = np.zeros((4, 4), dtype=bool)
    detected[0, 0] = True
    observed = np.ones((4, 4), dtype=bool)
    geodetic = await measure_mask_on_grid(detected, observed, transform=UTM_TRANSFORM, crs=UTM, resolution_metres=10.0, resolution_declared=False)
    nominal = await measure_mask_on_grid(detected, observed, transform=IDENTITY, crs=None, resolution_metres=0.5, resolution_declared=True)
    pixels = await measure_mask_on_grid(detected, observed, transform=IDENTITY, crs=None, resolution_metres=None, resolution_declared=False)
    assert geodetic.has_area and geodetic.equal_area_crs.startswith("+proj")
    assert nominal.has_area and nominal.equal_area_crs.startswith("nominal")
    assert not pixels.has_area


async def test_a_pictures_regions_are_claims_without_layers_and_the_hectares_are_labelled_nominal() -> None:
    detected = np.zeros((32, 32), dtype=bool)
    detected[4:12, 4:12] = True
    observed = np.ones((32, 32), dtype=bool)
    statistics = await measure_mask_nominal(detected, observed, resolution_metres=0.5)
    evidence = await build_region_evidence(
        detected, np.where(detected, 0.9, 0.1).astype(np.float32), statistics=statistics, transform=IDENTITY, crs=None, resolution_metres=0.5,
        run_id="run_t", trace_step_id="trc_t", scene_id="crop", mask_storage_uri=None, index_label="change probability",
        quantity_label="p >= 0.50", region_label="Change", lower=0.5, upper=1.0, obscured_fraction=None, unphysical_fraction=0.0,
        model_id=ModelId.CHANGEFORMER, model_version="v6", confidence=0.9, evidence_kind=EvidenceKind.CHANGE_MASK, nominal_resolution=True,
    )
    assert evidence.raster_layer is None and evidence.vector_layer is None and evidence.layers == []
    primary = evidence.claims[0]
    assert primary.is_primary and primary.kind is ClaimKind.QUANTITATIVE and primary.model_id is ModelId.CHANGEFORMER
    assert "(nominal, at 0.5 m per pixel)" in primary.text and "0.0016 hectares" in primary.text
    labels = {metric.label for metric in primary.metrics}
    assert {"Area (nominal)", "Declared ground sample distance", "Regions"} <= labels
    assert all(item.layer_id is None for item in evidence.evidence)
    assert evidence.evidence[0].kind is EvidenceKind.CHANGE_MASK


async def test_a_picture_with_no_pixel_size_is_claimed_in_pixels() -> None:
    detected = np.zeros((16, 16), dtype=bool)
    detected[:4, :4] = True
    observed = np.ones((16, 16), dtype=bool)
    statistics = await measure_mask_pixels(detected, observed)
    evidence = await build_region_evidence(
        detected, detected.astype(np.float32), statistics=statistics, transform=IDENTITY, crs=None, resolution_metres=None,
        run_id="run_t", trace_step_id="trc_t", scene_id="crop", mask_storage_uri=None, index_label="confidence", quantity_label="class",
        region_label="Building", lower=0.0, upper=1.0, obscured_fraction=None, unphysical_fraction=0.0,
    )
    text = evidence.claims[0].text
    assert "16 pixels" in text and "no ground size is known" in text and "hectare" not in text
    assert {metric.label for metric in evidence.claims[0].metrics} == {"Pixels", "Share of observed pixels", "Regions", "Observed pixels"}


# ── Detections as evidence ───────────────────────────────────────────────────────────────────────


def _box(class_index: int, score: float, x: float, y: float, size: float = 10.0) -> OrientedBox:
    return OrientedBox(class_index, score, np.array([[x, y], [x + size, y], [x + size, y + size], [x, y + size]], dtype=np.float32))


async def test_detections_over_a_picture_are_counts_with_scores_and_no_layer() -> None:
    boxes = [_box(0, 0.9, 10, 10), _box(0, 0.7, 40, 40), _box(1, 0.8, 70, 20)]
    evidence = await build_detection_evidence(
        boxes, ("plane", "ship"), asked=("plane", "storage tank"), shape=(100, 100), transform=IDENTITY, crs=None, resolution_metres=None,
        run_id="run_t", trace_step_id="trc_t", scene_id="crop", model_id=ModelId.DOTA_DETECTOR, model_version="v1", score_threshold=0.25,
        observed_fraction=1.0, wants_location=True,
    )
    assert evidence.layer is None and evidence.counts == {"plane": 2, "storage tank": 0, "ship": 1}
    by_text = {claim.text: claim for claim in evidence.claims}
    planes = by_text["The detector found 2 planes in crop, with a mean score of 0.80."]
    assert planes.is_primary and planes.confidence == pytest.approx(0.8) and {m.label for m in planes.metrics} == {"Count", "Mean score"}
    tanks = next(claim for claim in evidence.claims if claim.kind is ClaimKind.NEGATIVE)
    assert "No storage tanks were detected" in tanks.text and tanks.confidence is None
    assert {m.label for m in tanks.metrics} == {"Count", "Score threshold", "Observed share"}
    where = next(claim for claim in evidence.claims if claim.kind is ClaimKind.SPATIAL)
    assert "pixel column 15, row 15" in where.text and where.confidence == pytest.approx(0.9)
    also = next(claim for claim in evidence.claims if claim.text.startswith("Also found"))
    assert "1 ship" in also.text and not also.is_primary
    # Every claim points at an evidence record of its class; every record is a detection.
    ids = {item.id for item in evidence.evidence}
    assert all(set(claim.evidence_ids) <= ids for claim in evidence.claims)
    assert {item.kind for item in evidence.evidence} == {EvidenceKind.DETECTION}


async def test_detections_over_a_scene_are_placed_on_a_layer_with_a_geographic_ring_each() -> None:
    boxes = [_box(0, 0.9, 10, 10), _box(0, 0.6, 500, 300, 20.0)]
    evidence = await build_detection_evidence(
        boxes, ("plane",), asked=("plane",), shape=(1120, 1066), transform=UTM_TRANSFORM, crs=UTM, resolution_metres=10.0,
        run_id="run_t", trace_step_id="trc_t", scene_id="mumbai_gate", model_id=ModelId.DOTA_DETECTOR, model_version="v1",
        score_threshold=0.25, observed_fraction=0.98, wants_location=True,
    )
    assert evidence.layer is not None and len(evidence.layer.features) == 2
    feature = evidence.layer.features[0]
    assert feature.class_id == "plane" and feature.confidence == pytest.approx(0.9) and len(feature.geometry.ring) == 4
    assert all(72.0 < point.longitude < 73.5 and 18.5 < point.latitude < 19.5 for point in feature.geometry.ring)
    assert evidence.layer.bounds is not None and evidence.layer.provenance.confidence == pytest.approx(0.75)
    where = next(claim for claim in evidence.claims if claim.kind is ClaimKind.SPATIAL)
    assert "latitude 19." in where.text and "longitude 72." in where.text
    assert evidence.evidence[0].layer_id == evidence.layer.id and len(evidence.evidence[0].feature_ids) == 2


async def test_nothing_asked_means_every_class_found_is_claimed() -> None:
    boxes = [_box(0, 0.9, 10, 10), _box(1, 0.8, 70, 20)]
    evidence = await build_detection_evidence(
        boxes, ("plane", "ship"), asked=(), shape=(100, 100), transform=IDENTITY, crs=None, resolution_metres=None, run_id="run_t",
        trace_step_id="trc_t", scene_id="crop", model_id=ModelId.DOTA_DETECTOR, model_version="v1", score_threshold=0.25,
        observed_fraction=1.0, wants_location=False,
    )
    assert sorted(claim.text for claim in evidence.claims) == [
        "The detector found 1 plane in crop, with a mean score of 0.90.", "The detector found 1 ship in crop, with a mean score of 0.80.",
    ]


# ── Land-cover words ─────────────────────────────────────────────────────────────────────────────


def test_landcover_words_resolve_in_order_and_unknown_things_are_named() -> None:
    assert resolve_landcover_classes("outline the water bodies and the roads") == ("Water", "Road")
    assert resolve_landcover_classes("extract building footprints") == ("Building",)
    assert resolve_landcover_classes("classify the land cover") == ()
    assert unresolved_landcover_words("segment the runways") == ("runways",)
    assert unresolved_landcover_words("segment the buildings") == ()


# ── The gate's units ─────────────────────────────────────────────────────────────────────────────


def test_the_registration_tolerance_is_metres_where_the_resolution_is_known() -> None:
    assert tolerance_for(10.0) == (MAXIMUM_COREGISTRATION_RESIDUAL_METRES / 10.0, MAXIMUM_COREGISTRATION_RESIDUAL_METRES)
    assert tolerance_for(0.5) == (10.0, MAXIMUM_COREGISTRATION_RESIDUAL_METRES)
    assert tolerance_for(None) == (MAXIMUM_COREGISTRATION_RESIDUAL_PIXELS, None)


def test_the_registration_tile_shrinks_until_four_fit_each_way() -> None:
    assert tile_size_for((1120, 1066)) == 128
    assert tile_size_for((256, 256)) == 64
    assert tile_size_for((100, 100)) == 32


# ── The graphs' tables ───────────────────────────────────────────────────────────────────────────


def test_every_routed_intent_has_a_branch_and_every_branch_is_a_node() -> None:
    single = GRAPH_BUILDERS[GraphName.SINGLE_IMAGE]().compile().get_graph().nodes
    temporal = GRAPH_BUILDERS[GraphName.TEMPORAL]().compile().get_graph().nodes
    for intent, graph in INTENT_GRAPHS.items():
        if graph is GraphName.SINGLE_IMAGE:
            assert intent in FIRST_STAGE_BY_INTENT
        elif graph is GraphName.TEMPORAL:
            assert intent in AFTER_CHANGE_BY_INTENT
    assert set(FIRST_STAGE_BY_INTENT.values()) | set(GROUND_STAGE_BY_TOOL.values()) | set(LOCALISER_BY_STAGE.values()) <= set(single)
    assert set(AFTER_CHANGE_BY_INTENT.values()) <= set(temporal)
    assert set(LOCALISER_BY_STAGE) == {stage for stage in FIRST_STAGE_BY_INTENT.values() if stage != "answer_question"}


def test_cross_modal_graph_fans_out_only_after_validation_and_registration() -> None:
    graph = build_cross_modal_graph().compile().get_graph()
    edges = {(edge.source, edge.target) for edge in graph.edges}

    assert ("validate_inputs", "coregister_modalities") in edges
    assert ("coregister_modalities", "analyse_optical") in edges
    assert ("coregister_modalities", "analyse_radar") in edges
    assert ("analyse_optical", "fuse_modalities") in edges
    assert ("analyse_radar", "fuse_modalities") in edges


def test_the_edges_read_the_state_and_nothing_else() -> None:
    assert after_inputs({"intent": "INDEX_QUERY", "input_kind": "scene-directory", "modality": "optical"}) == "handle_clouds"
    assert after_inputs({"intent": "DETECT", "input_kind": "picture", "modality": "optical"}) == "detect_objects"
    assert after_inputs({"intent": "SCENE_VQA", "input_kind": "scene-directory", "modality": "sar"}) == "answer_question"
    assert first_stage({"intent": "GROUND", "tool": ModelId.DOTA_DETECTOR.value}) == "detect_objects"
    assert first_stage({"intent": "GROUND", "tool": ModelId.REMOTE_SENSING_VLM.value}) == "answer_question"
    assert first_stage({"intent": "SEGMENT"}) == "segment_land_cover"
    assert after_change({"intent": Intent.CHANGE_DETECT.value}) == "read_figure"
    assert after_change({"intent": Intent.CHANGE_VQA.value}) == "answer_question"
    with pytest.raises(KeyError):
        first_stage({"intent": "CROSS_MODAL"})
