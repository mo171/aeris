"""Tests the Phase 1.3 service boundaries and the acceptance gates behind them.

what  : Async service tests for mask application, the co-registration refusal, reprojection, the fixed SAR
        order, and the backscatter figure's wire contract.
where : ``tests/integration`` because rasterio file I/O, the s2cloudless model and the figure storage path
        are all part of what is being asserted.
how   : Synthetic arrays keep the scientific result inspectable while exercising the same boundaries a
        satellite scene does, so the suite does not depend on a download. The end-to-end demonstration on
        real Sentinel-1 and Copernicus DEM data is `aeris preprocess`, recorded at the bottom of this file.
"""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.constants.preprocessing import SAR_BACKSCATTER_DECIBEL_DOMAIN
from app.constants.scenes import Polarisation
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.exceptions import InvalidRequestError
from app.services.preprocessing.cloud_masking import (
    apply_optical_mask,
    build_optical_mask,
    infer_s2cloudless_probability,
)
from app.services.preprocessing.coregistration import measure_coregistration, require_comparison_ready
from app.services.preprocessing.math.grid_alignment import GridDefinition
from app.services.preprocessing.reprojection import reproject_to_reference_grid, require_matching_grids
from app.services.preprocessing.sar_calibration import preprocess_sar
from app.services.rendering.figures import render_sar_backscatter

DEFAULT_TRANSFORM = from_origin(0.0, 100.0, 10.0, 10.0)

SUN = {
    "sun_azimuth_degrees": 0.0,
    "sun_elevation_degrees": 45.0,
    "cloud_height_metres": 2.0,
    "pixel_size_metres": 1.0,
}
RADAR = {
    "incidence_angle_degrees": 35.0,
    "radar_azimuth_degrees": 90.0,
    "pixel_size_metres": 1.0,
}


def write_raster(path: Path, values: np.ndarray, *, transform=DEFAULT_TRANSFORM, nodata=None) -> Path:
    """Write a small projected raster whose grid is unambiguous to the reprojection service."""
    if nodata is None:
        nodata = np.nan if np.issubdtype(values.dtype, np.floating) else None
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=values.shape[0],
        width=values.shape[1],
        count=1,
        dtype=values.dtype,
        crs="EPSG:32643",
        transform=transform,
        nodata=nodata,
    ) as destination:
        destination.write(values, 1)
    return path


# ── S7 cloud handling ────────────────────────────────────────────────────────────────────────────


async def test_optical_mask_is_applied_before_downstream_values_are_returned() -> None:
    probability = np.zeros((12, 12), dtype=np.float32)
    probability[4, 4] = 1.0
    result = await build_optical_mask(probability, **SUN)

    masked = await apply_optical_mask(np.ones((12, 12), dtype=np.float32), result)

    assert np.isnan(masked[4, 4])
    assert np.isnan(masked[6, 4]), "the projected shadow must be removed before index arithmetic"
    assert masked[0, 0] == 1.0


async def test_the_obscured_fraction_counts_unjudged_pixels_as_unread() -> None:
    cloud_only = np.zeros((10, 10), dtype=np.float32)
    cloud_only[5, 5] = 1.0
    with_unjudged_row = cloud_only.copy()
    with_unjudged_row[0, :] = np.nan

    judged = await build_optical_mask(cloud_only, **SUN)
    partly_unjudged = await build_optical_mask(with_unjudged_row, **SUN)

    # One cloud pixel, dilated and projected two rows down the sun's bearing, is six obscured pixels.
    assert judged.cloud_mask.sum() == 1
    assert judged.obscured_fraction == pytest.approx(6 / 100)
    # The ten pixels the detector could not judge have not been shown to the operator either, so they
    # raise the fraction by exactly their own share. Counting them as clear would overstate the read.
    assert partly_unjudged.obscured_fraction == pytest.approx(16 / 100)


async def test_a_mask_from_a_different_grid_is_refused_rather_than_broadcast() -> None:
    result = await build_optical_mask(np.zeros((8, 8), dtype=np.float32), **SUN)

    with pytest.raises(ValueError, match="one grid"):
        await apply_optical_mask(np.ones((16, 16), dtype=np.float32), result)


async def test_s2cloudless_inference_returns_one_probability_per_input_pixel() -> None:
    """The real model boundary: the documented ten-band cube in, a probability on the same grid out."""
    probability = await infer_s2cloudless_probability(np.full((16, 16, 10), 0.1, dtype=np.float32))

    assert probability.shape == (16, 16)
    assert probability.dtype == np.float32
    assert np.isfinite(probability).all()
    assert ((probability >= 0.0) & (probability <= 1.0)).all()


