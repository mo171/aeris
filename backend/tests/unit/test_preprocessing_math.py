"""Tests the numerical kernels behind Phase 1.3 preprocessing.

what  : Hand-checkable masking, registration, speckle, terrain and grid tests.
where : Unit suite for ``services/preprocessing/math``; no model, storage or raster files are required.
how   : Every kernel here has a failure mode that produces a *plausible* raster rather than an error, so
        each test names the specific wrong answer it is holding off rather than asserting that output
        exists. Three of them are regressions for bugs this suite did not originally catch - the terrain
        sign inversion, the flat-ground gain, and the additive-noise speckle model - and each is written
        against a quantity that can be computed by hand.
"""

import numpy as np
import pytest

from app.services.preprocessing.math.cloud_probability import project_cloud_shadow, threshold_cloud_probability
from app.services.preprocessing.math.grid_alignment import GridDefinition, grids_match
from app.services.preprocessing.math.registration_residual import (
    _fill_with_mean,
    measure_registration_residual,
)
from app.services.preprocessing.math.speckle_filters import lee_filter
from app.services.preprocessing.math.terrain_flattening import terrain_flatten


def _ramp(rise_per_pixel: float, shape: tuple[int, int] = (16, 16)) -> np.ndarray:
    """An elevation surface rising eastward by a fixed amount per pixel."""
    return np.tile(np.arange(shape[1], dtype=np.float32) * rise_per_pixel, (shape[0], 1))


# ── Cloud ────────────────────────────────────────────────────────────────────────────────────────


def test_cloud_probability_threshold_keeps_unknown_observations_out_of_the_clear_class() -> None:
    probabilities = np.array([[0.39, 0.4], [np.nan, 0.9]], dtype=np.float32)

    mask = threshold_cloud_probability(probabilities, 0.4)

    # NaN is not cloud, and it is emphatically not clear sky either - `exclusion_mask` picks it up
    # separately. Treating it as clear is how an unjudged pixel becomes a reported index value.
    assert mask.tolist() == [[False, True], [False, True]]


def test_cloud_probability_outside_zero_to_one_is_refused_rather_than_clipped() -> None:
    # A probability of 4.0 means the caller passed reflectance, or a percentage, or a different model's
    # output. Clipping it to 1.0 turns a wiring mistake into a scene that is 100% cloud.
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        threshold_cloud_probability(np.array([[0.5, 4.0]], dtype=np.float32), 0.4)


def test_a_scene_with_no_judged_pixels_produces_no_cloud_rather_than_an_error() -> None:
    mask = threshold_cloud_probability(np.full((4, 4), np.nan, dtype=np.float32), 0.4)

    assert not mask.any()


def test_shadow_projects_away_from_the_sun_without_overwriting_the_cloud() -> None:
    clouds = np.zeros((9, 9), dtype=bool)
    clouds[4, 4] = True

    # Sun due north at 45 deg elevation: a 2 m cloud casts its shadow 2 / tan(45) = 2 m southward,
    # which on a 1 m grid is two rows down.
    shadow = project_cloud_shadow(
        clouds,
        sun_azimuth_degrees=0.0,
        sun_elevation_degrees=45.0,
        cloud_height_metres=2.0,
        pixel_size_metres=1.0,
        dilation_pixels=0,
    )

    assert shadow[6, 4]
    assert shadow.sum() == 1
    assert not shadow[4, 4]


def test_shadow_direction_follows_the_sun_rather_than_a_fixed_axis() -> None:
    clouds = np.zeros((9, 9), dtype=bool)
    clouds[4, 4] = True
    geometry = {
        "sun_elevation_degrees": 45.0,
        "cloud_height_metres": 2.0,
        "pixel_size_metres": 1.0,
        "dilation_pixels": 0,
    }

    # Sun in the west throws the shadow east; sun in the east throws it west. A projection that ignored
    # azimuth would put both in the same place and still look like a shadow mask.
    from_west = project_cloud_shadow(clouds, sun_azimuth_degrees=270.0, **geometry)
    from_east = project_cloud_shadow(clouds, sun_azimuth_degrees=90.0, **geometry)

    assert from_west[4, 6]
    assert from_east[4, 2]


