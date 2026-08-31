"""Executes the fixed SAR preprocessing order: calibrate, speckle-filter, terrain-correct.

what  : `SarPreprocessingResult` and `preprocess_sar` - the SAR branch of Phase 1.3.
where : Called by `cli/preprocess.py` today and by the S10 graph node from Phase 1.8. Its dB output is what
        `rendering/figures.render_sar_backscatter` draws.
how   : Async orchestration only; every array operation is a `math/` kernel reached through
        `asyncio.to_thread` (`architecture-context.md` §11, §12).

        **The order is fixed and this file is where that is enforced** (§8 rule 7). Calibration turns
        instrument counts into a physical quantity, speckle filtering assumes that quantity is linear power,
        and terrain correction needs an unspeckled estimate to redistribute. Filtering before calibrating
        averages numbers that are not yet comparable; correcting before filtering pushes speckle through a
        geometric transform. Neither reorder raises - both produce a plausible raster - which is why the
        order lives in code rather than in a caller's memory.

        **Calibration is refusable and skippable, and both matter.** `calibration_factor=None` says the
        product arrived already in linear power - which is true of every RTC product, including the
        Sentinel-1 scenes this phase's gate runs on. Calibrating an already-calibrated raster does not fail;
        it returns the square of the truth, a raster that opens cleanly, renders convincingly and is wrong
        everywhere. That is the same failure §8 rule 5 names for optical DN, pointed at radar.

        dB exists only at the end, and only for display. Everything upstream of `backscatter_decibels` is
        linear power, because dB is logarithmic and a mean of logarithms is not the logarithm of the mean.
"""

import asyncio
from dataclasses import dataclass

import numpy as np

from app.constants.preprocessing import (
    LEE_FILTER_WINDOW_SIZE,
    SAR_POWER_EPSILON,
    SENTINEL1_IW_GRD_EQUIVALENT_LOOKS,
)
from app.constants.scenes import Polarisation
from app.services.preprocessing.math.speckle_filters import lee_filter
from app.services.preprocessing.math.terrain_flattening import TerrainCorrectionResult, terrain_flatten


@dataclass(frozen=True, slots=True)
class SarPreprocessingResult:
    """Corrected backscatter, every intermediate it passed through, and the visibility masks."""

    polarisation: Polarisation
    calibrated_power: np.ndarray
    filtered_power: np.ndarray
    terrain_corrected_power: np.ndarray
    backscatter_decibels: np.ndarray
    layover_mask: np.ndarray
    shadow_mask: np.ndarray
    local_incidence_degrees: np.ndarray

    @property
    def obscured_mask(self) -> np.ndarray:
        """Ground radar could not read, for either geometric reason. Not the same as low backscatter."""
        return self.layover_mask | self.shadow_mask

    @property
    def obscured_fraction(self) -> float:
        """The radar half of the frontend's `sensorRunSchema.obscuredFraction`.

        Reported even when it is zero, because "radar could see all of this" is a finding an operator
        needs in order to read an absence as evidence rather than as a blind spot.
        """
        return float(self.obscured_mask.mean())


async def preprocess_sar(
    observed: np.ndarray,
    elevation_metres: np.ndarray,
    *,
    polarisation: Polarisation,
    calibration_factor: float | None,
    incidence_angle_degrees: float,
    radar_azimuth_degrees: float,
    pixel_size_metres: float,
    number_of_looks: float = SENTINEL1_IW_GRD_EQUIVALENT_LOOKS,
    lee_window_size: int = LEE_FILTER_WINDOW_SIZE,
) -> SarPreprocessingResult:
    """S10: calibrate -> speckle filter -> terrain correct, retaining layover and shadow as masks.

    `observed` is digital numbers when `calibration_factor` is given, and linear power when it is `None`.
    """
    if polarisation is Polarisation.RATIO:
        raise ValueError(
            "A polarisation ratio is derived from two preprocessed bands, not preprocessed itself. "
            "Run VV and VH separately and form the ratio from the results."
        )
    if calibration_factor is not None and calibration_factor <= 0.0:
        raise ValueError("SAR calibration factor must be positive")

    calibrated = await asyncio.to_thread(_calibrate, observed, calibration_factor)
    filtered = await asyncio.to_thread(
        lee_filter,
        calibrated,
        window_size=lee_window_size,
        number_of_looks=number_of_looks,
        epsilon=SAR_POWER_EPSILON,
    )
    terrain: TerrainCorrectionResult = await asyncio.to_thread(
        terrain_flatten,
        filtered,
        elevation_metres,
        incidence_angle_degrees=incidence_angle_degrees,
        radar_azimuth_degrees=radar_azimuth_degrees,
        pixel_size_metres=pixel_size_metres,
        epsilon=SAR_POWER_EPSILON,
    )
    decibels = await asyncio.to_thread(_to_decibels, terrain.corrected_power)

    return SarPreprocessingResult(
        polarisation=polarisation,
        calibrated_power=calibrated,
        filtered_power=filtered,
        terrain_corrected_power=terrain.corrected_power,
        backscatter_decibels=decibels,
        layover_mask=terrain.layover_mask,
        shadow_mask=terrain.shadow_mask,
        local_incidence_degrees=terrain.local_incidence_degrees,
    )


def _calibrate(observed: np.ndarray, calibration_factor: float | None) -> np.ndarray:
    """Digital numbers to linear power, or a documented pass-through for an already-calibrated product."""
    values = observed.astype(np.float32, copy=False)
    if calibration_factor is None:
        # Negative power is unphysical, so an already-calibrated product carrying negatives is a wrong
        # nodata value rather than dark ground. Dropped here rather than clamped.
        return np.where(np.isfinite(values) & (values >= 0.0), values, np.nan).astype(np.float32)
    return np.where(np.isfinite(values), values**2 * calibration_factor, np.nan).astype(np.float32)


def _to_decibels(power: np.ndarray) -> np.ndarray:
    """Linear power to dB, for display only. Nodata stays nodata rather than becoming a very small number."""
    with np.errstate(divide="ignore", invalid="ignore"):
        decibels = 10.0 * np.log10(np.maximum(power, SAR_POWER_EPSILON))
    return np.where(np.isfinite(power), decibels, np.nan).astype(np.float32)