async def test_s2cloudless_refuses_a_band_set_it_did_not_train_on() -> None:
    # Handing it four bands would not fail; the model would read a different spectrum into each slot and
    # return a confident probability map of nothing.
    with pytest.raises(ValueError, match="Sentinel-2 reflectance cube"):
        await infer_s2cloudless_probability(np.zeros((16, 16, 4), dtype=np.float32))


async def test_s2cloudless_separates_bright_cloud_from_dark_ground() -> None:
    """The model is wired up, not merely shaped correctly."""
    bright = await infer_s2cloudless_probability(np.full((32, 32, 10), 0.8, dtype=np.float32))
    dark = await infer_s2cloudless_probability(np.full((32, 32, 10), 0.02, dtype=np.float32))

    assert float(bright.mean()) > float(dark.mean())


# ── S8 / S10 spatial normalisation ───────────────────────────────────────────────────────────────


async def test_reprojection_writes_the_source_on_the_reference_grid(tmp_path: Path) -> None:
    source = write_raster(tmp_path / "source.tif", np.arange(16, dtype=np.float32).reshape(4, 4))
    reference = write_raster(
        tmp_path / "reference.tif",
        np.zeros((8, 8), dtype=np.float32),
        transform=from_origin(0.0, 100.0, 5.0, 5.0),
    )

    result = await reproject_to_reference_grid(source, reference, tmp_path / "aligned.tif")

    with rasterio.open(tmp_path / "aligned.tif") as aligned:
        assert (aligned.width, aligned.height) == (8, 8)
        assert aligned.transform == from_origin(0.0, 100.0, 5.0, 5.0)
    assert result.resampling == "bilinear"
    assert result.grid.crs == "EPSG:32643"


async def test_a_categorical_raster_is_resampled_without_inventing_classes(tmp_path: Path) -> None:
    """§8 rule 6. Interpolating a class label produces a class that means nothing.

    Bilinear between class 4 and class 8 yields 6 - a label the classifier never assigned and that the
    legend has no entry for. Nearest neighbour is the only correct choice, and it is chosen by the
    caller declaring what the data *is*, not inferred from its dtype.
    """
    classes = np.array([[4, 4, 8, 8]] * 4, dtype=np.uint8)
    source = write_raster(tmp_path / "classes.tif", classes)
    reference = write_raster(
        tmp_path / "reference.tif",
        np.zeros((8, 8), dtype=np.uint8),
        transform=from_origin(0.0, 100.0, 5.0, 5.0),
    )

    result = await reproject_to_reference_grid(
        source, reference, tmp_path / "aligned.tif", categorical=True
    )

    with rasterio.open(tmp_path / "aligned.tif") as aligned:
        present = set(np.unique(aligned.read(1)).tolist())
    assert result.resampling == "nearest"
    assert present <= {4, 8}, f"resampling invented the classes {sorted(present - {4, 8})}"


async def test_a_continuous_raster_is_interpolated_rather_than_stepped(tmp_path: Path) -> None:
    source = write_raster(tmp_path / "ramp.tif", np.array([[0.0, 0.0, 8.0, 8.0]] * 4, dtype=np.float32))
    reference = write_raster(
        tmp_path / "reference.tif",
        np.zeros((8, 8), dtype=np.float32),
        transform=from_origin(0.0, 100.0, 5.0, 5.0),
    )

    await reproject_to_reference_grid(source, reference, tmp_path / "aligned.tif")

    with rasterio.open(tmp_path / "aligned.tif") as aligned:
        values = set(np.unique(aligned.read(1)).tolist())
    assert values - {0.0, 8.0}, "bilinear resampling of a ramp should produce intermediate values"


async def test_two_rasters_that_were_never_aligned_are_refused_by_grid(tmp_path: Path) -> None:
    left = GridDefinition(100, 100, "EPSG:32643", (10.0, 0.0, 0.0, 0.0, -10.0, 0.0))
    half_a_pixel_east = GridDefinition(100, 100, "EPSG:32643", (10.0, 0.0, 5.0, 0.0, -10.0, 0.0))

    await require_matching_grids(left, left)
    with pytest.raises(InvalidRequestError, match="not on one grid"):
        await require_matching_grids(left, half_a_pixel_east)


# ── S9 co-registration ───────────────────────────────────────────────────────────────────────────


async def test_a_well_registered_pair_is_accepted_with_its_residual_reported() -> None:
    reference = np.random.default_rng(21).normal(size=(256, 256)).astype(np.float32)
    moving = np.roll(reference, 2, axis=1)

    result = await measure_coregistration(reference, moving, tile_size=64, minimum_valid_tiles=4)

    await require_comparison_ready(result)
    assert result.is_accepted
    assert result.measurement.residual_pixels < result.tolerance_pixels


