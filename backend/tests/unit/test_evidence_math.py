"""Tests the geometry and aggregation kernels behind Phase 1.5 against shapes whose answers are known by construction.

what  : Vectorisation (labels, polygons with holes, per-region means), simplification and the wire ring,
        polygon area against the raster measurement, the confidence rule, and the web-mercator zooms.
where : Unit suite for `segmentation/math/vectorize.py`, `evidence/math/{simplification,
        confidence_aggregation,area}.py` and `imagery/math/web_mercator.py`. Plain arrays, no files.
how   : `code-standards.md` §11. Each kernel has a wrong answer that looks right - a hole filled in, a
        staircase kept, an area from the ring instead of the region, a `None` confidence read as zero -
        and each test below names the one it holds off.
"""

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Polygon

from app.constants.evidence import CONFIDENCE_AGGREGATION_RULE
from app.services.evidence.math.area import local_equal_area_crs, measure_area, polygon_area
from app.services.evidence.math.confidence_aggregation import aggregate_confidence
from app.services.evidence.math.simplification import outer_ring_geographic, simplify_outline
from app.services.imagery.math.web_mercator import geographic_bounds, zoom_range
from app.services.segmentation.math.vectorize import label_regions, region_means, vectorise_regions

SCENE_TRANSFORM = (10.0, 0.0, 268410.0, 0.0, -10.0, 2113350.0)
SCENE_CRS = "EPSG:32643"


def ring_mask() -> np.ndarray:
    """A 6x6 square with a 2x2 hole: one region, one interior ring, 32 pixels."""
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:8, 2:8] = True
    mask[4:6, 4:6] = False
    return mask


# ── Vectorisation ────────────────────────────────────────────────────────────────────────────────


def test_labels_are_eight_connected_and_one_per_region() -> None:
    mask = np.zeros((5, 5), dtype=bool)
    mask[0, 0] = mask[1, 1] = True  # diagonal: one region
    mask[4, 4] = True

    labels, count = label_regions(mask)

    assert count == 2
    assert labels[0, 0] == labels[1, 1] != 0
    assert labels[4, 4] not in (0, labels[0, 0])


def test_a_region_with_a_hole_vectorises_with_the_hole_kept() -> None:
    """The plausible wrong answer is a filled square: 36 pixels of area for 32 pixels of ground."""
    labels, count = label_regions(ring_mask())

    regions = vectorise_regions(labels, SCENE_TRANSFORM)

    assert count == 1 and len(regions) == 1
    region = regions[0]
    assert region.pixel_count == 32
    assert isinstance(region.geometry, Polygon)
    assert len(region.geometry.interiors) == 1
    # Areas in the raster's own units: 32 pixels of 100 m^2, not 36.
    assert region.geometry.area == pytest.approx(3200.0)
    assert Polygon(region.geometry.exterior).area == pytest.approx(3600.0)


def test_no_regions_vectorise_to_no_polygons() -> None:
    labels, count = label_regions(np.zeros((4, 4), dtype=bool))

    assert count == 0
    assert vectorise_regions(labels, SCENE_TRANSFORM) == []


def test_region_means_ignore_nan_and_keep_region_order() -> None:
    mask = np.array([[True, True, False, False], [False, False, False, True]])
    values = np.array([[0.2, np.nan, 9.0, 9.0], [9.0, 9.0, 9.0, 0.6]], dtype=np.float32)
    labels, count = label_regions(mask)

    means = region_means(labels, values, count)

    # Region 1 is the top-left pair, of which one pixel is unobserved; region 2 is the single 0.6. Two
    # columns apart, because a diagonal touch would make them one region (eight-connectivity).
    assert count == 2
    assert means.tolist() == pytest.approx([0.2, 0.6])


# ── Simplification and the wire ring ──────────────────────────────────────────────────────────────


def test_a_staircase_edge_simplifies_to_its_line() -> None:
    """A diagonal region's rasterised outline has a corner per pixel; the ground has a straight edge."""
    mask = np.zeros((12, 12), dtype=bool)
    for index in range(10):
        mask[index, index:] = True  # a right triangle: its hypotenuse is a staircase
    labels, _ = label_regions(mask)
    region = vectorise_regions(labels, SCENE_TRANSFORM)[0]

    simplified = simplify_outline(region.geometry, 5.0)

    assert len(simplified.exterior.coords) < len(region.geometry.exterior.coords)
    assert simplified.is_valid
    # Simplification moves the outline within tolerance and never changes what the region measures.
    assert simplified.area == pytest.approx(region.geometry.area, rel=0.03)


