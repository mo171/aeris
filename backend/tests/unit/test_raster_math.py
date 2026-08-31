"""Pins the raster arithmetic against answers known by construction, including the bug that produced an NDVI of 347.

what  : Tests over `services/imagery/math/` - `indices`, `windowing` and `quality_statistics`.
where : `tests/unit/`. No Docker, no network, no GeoTIFF - these are NumPy arrays whose correct answers
        are worked out by hand.
how   : `architecture-context.md` §12 keeps this arithmetic pure and sync precisely so it can be tested
        this way. Every number below is one a person can verify without running the code.

        **The file exists mostly because of `test_an_index_never_escapes_its_own_algebra`.** The first
        NDVI this pipeline produced over a real scene ranged [-337, +347]. It wrote a valid COG and
        rendered as a plausible map; 0.055% of pixels were affected, which is invisible by eye and more
        than enough to set the colour scale of every figure drawn from the array - a ramp is stretched to
        the extremes it is given.

        The first fix was wrong. Raising the denominator guard did not work, because the cause was not a
        small denominator: it was **opposite-sign reflectance**, which breaks the `|a-b| <= |a+b|`
        inequality the bound depends on. The tests below encode both the symptom and the actual cause, so
        neither can come back.
"""

import numpy as np
import pytest

from app.constants.raster import (
    INFERENCE_TILE_OVERLAP,
    INFERENCE_TILE_SIZE,
    REFLECTANCE_OFFSET,
    REFLECTANCE_SCALE,
)
from app.services.imagery.math.indices import (
    _require_in_range,
    normalised_difference,
    to_surface_reflectance,
)
from app.services.imagery.math.quality_statistics import (
    decimation_step_for,
    distinct_value_fraction,
    measure_band,
    nodata_fraction,
    valid_mask,
)
from app.services.imagery.math.windowing import blend_weights, plan_tile_grid, tile_count_for

# --- Indices ---------------------------------------------------------------------------------------------


async def test_a_normalised_difference_is_computed_the_obvious_way() -> None:
    """The baseline: `(high - low) / (high + low)` on values whose answer is arithmetic."""
    high = np.array([[0.3, 0.5, 0.1]], dtype=np.float32)
    low = np.array([[0.1, 0.5, 0.3]], dtype=np.float32)

    index = normalised_difference(high, low)

    assert index[0, 0] == pytest.approx(0.2 / 0.4)
    assert index[0, 1] == pytest.approx(0.0)
    assert index[0, 2] == pytest.approx(-0.2 / 0.4)


async def test_an_index_never_escapes_its_own_algebra() -> None:
    """**The bug this file exists for.** A normalised difference outside [-1, 1] must raise, not return.

    A real scene produced [-337, +347] and wrote a valid COG from it. The value is not unusual data - it
    is arithmetically impossible for same-signed inputs - so returning it would be the "confident wrong
    number" `architecture-context.md` §8 opens by forbidding.
    """
    # Opposite signs, which is what actually breaks the bound: |0.2 - (-0.1)| = 0.3 > |0.2 + (-0.1)| = 0.1,
    # giving 3.0. The guard masks it rather than returning it.
    high = np.array([[0.2]], dtype=np.float32)
    low = np.array([[-0.1]], dtype=np.float32)

    index = normalised_difference(high, low)

    assert np.isnan(index[0, 0]), "an opposite-sign pair has no meaningful normalised difference"


async def test_the_range_guard_raises_when_it_is_reached() -> None:
    """The post-condition itself, called directly.

    Added after a mutation pass showed that deleting `_require_in_range` broke **nothing**: the masks
    above prevent an out-of-range value from ever reaching it, so end to end the guard is unreachable and
    therefore untested. That is exactly what makes it worth testing separately - it is the backstop that
    caught the original [-337, +347] bug, and a backstop nothing exercises is one that quietly stops
    working before the day it is needed.
    """
    with pytest.raises(ValueError, match="bounded by"):
        _require_in_range(np.array([[0.5, 347.0]], dtype=np.float32))

    # NaN is the masked state and must never trip it.
    _require_in_range(np.array([[np.nan, 0.5, -1.0, 1.0]], dtype=np.float32))


