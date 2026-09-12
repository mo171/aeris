"""Tests the area kernel against values from a method it shares no code with.

what  : Hand-checkable and geodesically-checked areas, region counting, and the two wrong answers the
        kernel exists to refuse - UTM units taken as ground truth, and degrees taken as metres.
where : Unit suite for `services/evidence/math/area.py`; needs no raster files and no infrastructure.
how   : `code-standards.md` §11: deterministic numerics are tested against an independent computation.
        The independent method here is pyproj's `Geod.polygon_area_perimeter`, which integrates on the
        WGS 84 ellipsoid and never touches a projection, so agreement between the two is agreement of two
        different pieces of mathematics rather than of a function with itself.
"""

import numpy as np
import pytest
from pyproj import CRS, Geod, Transformer

from app.services.evidence.math.area import count_regions, local_equal_area_crs, measure_area

# Where the Phase 1.2 scene sits: UTM zone 43N, about 230 km west of the zone's central meridian, which
# is far enough for the scale factor to matter at the fourth significant figure.
SCENE_TRANSFORM = (10.0, 0.0, 268410.0, 0.0, -10.0, 2113350.0)
SCENE_CRS = "EPSG:32643"

# Ten-metre pixels exactly on the central meridian at the equator, where UTM's scale factor is its
# defined 0.9996 in both directions and a pixel's true area is therefore computable by hand.
CENTRAL_MERIDIAN_TRANSFORM = (10.0, 0.0, 500_000.0, 0.0, -10.0, 0.0)
UTM_CENTRAL_SCALE = 0.9996


def geodesic_area(transform, crs: str, rows: int, columns: int) -> float:
    """Area of the grid's outer rectangle, integrated on the ellipsoid by pyproj. The independent method."""
    a, b, c, d, e, f = transform
    column = np.array([0, columns, columns, 0], dtype=float)
    row = np.array([0, 0, rows, rows], dtype=float)
    longitude, latitude = Transformer.from_crs(
        CRS.from_user_input(crs), CRS.from_epsg(4326), always_xy=True
    ).transform(c + a * column + b * row, f + d * column + e * row)
    area, _ = Geod(ellps="WGS84").polygon_area_perimeter(longitude, latitude)
    return abs(area)


def test_one_pixel_on_the_central_meridian_measures_what_the_scale_factor_says() -> None:
    """Hand value: a 10 m UTM pixel on the central meridian covers 100 / 0.9996**2 = 100.0800 m^2."""
    measurement = measure_area(np.ones((1, 1), dtype=bool), transform=CENTRAL_MERIDIAN_TRANSFORM, crs=SCENE_CRS)

    assert measurement.pixel_count == 1
    assert measurement.square_metres == pytest.approx(100.0 / UTM_CENTRAL_SCALE**2, rel=1e-7)


def test_a_utm_grid_is_not_measured_in_its_own_units() -> None:
    """The plausible wrong answer: 100 x 100 ten-metre pixels is "obviously" 1,000,000 m^2. It is not."""
    mask = np.ones((100, 100), dtype=bool)

    measurement = measure_area(mask, transform=SCENE_TRANSFORM, crs=SCENE_CRS)

    independent = geodesic_area(SCENE_TRANSFORM, SCENE_CRS, 100, 100)
    assert measurement.square_metres == pytest.approx(independent, rel=1e-7)
    # Half a hectare in a hundred, and the naive figure is the one a reviewer would nod through.
    assert abs(measurement.square_metres - 1_000_000.0) > 400.0
    assert measurement.hectares == pytest.approx(independent / 10_000.0)


def test_degrees_are_never_treated_as_metres() -> None:
    """A geographic grid measured in its own units gives square degrees; here it gives square metres."""
    transform = (0.001, 0.0, 72.9, 0.0, -0.001, 19.0)

    measurement = measure_area(np.ones((50, 50), dtype=bool), transform=transform, crs="EPSG:4326")

    independent = geodesic_area(transform, "EPSG:4326", 50, 50)
    assert measurement.square_metres == pytest.approx(independent, rel=1e-6)
    # 0.05 deg x 0.05 deg near 19 N is about 29 km^2, not 0.0025 of anything.
    assert 2.8e7 < measurement.square_metres < 3.0e7


def test_a_partial_mask_that_straddles_block_edges_measures_only_its_own_pixels() -> None:
    """Regression guard for the block sum: a rectangle offset from the block grid, on a grid whose size is
    not a multiple of the block, must equal the geodesic area of exactly that rectangle."""
    mask = np.zeros((70, 45), dtype=bool)
    mask[5:22, 10:33] = True

    measurement = measure_area(mask, transform=SCENE_TRANSFORM, crs=SCENE_CRS)

    a, b, c, d, e, f = SCENE_TRANSFORM
    rectangle_transform = (a, b, c + 10 * a, d, e, f + 5 * e)
    independent = geodesic_area(rectangle_transform, SCENE_CRS, 17, 23)
    assert measurement.pixel_count == 17 * 23
    assert measurement.square_metres == pytest.approx(independent, rel=1e-6)


def test_an_empty_mask_covers_nothing() -> None:
    measurement = measure_area(np.zeros((16, 16), dtype=bool), transform=SCENE_TRANSFORM, crs=SCENE_CRS)

    assert measurement.pixel_count == 0
    assert measurement.square_metres == 0.0
    assert measurement.hectares == 0.0


def test_the_projection_is_centred_on_the_grid_it_measures() -> None:
    crs = local_equal_area_crs(SCENE_TRANSFORM, SCENE_CRS, (1120, 1066))

    assert crs.startswith("+proj=laea")
    # Mumbai. A projection centred anywhere else is still equal-area, but a wrong centre here would mean
    # the centroid arithmetic is wrong - which nothing downstream would notice.
    assert "+lat_0=19.0" in crs
    assert "+lon_0=72.8" in crs


def test_a_non_boolean_mask_is_refused_rather_than_summed() -> None:
    # An index array passed where a mask was expected would sum its values as if they were counts.
    with pytest.raises(ValueError, match="boolean"):
        measure_area(np.ones((4, 4), dtype=np.float32), transform=SCENE_TRANSFORM, crs=SCENE_CRS)


def test_regions_are_counted_eight_connected() -> None:
    mask = np.zeros((6, 6), dtype=bool)
    mask[0, 0] = mask[1, 1] = True  # diagonal neighbours: one region
    mask[4, 4] = mask[4, 5] = True  # side neighbours: one region
    mask[0, 5] = True  # alone

    regions = count_regions(mask)

    assert regions.region_count == 3
    assert sorted(regions.region_pixel_counts) == [1, 2, 2]
    assert regions.largest_region_pixels == 2


def test_no_regions_in_an_empty_mask() -> None:
    regions = count_regions(np.zeros((3, 3), dtype=bool))

    assert regions.region_count == 0
    assert regions.region_pixel_counts == ()
    assert regions.largest_region_pixels == 0
