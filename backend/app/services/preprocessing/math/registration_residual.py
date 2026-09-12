"""Measures co-registration consistency from local phase-correlation translations.

what  : `RegistrationMeasurement` and `measure_registration_residual`.
where : Called by ``coregistration.py`` before any temporal comparison proceeds.
how   : **Pure, sync, NumPy only.** A global shift can look convincing while a warped or mismatched pair is
        wrong locally, so the residual is the RMS disagreement of independent per-tile shifts about their
        median, in pixels of the analysis grid.

        Invalid pixels are filled with the tile mean, never zero. Zero-filling paints a hard edge along the
        nodata boundary, phase correlation locks onto that edge instead of the ground, and the tile reports
        a shift of exactly (0, 0) - indistinguishable from perfect registration. Measured on the gate scene,
        which is 1.3% nodata: zero-fill reported 1.02 px on a pair registered to 0.00 px and the refusal
        fired on good data.
"""

from dataclasses import dataclass

import numpy as np
from skimage.registration import phase_cross_correlation


@dataclass(frozen=True, slots=True)
class RegistrationMeasurement:
    """The median translation and its local-consistency residual, all in pixels."""

    row_shift_pixels: float
    column_shift_pixels: float
    residual_pixels: float
    valid_tile_count: int


def measure_registration_residual(
    reference: np.ndarray,
    moving: np.ndarray,
    *,
    tile_size: int,
    minimum_valid_tiles: int,
    minimum_valid_fraction: float = 0.8,
) -> RegistrationMeasurement:
    """Estimate local translations and return their disagreement around the median translation."""
    if reference.shape != moving.shape or reference.ndim != 2:
        raise ValueError("registration inputs must be same-shaped two-dimensional arrays")
    if tile_size < 8 or minimum_valid_tiles < 1:
        raise ValueError("tile size must be at least 8 and minimum valid tiles must be positive")

    shifts: list[np.ndarray] = []
    for row in range(0, reference.shape[0] - tile_size + 1, tile_size):
        for column in range(0, reference.shape[1] - tile_size + 1, tile_size):
            window = (slice(row, row + tile_size), slice(column, column + tile_size))
            valid = np.isfinite(reference[window]) & np.isfinite(moving[window])
            if valid.mean() < minimum_valid_fraction:
                continue
            left = _fill_with_mean(reference[window], valid)
            right = _fill_with_mean(moving[window], valid)
            if left.std() == 0.0 or right.std() == 0.0:
                continue
            shift, _, _ = phase_cross_correlation(left, right, upsample_factor=10)
            shifts.append(shift[:2])

    if len(shifts) < minimum_valid_tiles:
        raise ValueError(
            f"registration needs {minimum_valid_tiles} textured valid tiles, but only {len(shifts)} were usable"
        )

    measured = np.asarray(shifts, dtype=np.float64)
    median = np.median(measured, axis=0)
    residual = float(np.sqrt(np.mean(np.sum((measured - median) ** 2, axis=1))))
    return RegistrationMeasurement(
        row_shift_pixels=float(median[0]),
        column_shift_pixels=float(median[1]),
        residual_pixels=residual,
        valid_tile_count=len(shifts),
    )


def _fill_with_mean(tile: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Replace invalid pixels with the tile's own mean, leaving no edge for the correlator to find."""
    values = tile.astype(np.float64, copy=False)
    if valid.all():
        return values
    return np.where(valid, values, values[valid].mean())