# ── Registration ─────────────────────────────────────────────────────────────────────────────────


def test_registration_recovers_a_known_translation_and_reports_no_disagreement() -> None:
    reference = np.random.default_rng(11).normal(size=(256, 256)).astype(np.float32)
    moving = np.roll(np.roll(reference, 3, axis=0), -2, axis=1)

    measurement = measure_registration_residual(reference, moving, tile_size=64, minimum_valid_tiles=4)

    assert measurement.row_shift_pixels == pytest.approx(-3.0, abs=0.1)
    assert measurement.column_shift_pixels == pytest.approx(2.0, abs=0.1)
    assert measurement.residual_pixels < 0.05


def test_registration_residual_is_large_when_translation_changes_by_tile() -> None:
    generator = np.random.default_rng(7)
    reference = generator.normal(size=(256, 256)).astype(np.float32)
    moving = np.empty_like(reference)
    moving[:128] = np.roll(reference[:128], 2, axis=1)
    moving[128:] = np.roll(reference[128:], -3, axis=1)

    measurement = measure_registration_residual(reference, moving, tile_size=64, minimum_valid_tiles=4)

    # Half the tiles sit at +2 and half at -3 about a median of one of them, so the disagreement is
    # metres of ground, not rounding. This is the pair that must never reach change detection.
    assert measurement.residual_pixels > 0.5


def test_invalid_pixels_are_filled_without_leaving_an_edge_to_lock_onto() -> None:
    """Regression: invalid pixels were filled with zero, and the correlator locked onto that edge.

    A hard zero block is a strong feature. Tiles touching the nodata margin reported a shift of exactly
    (0, 0) - which reads as *perfect* registration rather than as a failure - and those false zeros
    dragged the residual to 1.02 px on the gate scene, refusing a pair aligned to 0.00 px. 1.3% nodata
    was enough.

    Asserted on the fill itself rather than on a residual, because the downstream effect could not be
    reproduced synthetically: white noise locks through the artefact and smooth noise never locks at
    all, so only real imagery texture sits in the band where the edge wins. The property the fix
    actually delivers is this one - the filled tile is continuous - and it is measurable exactly.
    """
    tile = np.full((16, 16), 3000.0)
    tile[:4, :] = np.nan
    valid = np.isfinite(tile)

    filled = _fill_with_mean(tile, valid)

    assert np.isfinite(filled).all()
    assert filled.std() == pytest.approx(0.0), "the fill introduced a step the correlator can see"
    assert filled[valid] == pytest.approx(3000.0)


def test_nodata_does_not_invent_a_registration_error() -> None:
    """A pair with a nodata margin and one rigid translation still measures as well registered."""
    generator = np.random.default_rng(19)
    reference = generator.normal(loc=5.0, size=(256, 256)).astype(np.float32)
    # Eight rows, not more: a deeper band drops the affected tiles below the 0.8 validity floor and they
    # are skipped, so no tile ever contains the nodata edge and the test proves nothing. The first
    # version of this test made exactly that mistake and passed against the bug it was written for.
    reference[:8, :] = np.nan
    moving = np.roll(reference, 2, axis=1)

    measurement = measure_registration_residual(reference, moving, tile_size=64, minimum_valid_tiles=4)

    assert measurement.valid_tile_count == 16
    assert measurement.column_shift_pixels == pytest.approx(-2.0, abs=0.1)
    assert measurement.residual_pixels < 0.05


def test_the_reported_translation_is_the_one_most_of_the_scene_agrees_on() -> None:
    """A quarter of the scene failing must not move the shift the rest of it measured.

    The median is what makes that true: a mean over the same tiles lands between the two answers, at a
    translation no part of the image actually has, and a later stage would align the pair by it.
    """
    generator = np.random.default_rng(23)
    reference = generator.normal(size=(256, 256)).astype(np.float32)
    moving = np.roll(reference, 2, axis=1)
    moving[192:] = np.roll(reference[192:], 20, axis=1)

    measurement = measure_registration_residual(reference, moving, tile_size=64, minimum_valid_tiles=4)

    assert measurement.column_shift_pixels == pytest.approx(-2.0, abs=0.1)
    # And the disagreement is still reported, so the pair is refused rather than quietly aligned.
    assert measurement.residual_pixels > 0.5