async def test_nodata_is_masked_from_the_raw_integers_not_the_scaled_values() -> None:
    """Masking after scaling would look for the nodata value among reflectances, and find nothing.

    Sentinel-2 declares nodata as 0. Scale first and that pixel becomes -0.1; a mask comparing the scaled
    array against 0 then matches only *genuine* zero-reflectance pixels and leaves every nodata pixel in
    the data as a plausible -0.1.
    """
    raw = np.array([[0, 1000, 5000]], dtype=np.uint16)

    reflectance = to_surface_reflectance(raw, nodata=0)

    assert np.isnan(reflectance[0, 0]), "the nodata pixel is masked"
    # DN 1000 scales to exactly 0.0 reflectance. If the mask ran on the scaled array it would strike this
    # pixel instead - a real observation removed, and the actual nodata kept.
    assert reflectance[0, 1] == pytest.approx(0.0), "a genuine zero-reflectance pixel survives"
    assert np.isfinite(reflectance[0, 2])


async def test_negative_reflectance_is_masked_because_it_is_not_a_measurement() -> None:
    """The actual cause, isolated. Raising the denominator guard did **not** fix this.

    Subtracting the L2A offset from a dark pixel - deep water, terrain shadow - gives a small negative
    reflectance, which is an atmospheric-correction artefact. Measured on a real scene: 0.52% of valid
    pixels, and **100% of the out-of-range values came from exactly those pixels**.
    """
    high = np.array([[0.4, 0.4, -0.05]], dtype=np.float32)
    low = np.array([[0.2, -0.05, -0.02]], dtype=np.float32)

    index = normalised_difference(high, low)

    assert index[0, 0] == pytest.approx(0.2 / 0.6), "both positive - computed normally"
    assert np.isnan(index[0, 1]), "one band negative - masked"
    assert np.isnan(index[0, 2]), "both negative - masked"


async def test_a_vanishing_denominator_is_masked_rather_than_dividing() -> None:
    """`(a - b) / (a + b)` is unbounded as the denominator approaches zero.

    Guarding `denominator == 0` catches nothing, because the problem is *near*-zero: two bands at 1e-9
    reflectance sum to 2e-9, and their ratio is noise amplified by a factor of a billion.
    """
    tiny = np.array([[1e-9, 0.3]], dtype=np.float32)
    other = np.array([[2e-9, 0.1]], dtype=np.float32)

    index = normalised_difference(tiny, other)

    assert np.isnan(index[0, 0]), "below the denominator floor - masked"
    assert np.isfinite(index[0, 1]), "an ordinary pair is unaffected"


async def test_masking_never_clips() -> None:
    """A masked pixel is NaN, never a plausible number.

    §8 rule 4. Clipping to -1 would be indistinguishable from a real -1 in every statistic computed
    afterwards - the mean, the histogram, the stretch bounds of every figure.
    """
    high = np.array([[0.2, 0.4]], dtype=np.float32)
    low = np.array([[-0.1, 0.2]], dtype=np.float32)

    index = normalised_difference(high, low)

    assert np.isnan(index[0, 0])
    assert index[0, 0] != -1.0 and index[0, 0] != 1.0


async def test_reflectance_scaling_applies_the_offset_and_keeps_nodata_out() -> None:
    """`(digital_number - 1000) / 10000`, with nodata as NaN.

    The offset is measured, not stylistic: omitting it moved the vegetated fraction of a real scene from
    75.1% to 61.4% (`notebooks/02_data_exploration/01_sentinel2_l2a.ipynb`).
    """
    raw = np.array([[0, 1000, 3000]], dtype=np.uint16)

    reflectance = to_surface_reflectance(raw, nodata=0)

    assert np.isnan(reflectance[0, 0]), "the declared nodata value must not become a number"
    assert reflectance[0, 1] == pytest.approx(0.0)
    assert reflectance[0, 2] == pytest.approx((3000 - REFLECTANCE_OFFSET) / REFLECTANCE_SCALE)