async def test_bad_coregistration_pair_is_refused_with_its_measured_reason() -> None:
    generator = np.random.default_rng(4)
    reference = generator.normal(size=(256, 256)).astype(np.float32)
    moving = np.empty_like(reference)
    moving[:128] = np.roll(reference[:128], 2, axis=1)
    moving[128:] = np.roll(reference[128:], -3, axis=1)

    result = await measure_coregistration(reference, moving, tile_size=64, minimum_valid_tiles=4)

    assert not result.is_accepted
    with pytest.raises(InvalidRequestError, match="co-registration residual") as error:
        await require_comparison_ready(result)
    # The refusal carries the measurement, so an operator reads *how far out* it was rather than being
    # told only that something was wrong. §8 rule 2 - refusing is the answer, not a failure to answer.
    assert error.value.details["residualPixels"] > error.value.details["tolerancePixels"]
    assert error.value.details["validTileCount"] > 0


# ── S10 the SAR branch ───────────────────────────────────────────────────────────────────────────


async def test_sar_preprocessing_retains_visibility_masks_over_real_relief() -> None:
    observed = np.full((32, 32), 0.2, dtype=np.float32)
    elevation = np.tile(np.arange(32, dtype=np.float32) * -1.5, (32, 1))
    elevation[:, 16:] = np.arange(16, dtype=np.float32) * 3.0

    result = await preprocess_sar(
        observed, elevation, polarisation=Polarisation.VV, calibration_factor=None, **RADAR
    )

    assert result.layover_mask.any()
    assert result.shadow_mask.any()
    assert not (result.layover_mask & result.shadow_mask).any()
    assert result.obscured_fraction > 0.0
    assert np.isnan(result.backscatter_decibels[result.obscured_mask]).all()


async def test_an_already_calibrated_product_is_not_calibrated_again() -> None:
    """A second calibration does not fail. It returns the square of the truth, and it opens cleanly.

    Every RTC product - including the Sentinel-1 scene this phase's gate runs on - arrives in linear
    power. `calibration_factor=None` is how a caller says so, and it is the radar reading of §8 rule 5.
    """
    power = np.full((16, 16), 0.25, dtype=np.float32)
    flat = np.zeros((16, 16), dtype=np.float32)

    passed_through = await preprocess_sar(
        power, flat, polarisation=Polarisation.VV, calibration_factor=None, **RADAR
    )
    calibrated_again = await preprocess_sar(
        power, flat, polarisation=Polarisation.VV, calibration_factor=1.0, **RADAR
    )

    assert float(np.nanmean(passed_through.calibrated_power)) == pytest.approx(0.25, rel=1e-5)
    assert float(np.nanmean(calibrated_again.calibrated_power)) == pytest.approx(0.0625, rel=1e-5)


async def test_negative_power_in_a_calibrated_product_is_dropped_rather_than_kept() -> None:
    power = np.full((16, 16), 0.25, dtype=np.float32)
    power[3, 3] = -9999.0

    result = await preprocess_sar(
        power, np.zeros((16, 16), dtype=np.float32),
        polarisation=Polarisation.VV, calibration_factor=None, **RADAR,
    )

    # Negative power is unphysical, so this is a wrong nodata value rather than very dark ground.
    assert np.isnan(result.calibrated_power[3, 3])


async def test_a_polarisation_ratio_cannot_be_preprocessed_as_if_it_were_measured() -> None:
    with pytest.raises(ValueError, match="derived from two"):
        await preprocess_sar(
            np.ones((8, 8), dtype=np.float32), np.zeros((8, 8), dtype=np.float32),
            polarisation=Polarisation.RATIO, calibration_factor=None, **RADAR,
        )


@pytest.mark.integration
async def test_the_backscatter_figure_speaks_the_frontends_vocabulary(tmp_path: Path) -> None:
    result = await preprocess_sar(
        np.full((32, 32), 0.2, dtype=np.float32),
        np.tile(np.arange(32, dtype=np.float32) * -1.5, (32, 1)),
        polarisation=Polarisation.VV, calibration_factor=None, **RADAR,
    )

    figure = await render_sar_backscatter(
        result.backscatter_decibels,
        run_id=new_identifier(IdentifierPrefix.RUN),
        trace_step_id=new_identifier(IdentifierPrefix.TRACE_STEP),
        title="VV backscatter",
        polarisation=Polarisation.VV,
        mask_applied=True,
    )

    specification = figure.event.render_spec
    # Upper case, because `polarisationSchema` is. A lower-case `vv` parses on neither side.
    assert specification.bands == ["VV"]
    assert figure.event.kind.value == "sar-backscatter"
    assert figure.event.legend.label == "VV backscatter (dB)"
    assert specification.color_ramp.value == "sar-grayscale"
    assert specification.mask_applied is True


