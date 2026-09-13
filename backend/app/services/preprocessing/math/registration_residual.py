"""Measures co-registration consistency from local phase-correlation translations.

what  : `RegistrationMeasurement`, `measure_registration_residual`, `global_translation`.
where : Called by ``coregistration.py`` before any temporal comparison proceeds.
how   : **Pure, sync, NumPy only.** A global shift can look convincing while a warped or mismatched pair is
        wrong locally, so each tile's translation is measured independently and the pair is judged by how
        the tiles agree about the median translation, in pixels of the analysis grid.

        **The residual is the median disagreement, not the root-mean-square** (1.10). A pair of dates
        that changed - which is the only kind a change detector is asked about - has tiles whose content
        is different ground: a building where there was a field. Phase correlation on such a tile locks
        onto the content and reports a translation that has nothing to do with geometry. The RMS of all
        tiles is dominated by those (measured on a LEVIR-CD pair: 32 px from a pair the dataset registered
        to about 2 px), so the statistic must be one a minority of changed tiles cannot move: the median
        absolute deviation about the median translation. A warp or a half-scene offset still moves it - a
        pair whose halves disagree by 5 px reports 2.5 px, not 0 - because geometry affects every tile and
        change affects a minority. Every tile's translation is kept so the caller can count how many agree
        with any translation to within its tolerance.

        `global_translation` is phase correlation over the whole frame: the stable majority of pixels sets
        the peak, so it survives appearance change that scatters the tiles (seasons, shadows, a third of
        the ground rebuilt). Measured on sixty LEVIR-CD pairs: the tile majority agreed on 14, the global
        peak with a quarter of the tiles behind it on 32, and neither admitted a single one of forty pairs
        offset on purpose by 25-30 px. `coregistration.py` is where the two are combined into a gate.

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
    # The median of each tile's distance from the median translation: what at least half the tiles agree to.
    residual_pixels: float
    valid_tile_count: int
    # Every tile's (row, column) translation. Empty only in a hand-built record.
    tile_shifts_pixels: tuple[tuple[float, float], ...] = ()

    @property
    def shift_magnitude_pixels(self) -> float:
        """How far the whole pair is offset: the systematic misregistration the residual does not see."""
        return float(np.hypot(self.row_shift_pixels, self.column_shift_pixels))

    def agreeing_fraction(self, within_pixels: float, translation: tuple[float, float] | None = None) -> float:
        """The share of tiles whose translation lies within `within_pixels` of `translation` (the median by default)."""
        if not self.tile_shifts_pixels:
            return 0.0
        shifts = np.asarray(self.tile_shifts_pixels, dtype=np.float64)
        centre = np.asarray(translation if translation is not None else (self.row_shift_pixels, self.column_shift_pixels))
        return float(np.mean(np.sqrt(((shifts - centre) ** 2).sum(axis=1)) <= within_pixels))


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
    deviations = np.sqrt(np.sum((measured - median) ** 2, axis=1))
    return RegistrationMeasurement(
        row_shift_pixels=float(median[0]),
        column_shift_pixels=float(median[1]),
        residual_pixels=float(np.median(deviations)),
        valid_tile_count=len(shifts),
        tile_shifts_pixels=tuple((float(row), float(column)) for row, column in measured),
    )


def global_translation(reference: np.ndarray, moving: np.ndarray) -> tuple[float, float]:
    """The (row, column) translation of the whole frame by phase correlation, nodata filled with the mean."""
    if reference.shape != moving.shape or reference.ndim != 2:
        raise ValueError("registration inputs must be same-shaped two-dimensional arrays")
    valid = np.isfinite(reference) & np.isfinite(moving)
    if not valid.any():
        raise ValueError("registration needs some pixels both dates observed")
    left = _fill_with_mean(reference, valid)
    right = _fill_with_mean(moving, valid)
    if left.std() == 0.0 or right.std() == 0.0:
        raise ValueError("registration needs texture on both dates")
    shift, _, _ = phase_cross_correlation(left, right, upsample_factor=10)
    return float(shift[0]), float(shift[1])


def _fill_with_mean(tile: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Replace invalid pixels with the tile's own mean, leaving no edge for the correlator to find."""
    values = tile.astype(np.float64, copy=False)
    if valid.all():
        return values
    return np.where(valid, values, values[valid].mean())