async def test_nodata_is_masked_before_scaling_not_after() -> None:
    """The ordering that makes nodata detectable at all.

    Sentinel-2 declares nodata as 0. Subtract the offset and it becomes -0.1, which is an ordinary float
    no downstream check can tell from a dark pixel. The mask has to be taken from the raw integers.
    """
    raw = np.array([[0]], dtype=np.uint16)

    assert np.isnan(to_surface_reflectance(raw, nodata=0)[0, 0])
    # Without a declared nodata, 0 is a legitimate reading and is scaled like any other value.
    assert to_surface_reflectance(raw, nodata=None)[0, 0] == pytest.approx(-0.1)


async def test_bands_on_different_grids_are_refused() -> None:
    """Two bands of different shapes would combine two different places in every pixel."""
    with pytest.raises(ValueError, match="share a grid"):
        normalised_difference(np.zeros((4, 4), np.float32), np.zeros((4, 5), np.float32))


# --- Windowing -------------------------------------------------------------------------------------------


async def test_a_tile_grid_covers_every_pixel() -> None:
    """A grid that misses pixels produces a change mask with a hole in it and no error anywhere."""
    width, height, size, overlap = 1000, 700, 256, 32
    windows = plan_tile_grid(width=width, height=height, tile_size=size, overlap=overlap)

    covered = np.zeros((height, width), dtype=bool)
    for window in windows:
        rows, columns = window.as_slices()
        covered[rows, columns] = True

    assert covered.all(), f"{(~covered).sum()} pixels are in no window"


async def test_no_window_extends_past_the_raster() -> None:
    """The last window is **shifted back**, never padded.

    Padding the remainder feeds a model a strip of fabricated black pixels and gets a prediction about
    them. Shifting means every pixel is real; the cost is that the last two windows overlap more, which
    the blend already handles.
    """
    windows = plan_tile_grid(width=1000, height=1000, tile_size=256, overlap=32)

    assert all(window.column_end <= 1000 and window.row_end <= 1000 for window in windows)
    assert max(window.column_end for window in windows) == 1000, "the grid must reach the edge"


async def test_a_raster_smaller_than_one_tile_is_a_single_window() -> None:
    """The degenerate case, which is what a test fixture or a small crop actually is."""
    windows = plan_tile_grid(width=100, height=80, tile_size=512, overlap=64)

    assert len(windows) == 1
    assert (windows[0].width, windows[0].height) == (100, 80)


async def test_an_overlap_that_would_stall_the_grid_is_refused() -> None:
    """Overlap >= tile size means a step of zero. Caught at the argument, because the symptom otherwise
    is an infinite loop rather than a wrong answer."""
    with pytest.raises(ValueError, match="never advances"):
        plan_tile_grid(width=1000, height=1000, tile_size=256, overlap=256)


async def test_counting_tiles_agrees_with_building_them() -> None:
    """`tile_count_for` exists so a caller can price an inference run without materialising thousands of
    window objects. Two implementations of one number is how they come to disagree."""
    for width, height in ((1000, 700), (10980, 10980), (256, 256), (100, 3000)):
        assert tile_count_for(
            width=width, height=height, tile_size=INFERENCE_TILE_SIZE, overlap=INFERENCE_TILE_OVERLAP
        ) == len(
            plan_tile_grid(
                width=width, height=height,
                tile_size=INFERENCE_TILE_SIZE, overlap=INFERENCE_TILE_OVERLAP,
            )
        )