def test_the_wire_ring_is_the_outer_ring_in_degrees_rounded_and_unclosed() -> None:
    labels, _ = label_regions(ring_mask())
    region = vectorise_regions(labels, SCENE_TRANSFORM)[0]

    ring = outer_ring_geographic(region.geometry, crs=SCENE_CRS)

    assert len(ring) == len(region.geometry.exterior.coords) - 1
    assert ring[0] != ring[-1], "the closing point is the frontend's to add"
    for longitude, latitude in ring:
        assert 72.7 < longitude < 72.9 and 19.0 < latitude < 19.2
        assert round(longitude, 7) == longitude and round(latitude, 7) == latitude


def test_a_multipolygon_contributes_its_largest_piece() -> None:
    small = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    large = Polygon([(100, 100), (130, 100), (130, 130), (100, 130)])

    ring = outer_ring_geographic(MultiPolygon([small, large]), crs=SCENE_CRS)

    assert len(ring) == 4
    # The large square starts at (100, 100); the small one at the origin. Distinguishable in degrees.
    origin = outer_ring_geographic(small, crs=SCENE_CRS)
    assert ring != origin


# ── Polygon area agrees with the raster measurement ─────────────────────────────────────────────


def test_a_polygon_measures_what_its_pixels_measure() -> None:
    """The same region, two routes: the raster block sum (1.4) and the projected polygon. One number."""
    mask = ring_mask()
    labels, _ = label_regions(mask)
    region = vectorise_regions(labels, SCENE_TRANSFORM)[0]
    equal_area = local_equal_area_crs(SCENE_TRANSFORM, SCENE_CRS, mask.shape)

    from_pixels = measure_area(mask, transform=SCENE_TRANSFORM, crs=SCENE_CRS)
    from_polygon = polygon_area(region.geometry, crs=SCENE_CRS, equal_area_crs=equal_area)

    assert from_polygon == pytest.approx(from_pixels.square_metres, rel=1e-8)
    # And neither is the naive 3200 m^2: UTM's scale at this longitude is not 1.
    assert abs(from_polygon - 3200.0) > 1.0


# ── Confidence ───────────────────────────────────────────────────────────────────────────────────


def test_the_run_is_as_confident_as_its_weakest_stated_stage() -> None:
    assert aggregate_confidence([0.9, None, 0.6, None]) == 0.6


def test_a_declined_confidence_is_absent_not_zero() -> None:
    """`None` read as 0.0 would make every run that ran a deterministic engine worthless."""
    assert aggregate_confidence([None, None]) is None
    assert aggregate_confidence([]) is None
    assert aggregate_confidence([None, 0.8]) == 0.8


def test_a_confidence_outside_the_unit_interval_is_refused() -> None:
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        aggregate_confidence([1.2])


def test_the_rule_is_named_for_the_record() -> None:
    assert CONFIDENCE_AGGREGATION_RULE == "minimum-of-stated"


# ── Web mercator ─────────────────────────────────────────────────────────────────────────────────


def test_the_zooms_match_what_titiler_reported_for_the_phase_1_2_scene() -> None:
    """The 1.2 gate's TileJSON over the 10 m Ghaziabad tile: bounds as recorded, minzoom 8, maxzoom 14."""
    assert zoom_range((77.032, 27.901, 78.176, 28.913), 10.0) == (8, 14)


def test_a_small_subset_needs_a_higher_minimum_zoom_than_a_whole_tile() -> None:
    bounds = geographic_bounds(SCENE_TRANSFORM, SCENE_CRS, (1120, 1066))

    minimum, maximum = zoom_range(bounds, 10.0)

    assert 72.79 < bounds[0] < 72.81 and 18.99 < bounds[1] < 19.01
    assert maximum == 14
    assert minimum > 8, "a 10 km subset fits one tile at a finer zoom than a 110 km tile does"
