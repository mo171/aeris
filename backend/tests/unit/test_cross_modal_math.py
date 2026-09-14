"""Hand-derived tests for Phase 1.11's physical measurements and late-fusion policy."""

from datetime import UTC, datetime

import numpy as np

from app.services.optical_sar.math.fusion_rules import (
    SensorFindingMasks,
    assess_pair,
    build_agreement_findings,
    fused_confidence,
    minimum_region_pixels_for_hectares,
    source_feature_ids_for_component,
)
from app.services.optical_sar.math.indices import optical_landcover_masks
from app.services.optical_sar.math.sar_masks import sar_landcover_masks
from app.services.optical_sar.metadata import sentinel_metadata


async def test_optical_masks_apply_observation_before_index_arithmetic() -> None:
    green = np.array([[0.40, 0.10], [0.20, 0.10]], dtype=np.float32)
    nir = np.array([[0.20, 0.20], [0.10, 0.10]], dtype=np.float32)
    swir = np.array([[0.10, 0.40], [0.20, 0.10]], dtype=np.float32)
    observed = np.array([[True, True], [False, True]])

    result = optical_landcover_masks(green, nir, swir, observed, minimum_samples=2)

    assert result.water.tolist() == [[True, False], [False, False]]
    assert result.built_up.tolist() == [[False, True], [False, False]]
    assert np.isnan(result.mndwi[1, 0]) and np.isnan(result.ndbi[1, 0])
    assert result.informative is True


async def test_sar_masks_use_dark_dual_pol_for_water_and_strong_return_for_built_up() -> None:
    vv_db = np.array([[-19.0, -6.0], [-12.0, -10.0]], dtype=np.float32)
    vh_db = np.array([[-25.0, -12.0], [-19.0, -18.0]], dtype=np.float32)
    vv = np.power(10.0, vv_db / 10.0)
    vh = np.power(10.0, vh_db / 10.0)

    result = sar_landcover_masks(vv, vh, np.ones((2, 2), dtype=bool), minimum_samples=4)

    assert result.water.tolist() == [[True, False], [False, False]]
    assert result.built_up.tolist() == [[False, True], [False, False]]
    assert result.informative is True


async def test_fusion_partitions_overlap_and_sensor_only_pixels_without_scripting_rows() -> None:
    optical = SensorFindingMasks(
        water=np.array([[True, True, False], [False, False, False]]),
        built_up=np.array([[False, False, False], [True, False, False]]),
        observed=np.ones((2, 3), dtype=bool),
        obscured=np.zeros((2, 3), dtype=bool),
        water_confidence=0.9,
        built_up_confidence=0.8,
    )
    radar = SensorFindingMasks(
        water=np.array([[True, False, False], [False, False, False]]),
        built_up=np.array([[False, False, False], [True, False, True]]),
        observed=np.ones((2, 3), dtype=bool),
        obscured=np.zeros((2, 3), dtype=bool),
        water_confidence=0.7,
        built_up_confidence=0.75,
    )

    rows = build_agreement_findings(optical, radar)

    assert [(row.label, row.state, row.pixel_count) for row in rows] == [
        ("Built-up region 1", "corroborated", 1),
        ("Built-up region 2", "radar-only", 1),
        ("Water region 1", "corroborated", 1),
        ("Water region 2", "optical-only", 1),
    ]
    assert all(row.reason for row in rows)


async def test_conflict_retains_the_opposing_class_for_each_sensor() -> None:
    optical = SensorFindingMasks(
        water=np.array([[True]]), built_up=np.array([[False]]), observed=np.array([[True]]),
        obscured=np.array([[False]]), water_confidence=0.9, built_up_confidence=None,
    )
    radar = SensorFindingMasks(
        water=np.array([[False]]), built_up=np.array([[True]]), observed=np.array([[True]]),
        obscured=np.array([[False]]), water_confidence=None, built_up_confidence=0.8,
    )

    conflict = build_agreement_findings(optical, radar)[0]

    assert conflict.state == "conflict"
    assert conflict.optical_class == "water"
    assert conflict.radar_class == "built_up"


