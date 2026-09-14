"""Physically interpretable dual-polarisation SAR masks on linear RTC power."""

from dataclasses import dataclass

import numpy as np

POWER_EPSILON = 1e-8
WATER_VV_MAX_DB = -17.0
WATER_VH_MAX_DB = -22.0
BUILT_UP_VV_MIN_DB = -8.0
BUILT_UP_VH_MIN_DB = -15.0
MINIMUM_DYNAMIC_RANGE_DB = 3.0


@dataclass(frozen=True, slots=True)
class SarLandcoverMasks:
    water: np.ndarray
    built_up: np.ndarray
    observed: np.ndarray
    vv_decibels: np.ndarray
    vh_decibels: np.ndarray
    water_confidence: float | None
    built_up_confidence: float | None
    informative: bool


def sar_landcover_masks(
    vv_power: np.ndarray,
    vh_power: np.ndarray,
    observed: np.ndarray,
    *,
    minimum_samples: int = 64,
) -> SarLandcoverMasks:
    """Classify smooth dark water and strong rough returns without treating darkness as nodata."""
    shapes = {vv_power.shape, vh_power.shape, observed.shape}
    if len(shapes) != 1:
        raise ValueError(f"Cross-modal SAR arrays must share one grid, got {sorted(shapes)}.")
    valid = observed.astype(bool) & np.isfinite(vv_power) & np.isfinite(vh_power) & (vv_power >= 0) & (vh_power >= 0)
    vv_db = _decibels(vv_power, valid)
    vh_db = _decibels(vh_power, valid)
    water = valid & (vv_db <= WATER_VV_MAX_DB) & (vh_db <= WATER_VH_MAX_DB)
    built_up = valid & (vv_db >= BUILT_UP_VV_MIN_DB) & (vh_db >= BUILT_UP_VH_MIN_DB)
    finite_vv = vv_db[valid]
    finite_vh = vh_db[valid]
    informative = (
        finite_vv.size >= minimum_samples
        and float(np.ptp(finite_vv)) >= MINIMUM_DYNAMIC_RANGE_DB
        and float(np.ptp(finite_vh)) >= MINIMUM_DYNAMIC_RANGE_DB
    )
    return SarLandcoverMasks(
        water=water,
        built_up=built_up,
        observed=valid,
        vv_decibels=vv_db,
        vh_decibels=vh_db,
        water_confidence=_confidence(WATER_VV_MAX_DB - vv_db[water]),
        built_up_confidence=_confidence(vv_db[built_up] - BUILT_UP_VV_MIN_DB),
        informative=informative,
    )


def _decibels(power: np.ndarray, valid: np.ndarray) -> np.ndarray:
    result = np.full(power.shape, np.nan, dtype=np.float32)
    result[valid] = 10.0 * np.log10(np.maximum(power[valid], POWER_EPSILON))
    return result


def _confidence(margin_db: np.ndarray) -> float | None:
    if margin_db.size == 0:
        return None
    return float(np.clip(0.5 + np.mean(np.clip(margin_db / 12.0, 0.0, 1.0)) * 0.5, 0.0, 1.0))