async def test_blend_weights_fall_off_at_the_edge_and_never_reach_zero() -> None:
    """What makes stitching seamless.

    The tiles overlap because predictions near an edge are made with cropped context and are worse.
    Averaging the two answers equally keeps half that error; a ramp weights each pixel towards the tile
    that saw it with the most context.

    Never exactly zero: a pixel with zero weight in every covering tile divides by zero during
    normalisation, and the caller gets NaN in a mask rather than a class.
    """
    weights = blend_weights(tile_size=64, overlap=8)

    assert weights.shape == (64, 64)
    assert weights.dtype == np.float32
    assert weights[32, 32] == pytest.approx(1.0), "the interior is unweighted"
    assert 0.0 < weights[0, 0] < weights[8, 8], "the corner is lowest, and strictly positive"
    assert weights[0, 32] < 1.0, "an edge is weighted down"


async def test_blend_weights_are_uniform_without_overlap() -> None:
    """No overlap means no ambiguity to resolve, so every pixel weighs the same."""
    assert (blend_weights(tile_size=16, overlap=0) == 1.0).all()


# --- Quality statistics ----------------------------------------------------------------------------------


async def test_nodata_is_not_zero() -> None:
    """**§8 rule 4, as a test.** Zero is a legitimate reflectance - deep water in the near infrared.

    Computing the nodata mask as `array == 0` marks every lake as missing and refuses a good scene.
    """
    array = np.array([[0.0, 0.0, 0.5, 0.5]], dtype=np.float32)

    assert nodata_fraction(array, nodata=None) == 0.0, "no declared nodata means nothing is missing"
    assert nodata_fraction(array, nodata=0.0) == pytest.approx(0.5), "declared - then zero is missing"


async def test_a_declared_nodata_other_than_zero_is_honoured() -> None:
    """The mask comes from what the raster *declares*, not from a value that looks empty.

    Added after a mutation pass: replacing the mask with `array != 0` was caught by nothing, because every
    test happened to use `nodata=0`. A raster declaring -9999 with legitimate zeros in it is the case that
    separates the two, and it is an ordinary one - plenty of DEMs and index products are written that way.
    """
    array = np.array([[-9999.0, 0.0, 0.0, 5.0]], dtype=np.float32)

    assert nodata_fraction(array, nodata=-9999.0) == pytest.approx(0.25), "only the declared value is missing"

    statistics = measure_band(array, nodata=-9999.0)
    assert statistics.valid_pixel_count == 3, "the two zeros are real observations"
    assert statistics.mean == pytest.approx(5.0 / 3.0)


async def test_statistics_are_computed_over_valid_pixels_only() -> None:
    """A mean that includes nodata is a mean of the data and the absence of data, which is not a quantity."""
    array = np.array([[0.0, 0.0, 2.0, 4.0]], dtype=np.float32)

    statistics = measure_band(array, nodata=0.0)

    assert statistics.valid_pixel_count == 2
    assert statistics.total_pixel_count == 4
    assert statistics.mean == pytest.approx(3.0), "mean of 2 and 4, not of 0, 0, 2 and 4"
    assert statistics.nodata_fraction == pytest.approx(0.5)


async def test_an_entirely_empty_band_reports_nothing_rather_than_nan() -> None:
    """`valid_pixel_count == 0` is distinguishable; a struct full of NaN is not.

    Every reduction over an empty array is NaN and warns, and a caller cannot tell "measured NaN" from
    "measured nothing".
    """
    statistics = measure_band(np.zeros((4, 4), np.float32), nodata=0.0)

    assert statistics.is_empty
    assert statistics.nodata_fraction == 1.0
    assert not np.isnan(statistics.mean)


async def test_a_constant_raster_is_detected_at_any_size() -> None:
    """A failed download opens cleanly and renders as a plausible flat image.

    **Counted, not ratioed**, and that correction came from a failing test. `distinct / valid` is `1 / N`
    for a constant raster, so a fixed fraction threshold means something different at every resolution:
    at 1e-6 it fired on a 10980x10980 scene and silently passed a 20x20 one. Constancy does not depend on
    size, so neither does the check.
    """
    for size in (4, 20, 100):
        statistics = measure_band(np.full((size, size), 7.0), nodata=None)
        assert statistics.distinct_value_count == 1, f"{size}x{size} constant raster"

    varied = measure_band(np.arange(100.0).reshape(10, 10), nodata=None)
    assert varied.distinct_value_count == 100
    assert distinct_value_fraction(np.arange(100.0).reshape(10, 10), nodata=None) == pytest.approx(1.0)