def test_registration_refuses_rather_than_reporting_a_shift_it_could_not_measure() -> None:
    flat = np.zeros((128, 128), dtype=np.float32)

    with pytest.raises(ValueError, match="textured valid tiles"):
        measure_registration_residual(flat, flat, tile_size=64, minimum_valid_tiles=4)


# ── Speckle ──────────────────────────────────────────────────────────────────────────────────────


def test_lee_filter_smooths_equally_speckled_ground_by_the_same_amount_at_any_brightness() -> None:
    """Regression: the filter used an additive-noise model on multiplicative speckle.

    Speckle's standard deviation scales with the local mean, so a dark lake and a bright field with
    identical speckle statistics have local variances two orders of magnitude apart. Comparing local
    variance against one global noise variance therefore read the lake as quiet and flattened it, while
    leaving the field alone. Measured on this code before the fix: 25x smoothing dark, 1.4x bright.
    Downstream, a change detector reads that collapse of variance over water as a finding.
    """
    generator = np.random.default_rng(0)
    speckle = generator.gamma(shape=1.0, scale=1.0, size=(256, 256))
    truth = np.full((256, 256), 0.05)
    truth[:, 128:] = 1.0
    power = (truth * speckle).astype(np.float32)

    filtered = lee_filter(power, window_size=5, number_of_looks=1.0, epsilon=1e-10)

    def equivalent_looks(values: np.ndarray) -> float:
        finite = values[np.isfinite(values)]
        return float(finite.mean() ** 2 / finite.var())

    dark = np.s_[:, 10:118]
    bright = np.s_[:, 138:-10]
    dark_gain = equivalent_looks(filtered[dark]) / equivalent_looks(power[dark])
    bright_gain = equivalent_looks(filtered[bright]) / equivalent_looks(power[bright])

    assert dark_gain > 2.0
    assert bright_gain > 2.0
    assert max(dark_gain, bright_gain) / min(dark_gain, bright_gain) < 2.0


def test_lee_filter_preserves_radiometry_and_nodata() -> None:
    generator = np.random.default_rng(3)
    power = generator.gamma(shape=1.0, scale=1.0, size=(96, 96)).astype(np.float32)
    power[0, 0] = np.nan

    filtered = lee_filter(power, window_size=5, number_of_looks=1.0, epsilon=1e-10)

    assert np.nanvar(filtered) < np.nanvar(power)
    assert np.isnan(filtered[0, 0])
    # A smoothing filter that also shifts the mean has changed the backscatter, not just its texture.
    assert np.nanmean(filtered) == pytest.approx(np.nanmean(power), rel=0.02)


def test_lee_filter_leaves_a_hard_edge_where_it_is() -> None:
    power = np.full((64, 64), 0.1, dtype=np.float32)
    power[:, 32:] = 10.0

    filtered = lee_filter(power, window_size=5, number_of_looks=4.4, epsilon=1e-10)

    # Local variation across the step is far above speckle's own, so the weight goes to one and the
    # pixels are returned untouched. A filter that blurred here would erase coastlines.
    assert filtered[10, 20] == pytest.approx(0.1, rel=1e-3)
    assert filtered[10, 45] == pytest.approx(10.0, rel=1e-3)


