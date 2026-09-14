"""Optical water and built-up measurements from masked L2A reflectance."""

from dataclasses import dataclass

import numpy as np

MNDWI_WATER_THRESHOLD = 0.15
NDBI_BUILT_UP_THRESHOLD = 0.05
INDEX_EPSILON = 1e-6
MINIMUM_INDEX_RANGE = 0.02


@dataclass(frozen=True, slots=True)
class OpticalLandcoverMasks:
    water: np.ndarray
    built_up: np.ndarray
    observed: np.ndarray
    mndwi: np.ndarray
    ndbi: np.ndarray
    water_confidence: float | None
    built_up_confidence: float | None
    informative: bool


def optical_landcover_masks(
    green: np.ndarray,
    nir: np.ndarray,
    swir: np.ndarray,
    observed: np.ndarray,
    *,
    minimum_samples: int = 64,
) -> OpticalLandcoverMasks:
    """Measure water and built-up signatures only where all inputs were observed."""
    _require_same_shape(green, nir, swir, observed)
    valid = observed.astype(bool) & np.isfinite(green) & np.isfinite(nir) & np.isfinite(swir)
    mndwi = _normalised_difference(green, swir, valid)
    ndbi = _normalised_difference(swir, nir, valid)
    water = valid & (mndwi > MNDWI_WATER_THRESHOLD) & (ndbi < 0.0)
    built_up = valid & (ndbi > NDBI_BUILT_UP_THRESHOLD) & (mndwi < MNDWI_WATER_THRESHOLD)
    informative = _informative(mndwi, valid, minimum_samples) and _informative(ndbi, valid, minimum_samples)
    return OpticalLandcoverMasks(
        water=water,
        built_up=built_up,
        observed=valid,
        mndwi=mndwi,
        ndbi=ndbi,
        water_confidence=_margin_confidence(mndwi[water], MNDWI_WATER_THRESHOLD, 1.0),
        built_up_confidence=_margin_confidence(ndbi[built_up], NDBI_BUILT_UP_THRESHOLD, 1.0),
        informative=informative,
    )


def _normalised_difference(left: np.ndarray, right: np.ndarray, valid: np.ndarray) -> np.ndarray:
    denominator = left.astype(np.float32) + right.astype(np.float32)
    usable = valid & (np.abs(denominator) > INDEX_EPSILON)
    result = np.full(left.shape, np.nan, dtype=np.float32)
    result[usable] = (left[usable] - right[usable]) / denominator[usable]
    return result


def _informative(values: np.ndarray, valid: np.ndarray, minimum_samples: int) -> bool:
    finite = values[valid & np.isfinite(values)]
    return finite.size >= minimum_samples and float(np.ptp(finite)) >= MINIMUM_INDEX_RANGE


def _margin_confidence(values: np.ndarray, threshold: float, ceiling: float) -> float | None:
    if values.size == 0:
        return None
    margins = np.clip((values - threshold) / max(ceiling - threshold, INDEX_EPSILON), 0.0, 1.0)
    return float(np.clip(0.5 + 0.5 * np.mean(margins), 0.0, 1.0))


def _require_same_shape(*arrays: np.ndarray) -> None:
    shapes = {array.shape for array in arrays}
    if len(shapes) != 1:
        raise ValueError(f"Cross-modal optical arrays must share one grid, got {sorted(shapes)}.")