async def test_obscured_silence_is_not_described_as_negative_evidence() -> None:
    optical = SensorFindingMasks(
        water=np.array([[True]]), built_up=np.array([[False]]), observed=np.array([[True]]),
        obscured=np.array([[False]]), water_confidence=0.9, built_up_confidence=None,
    )
    radar = SensorFindingMasks(
        water=np.array([[False]]), built_up=np.array([[False]]), observed=np.array([[False]]),
        obscured=np.array([[True]]), water_confidence=None, built_up_confidence=None,
    )

    row = build_agreement_findings(optical, radar)[0]

    assert row.state == "optical-only"
    assert "layover or shadow" in row.reason


async def test_minimum_region_floor_drops_speckle_without_materialising_full_scene_per_pixel() -> None:
    # One clear pixel is separated from every other one by a blank row and column, even under the
    # evidence builder's eight-connected convention.
    checkerboard = np.zeros((256, 256), dtype=bool)
    checkerboard[::2, ::2] = True
    empty = np.zeros_like(checkerboard)
    observed = np.ones_like(checkerboard)
    optical = SensorFindingMasks(checkerboard, empty, observed, empty, 0.8, None)
    radar = SensorFindingMasks(empty, empty, observed, empty, None, None)

    rows = build_agreement_findings(optical, radar, minimum_region_pixels=25)

    assert rows == []


async def test_component_references_only_the_source_features_it_touches() -> None:
    """Protects the ledger from copying an entire branch's feature list into every row."""
    source = np.zeros((8, 8), dtype=bool)
    source[1:3, 1:3] = True
    source[5:8, 5:8] = True
    component = np.ones((3, 3), dtype=bool)

    feature_ids = source_feature_ids_for_component(
        source, component, row_start=5, column_start=5,
        feature_ids_by_region_label={1: "ftr_left", 2: "ftr_right"},
    )

    assert feature_ids == ["ftr_right"]


async def test_ledger_uses_the_eight_connected_regions_that_evidence_vectors_use() -> None:
    diagonal = np.array([[True, False], [False, True]])
    empty = np.zeros_like(diagonal)
    observed = np.ones_like(diagonal)
    optical = SensorFindingMasks(diagonal, empty, observed, empty, 0.8, None)
    radar = SensorFindingMasks(empty, empty, observed, empty, None, None)

    rows = build_agreement_findings(optical, radar)

    assert [(row.state, row.pixel_count) for row in rows] == [("optical-only", 2)]


async def test_material_ledger_floor_is_a_ground_area_not_a_resolution_dependent_pixel_count() -> None:
    assert minimum_region_pixels_for_hectares(5.0, resolution_metres=10.0) == 500
    assert minimum_region_pixels_for_hectares(5.0, resolution_metres=0.5) == 200_000


async def test_pair_at_one_pixel_is_unusable_and_minimum_confidence_is_conservative() -> None:
    assessment = assess_pair(
        datetime(2026, 3, 8, tzinfo=UTC), datetime(2026, 3, 10, tzinfo=UTC), 1.0
    )

    assert assessment.verdict == "unusable"
    assert assessment.refusal == "poor-co-registration"
    assert fused_confidence(0.91, 0.63) == 0.63
    assert fused_confidence(None, 0.63) == 0.63


async def test_standard_sentinel_ids_supply_auditable_platform_and_capture_time() -> None:
    optical = sentinel_metadata("S2B_MSIL2A_20260308T052649_N0511_R105_T43QBB_20260308T081430")
    radar = sentinel_metadata("S1A_IW_GRDH_1SDV_20260309T010203_000001_000001_0001")

    assert optical.platform == "Sentinel-2B"
    assert optical.captured_at == datetime(2026, 3, 8, 5, 26, 49, tzinfo=UTC)
    assert radar.platform == "Sentinel-1A"
    assert radar.captured_at == datetime(2026, 3, 9, 1, 2, 3, tzinfo=UTC)