def test_lee_filter_does_not_drag_the_scene_edge_towards_nodata() -> None:
    """Nodata is excluded from the local statistics, not averaged in as zero (§8 rule 4).

    A window straddling the nodata margin covers fewer real pixels than its own area, so the sums have
    to be divided by how many were real. Dividing by the window area instead pulls every pixel beside a
    scene edge towards zero - a dark rim that looks like genuinely low backscatter.
    """
    power = np.full((32, 32), 4.0, dtype=np.float32)
    power[:, :8] = np.nan

    filtered = lee_filter(power, window_size=5, number_of_looks=4.4, epsilon=1e-10)

    assert filtered[16, 8] == pytest.approx(4.0, rel=1e-3)
    assert filtered[16, 9] == pytest.approx(4.0, rel=1e-3)
    assert np.isnan(filtered[16, 7])


def test_lee_filter_rejects_a_window_that_has_no_centre() -> None:
    power = np.ones((16, 16), dtype=np.float32)

    with pytest.raises(ValueError, match="odd integer"):
        lee_filter(power, window_size=4, number_of_looks=4.4, epsilon=1e-10)


# ── Terrain ──────────────────────────────────────────────────────────────────────────────────────


def test_layover_is_on_the_slope_facing_the_radar_and_shadow_on_the_slope_behind_it() -> None:
    """Regression: the two masks were swapped, and nothing in the suite could see it.

    The original test asserted only that both masks were non-empty and differed from each other, which
    stays true when the sign flips. A swap is invisible in a figure - both cases put a plausible mask on
    plausible ground - and it silently exchanges the two states §8 rule 7 exists to keep apart.

    Look azimuth 90 deg means the beam travels east, so the sensor is to the west. Terrain rising
    westward faces the sensor and folds; terrain rising eastward hides behind itself.
    """
    power = np.ones((16, 16), dtype=np.float32)
    incidence = 35.0

    # A 45 deg slope: steeper than the 35 deg incidence, so a foreslope is in layover, and shallower
    # than the 55 deg needed for shadow, so a backslope is merely dim.
    facing_sensor = terrain_flatten(
        power, _ramp(-1.0), incidence_angle_degrees=incidence,
        radar_azimuth_degrees=90.0, pixel_size_metres=1.0, epsilon=1e-10,
    )
    facing_away = terrain_flatten(
        power, _ramp(+1.0), incidence_angle_degrees=incidence,
        radar_azimuth_degrees=90.0, pixel_size_metres=1.0, epsilon=1e-10,
    )

    assert facing_sensor.layover_mask.all()
    assert not facing_sensor.shadow_mask.any()
    assert not facing_away.layover_mask.any()
    assert not facing_away.shadow_mask.any()

    # Past 55 deg away from the sensor the ground is never illuminated at all.
    steep_away = terrain_flatten(
        power, _ramp(+2.0), incidence_angle_degrees=incidence,
        radar_azimuth_degrees=90.0, pixel_size_metres=1.0, epsilon=1e-10,
    )
    assert steep_away.shadow_mask.all()
    assert not steep_away.layover_mask.any()


def test_the_masks_follow_the_look_direction_rather_than_the_column_axis() -> None:
    power = np.ones((16, 16), dtype=np.float32)
    rising_east = _ramp(+1.0)

    looking_east = terrain_flatten(
        power, rising_east, incidence_angle_degrees=35.0,
        radar_azimuth_degrees=90.0, pixel_size_metres=1.0, epsilon=1e-10,
    )
    looking_west = terrain_flatten(
        power, rising_east, incidence_angle_degrees=35.0,
        radar_azimuth_degrees=270.0, pixel_size_metres=1.0, epsilon=1e-10,
    )

    # One surface, two orbits: the slope that hides from an eastward look faces a westward one.
    assert not looking_east.layover_mask.any()
    assert looking_west.layover_mask.all()


def test_flat_ground_passes_through_terrain_correction_unchanged() -> None:
    """Regression: the correction was cos(slope)/cos(incidence), which is 1.22 on flat ground at 35 deg.

    A correction that is not the identity where there is nothing to correct is a gain wearing a
    correction's name, and it biases every backscatter value in a scene by a constant nobody declared.
    """
    power = np.full((16, 16), 0.25, dtype=np.float32)

    result = terrain_flatten(
        power, np.zeros((16, 16), dtype=np.float32), incidence_angle_degrees=35.0,
        radar_azimuth_degrees=100.0, pixel_size_metres=10.0, epsilon=1e-10,
    )

    assert result.corrected_power == pytest.approx(power, rel=1e-6)
    assert result.local_incidence_degrees == pytest.approx(np.full((16, 16), 35.0), abs=1e-4)
    assert result.obscured_fraction == 0.0