@pytest.mark.integration
async def test_the_backscatter_stretch_is_fixed_so_two_dates_are_comparable() -> None:
    """A radar time series exists to be compared; a per-date percentile stretch destroys that.

    Two scenes with different backscatter distributions must land on the same grey for the same dB, or
    a flooded field and a calm one look alike and the change the operator came for is invisible.
    """
    quiet = np.full((16, 16), -18.0, dtype=np.float32)
    loud = np.full((16, 16), -4.0, dtype=np.float32)
    common = {
        "run_id": new_identifier(IdentifierPrefix.RUN),
        "trace_step_id": new_identifier(IdentifierPrefix.TRACE_STEP),
        "title": "VV backscatter",
        "polarisation": Polarisation.VH,
        "mask_applied": False,
    }

    first = await render_sar_backscatter(quiet, **common)
    second = await render_sar_backscatter(loud, **common)

    minimum, maximum = SAR_BACKSCATTER_DECIBEL_DOMAIN
    for figure in (first, second):
        assert figure.event.render_spec.stretch == {
            "min": minimum, "max": maximum, "method": "fixed"
        }
        assert figure.event.legend.domain == [minimum, maximum]
    assert first.event.render_spec.bands == ["VH"]


# ── Recorded run ─────────────────────────────────────────────────────────────────────────────────
#
#   uv run pytest tests/integration/test_preprocessing.py -q -p no:warnings -m "not integration"
#   16 passed, 2 deselected in 2.94s
#
#   uv run pytest -q -p no:warnings -m "not integration"
#   337 passed, 60 deselected in 34.65s        ruff 0        uv lock --check 0
#
# The two deselected tests upload a figure, so they need MinIO. `docker compose up -d` first; the suite
# is configured to fail loudly rather than skip when infrastructure is missing.
#
# THE PHASE 1.3 GATE, on real data.
#
#   uv run aeris preprocess coregister notebooks/01_remote_sensing/data          exit 0
#
#     reference s2_B04.tif  1024x1024  nodata 1.3%  tolerance 0.5 px
#     known-good  one rigid translation of (2.5, -1.25)   residual 0.0000 px   accepted
#     known-bad   opposite translations in each half      residual 4.0000 px   REFUSED
#     real pair   s2_B04.tif against s2_B08.tif           residual 0.1436 px   accepted
#
#   The bad pair's 4.0000 px is hand-checkable: half the tiles sit at +4 and half at -4 about a median
#   of 0, so the RMS is exactly 4. It is aligned on average and wrong everywhere, which is the pair a
#   global shift measurement would wave through.
#
#   uv run aeris preprocess sar notebooks/01_remote_sensing/data
#
#     s1_vv.tif  1066x1120  10 m  EPSG:32643      Copernicus DEM GLO-30, 100% known
#     elevation -9 to 82 m                        local incidence 2.2 to 71.1 deg (nominal 39)
#     speckle   coefficient of variation 17.782 -> 16.446
#     radar could not see   0.00%                 radar saw nothing   0.02%
#
#   ZERO IS THE CORRECT ANSWER HERE and it is why this command's gate is not `obscured > 0`. Layover
#   needs a slope steeper than the incidence angle; the scene is coastal Mumbai with 91 m of relief and
#   has none. What the command checks is that the terrain actually reached the geometry - a DEM that
#   never arrived leaves the local incidence pinned at the nominal angle instead of spanning 69 degrees.
#   An operator needs the zero in order to read an absence of radar evidence as evidence.
#
#   uv run aeris preprocess relief                                              exit 0
#
#     Khumbu, Nepal (86.8, 27.9, 86.95, 28.05)    elevation 4276 to 8737 m, relief 4461 m
#     S1A_IW_GRDH_1SDV_20230325T001130_20230325T001155_047793_05BDF2_rtc
#     window 1477x1663 of a 27577x21415 scene, read in place rather than downloaded
#
#       look azimuth 280 deg   could not see 8.55%  (layover 7.35%, shadow 1.20%)   saw nothing 0.02%
#       look azimuth 100 deg   could not see 7.34%  (layover 5.16%, shadow 2.18%)   saw nothing 0.01%
#
#   Three claims, and the third is the one that proves it is geometry rather than a property of the
#   ground: the masks are non-empty over relief, they are two orders of magnitude away from "low
#   backscatter", and reversing the orbit swaps which slopes fold and which hide.
#
# STILL PENDING: the two figure tests above and mutation O (the backscatter stretch reverting to
# per-scene percentiles) both need object storage, which was not running when this was recorded.