async def test_percentiles_are_robust_where_min_and_max_are_not() -> None:
    """A single hot pixel sets the maximum and collapses the visible range of everything else.

    Which is why the display stretch uses p2-p98 and not min-max - `architecture-context.md` §8 rule 13:
    widen a stretch and a drought disappears.
    """
    array = np.concatenate([np.full(999, 0.3), np.array([1000.0])]).astype(np.float32)

    statistics = measure_band(array, nodata=None)

    assert statistics.maximum == 1000.0
    assert statistics.percentile_98 == pytest.approx(0.3), "the outlier does not move p98"


async def test_decimation_is_regular_so_the_same_scene_measures_the_same_twice() -> None:
    """A quality report that varies between runs cannot answer whether the scene changed or the
    measurement did."""
    step = decimation_step_for(width=10980, height=10980, maximum_pixels=4_000_000)

    assert step > 1
    assert (10980 // step) * (10980 // step) <= 4_000_000
    assert decimation_step_for(width=100, height=100, maximum_pixels=4_000_000) == 1


async def test_the_valid_mask_excludes_nan_whatever_the_nodata_value() -> None:
    """NaN is what a float raster uses for nodata, and it is never equal to anything - including itself."""
    array = np.array([[1.0, np.nan, 3.0]], dtype=np.float32)

    assert valid_mask(array, nodata=None).tolist() == [[True, False, True]]
    assert valid_mask(array, nodata=float("nan")).tolist() == [[True, False, True]]


# --- Recorded run ----------------------------------------------------------------------------------------
#
# $ uv run pytest tests/unit/test_raster_math.py -q                                   2026-08-31
#
#   ..........................                                               [100%]
#   26 passed in 0.38s
#
# No Docker, no network, no GeoTIFF. Every number above is one a person can check by hand.
#
# Checked by mutation, against both this file and tests/integration/test_raster_pipeline.py:
#
#   B  negative reflectance no longer masked      -> 3 tests FAILED
#   C  denominator guard becomes `== 0`           -> test_a_vanishing_denominator_is_masked_rather_than
#                                                    _dividing FAILED
#   D  nodata masked AFTER scaling                -> 3 tests FAILED, including
#                                                    test_nodata_is_masked_from_the_raw_integers_not_the
#                                                    _scaled_values
#   E  the reflectance offset dropped             -> 2 tests FAILED
#   F  the last window padded, not shifted        -> 4 tests FAILED
#   G  blend weights become uniform               -> test_blend_weights_fall_off_at_the_edge_and_never
#                                                    _reach_zero FAILED
#   H  nodata detected as `array != 0`            -> test_a_declared_nodata_other_than_zero_is_honoured
#                                                    FAILED
#
#   A  the `_require_in_range` CALL removed       -> *** NOT CAUGHT, and correctly so ***
#
# **A is recorded as uncaught rather than papered over.** Once the masks are right, no input can produce an
# out-of-range value, so the post-condition is unreachable and deleting its call changes no behaviour. It
# is defence in depth against a *future* regression in the masking - which mutation B shows is caught
# independently. `test_the_range_guard_raises_when_it_is_reached` calls the guard directly, so the guard
# itself is proven to work; writing a test that forced the call site to fire would mean breaking the masks
# to do it, which is the thing the masks exist to prevent.
#
# Four of these (A, D, H, and L in the pipeline file) survived the FIRST mutation pass. D survived because
# the mutation was wrong - it still masked before scaling - and H and L survived because of real gaps:
# every nodata test happened to use `nodata=0`, so `array != nodata` and `array != 0` were indistinguishable.
# Three tests were added and the mutations re-run.
#
# All mutated files were restored and byte-compared against their originals.