def test_local_incidence_is_the_nominal_angle_less_the_slope_towards_the_sensor() -> None:
    power = np.ones((16, 16), dtype=np.float32)

    # A 20 m rise per 100 m pixel is atan(0.2) = 11.31 deg. Rising west with an eastward look means it
    # rises towards the sensor, so the local incidence is 39 - 11.31 = 27.69 deg.
    result = terrain_flatten(
        power, _ramp(-20.0), incidence_angle_degrees=39.0,
        radar_azimuth_degrees=90.0, pixel_size_metres=100.0, epsilon=1e-10,
    )

    interior = result.local_incidence_degrees[4:-4, 4:-4]
    assert interior == pytest.approx(np.full(interior.shape, 27.69), abs=0.02)


def test_a_foreslope_is_darkened_and_a_backslope_brightened_by_the_area_correction() -> None:
    power = np.full((16, 16), 1.0, dtype=np.float32)
    geometry = {
        "incidence_angle_degrees": 39.0,
        "radar_azimuth_degrees": 90.0,
        "pixel_size_metres": 100.0,
        "epsilon": 1e-10,
    }

    towards = terrain_flatten(power, _ramp(-20.0), **geometry)
    away = terrain_flatten(power, _ramp(+20.0), **geometry)

    # A slope tilted into the beam presents more surface per unit of ground and returns more energy;
    # flattening removes that geometric advantage rather than reporting it as brighter ground.
    assert float(np.nanmean(towards.corrected_power[4:-4, 4:-4])) < 1.0
    assert float(np.nanmean(away.corrected_power[4:-4, 4:-4])) > 1.0


def test_terrain_keeps_layover_and_shadow_as_different_masks_and_neither_carries_a_value() -> None:
    power = np.ones((9, 9), dtype=np.float32)
    elevation = np.zeros((9, 9), dtype=np.float32)
    elevation[:, 3:] = -20.0
    elevation[:, 6:] = 20.0

    result = terrain_flatten(
        power, elevation, incidence_angle_degrees=35.0,
        radar_azimuth_degrees=90.0, pixel_size_metres=1.0, epsilon=1e-10,
    )

    assert result.layover_mask.any()
    assert result.shadow_mask.any()
    assert not (result.layover_mask & result.shadow_mask).any()
    # Neither state gets a number. A backscatter value over layover is a measurement of two places at
    # once, and one over shadow is a measurement of nothing - §8 rule 7.
    assert np.isnan(result.corrected_power[result.obscured_mask]).all()
    assert result.obscured_fraction == pytest.approx(float(result.obscured_mask.mean()))


def test_unknown_elevation_produces_unknown_visibility_rather_than_clear_ground() -> None:
    power = np.ones((8, 8), dtype=np.float32)
    elevation = np.zeros((8, 8), dtype=np.float32)
    elevation[2, 2] = np.nan

    result = terrain_flatten(
        power, elevation, incidence_angle_degrees=35.0,
        radar_azimuth_degrees=90.0, pixel_size_metres=10.0, epsilon=1e-10,
    )

    # A hole in the DEM propagates: the gradient around it is undefined, so those pixels cannot be
    # corrected and must not be reported as if they had been.
    assert np.isnan(result.corrected_power[2, 2])


# ── Grids ────────────────────────────────────────────────────────────────────────────────────────


def test_grid_match_requires_transform_as_well_as_crs_and_shape() -> None:
    reference = GridDefinition(100, 100, "EPSG:32643", (10.0, 0.0, 1.0, 0.0, -10.0, 2.0))
    shifted = GridDefinition(100, 100, "EPSG:32643", (10.0, 0.0, 1.5, 0.0, -10.0, 2.0))

    # Same size, same CRS, half a pixel apart. Comparing these by index compares different ground.
    assert not grids_match(reference, shifted)
    assert grids_match(reference, reference)


def test_grid_match_separates_the_same_extent_at_different_resolutions() -> None:
    coarse = GridDefinition(50, 50, "EPSG:32643", (20.0, 0.0, 0.0, 0.0, -20.0, 0.0))
    fine = GridDefinition(100, 100, "EPSG:32643", (10.0, 0.0, 0.0, 0.0, -10.0, 0.0))

    assert not grids_match(coarse, fine)


# ── Recorded run ─────────────────────────────────────────────────────────────────────────────────
#
#   uv run pytest tests/unit/test_preprocessing_math.py -q -p no:warnings
#   25 passed in 0.81s
#
# MUTATION PASS - 16 applied against this file and tests/integration/test_preprocessing.py.
# 14 caught, 1 equivalent, 1 pending infrastructure. Every mutated file was byte-compared after restore.
#
#   A  slope measured away from the sensor, not towards it (the original bug)  caught
#        test_layover_is_on_the_slope_facing_the_radar_and_shadow_on_the_slope_behind_it
#   B  correction back to cos(slope)/cos(incidence), 1.22x on flat ground      caught
#        test_flat_ground_passes_through_terrain_correction_unchanged
#   C  shadow never marked, so unreadable ground reports a value               caught
#   D  speckle treated as additive noise again (the original bug)              caught
#        test_lee_filter_smooths_equally_speckled_ground_by_the_same_amount_at_any_brightness
#   E  nodata-neighbour rescale dropped, pulling scene edges towards zero      caught (2nd pass)
#   F  registration fills nodata with zero again (the original bug)            caught (3rd pass)
#   G  residual measured about the mean rather than the median                 caught (2nd pass)
#   H  cloud threshold becomes exclusive                                       caught
#   I  an unjudged pixel treated as clear sky                                  EQUIVALENT - see below
#   J  shadow projected towards the sun instead of away                        caught
#   K  an already-calibrated product calibrated again anyway                   caught
#   L  negative power clamped to zero rather than dropped                      caught
#   M  categorical raster resampled bilinearly, inventing classes              caught
#   N  grids compared on shape and CRS only, ignoring the transform            caught
#   O  backscatter stretch back to per-scene percentiles                       pending MinIO
#   P  the co-registration refusal downgraded to acceptance                    caught
#
# THREE SURVIVED THE FIRST PASS, and all three were real gaps rather than equivalent mutations:
#
#   E had no test at all - nothing covered the Lee filter beside a nodata margin, which is exactly
#     where §8 rule 4 is broken quietly. `test_lee_filter_does_not_drag_the_scene_edge_towards_nodata`.
#
#   G survived because RMS about the mean and about the median agree when disagreement is symmetric,
#     which is what the existing test constructed. The property that actually separates them is the
#     reported *translation*, not the residual: a quarter of the scene failing must not move the shift
#     the rest of it measured. `test_the_reported_translation_is_the_one_most_of_the_scene_agrees_on`.
#
#   F survived a test written specifically for it. The NaN band was 24 rows deep against a 64-row tile,
#     so the affected tiles were 62.5% valid, fell below the 0.8 floor and were SKIPPED - no tile in
#     the test ever contained a nodata edge. Narrowing the band to 8 rows fixed the construction but
#     still did not catch the mutation: white noise locks through the artefact and gaussian-smoothed
#     noise never locks at all, so no synthetic texture reproduces the real failure. Pinned instead on
#     the property the fix delivers - the filled tile is continuous - which is exact and measurable.
#
# I is recorded as equivalent rather than papered over. `np.nan_to_num(p, nan=0.0) >= threshold` and
# `isfinite(p) & (p >= threshold)` return the same mask for every threshold in (0, 1], and the project
# threshold is 0.4. They differ only at threshold 0.0, which no caller uses. The claim the isfinite
# guard actually carries - that an unjudged pixel is not clear sky - is enforced on `obscured_fraction`
# in the integration suite, where it is observable.
