"""Finds where radar backscatter rose or fell between two dates, keeping the two directions apart because they are different physics.

what  : `SarChangeResult` and `detect_sar_change()`. The `sar-change` model id: deterministic, no weights.
where : S13 for a radar pair. Takes two `SarPreprocessingResult`s from the 1.3 chain - already calibrated,
        filtered and terrain-corrected, with their layover and shadow masks - and 1.11 joins its output
        with the optical detector's at S15.
how   : Log-ratio on linear power (`math/log_ratio.py`) at a fixed dB threshold (`constants/change.py`).
        Ground either date could not see - layover, shadow, nodata - is unobserved in the result, never
        "unchanged": the 1.3 distinction between *radar saw nothing* and *radar could not see* is the
        whole reason those masks were retained, and it is honoured here.

        Confidence is `None`. A threshold on a ratio has no probability to state; what the operator can
        judge is the ratio map itself, which travels in the result for exactly that.
"""

import asyncio
from dataclasses import dataclass

import numpy as np

from app.constants.change import SAR_LOG_RATIO_THRESHOLD_DECIBELS
from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.services.change_detection.math.change_statistics import change_fraction
from app.services.change_detection.math.log_ratio import log_ratio_decibels, threshold_log_ratio
from app.services.preprocessing.sar_calibration import SarPreprocessingResult


@dataclass(frozen=True, slots=True)
class SarChangeResult:
    """Where backscatter rose, where it fell, and the ratio both were cut from."""

    ratio_decibels: np.ndarray
    increase: np.ndarray
    decrease: np.ndarray
    observed: np.ndarray
    threshold_decibels: float
    model_id: ModelId
    model_version: str
    confidence: float | None

    @property
    def changed(self) -> np.ndarray:
        return self.increase | self.decrease

    @property
    def changed_fraction(self) -> float:
        return change_fraction(self.changed, self.observed)


async def detect_sar_change(
    before: SarPreprocessingResult,
    after: SarPreprocessingResult,
    *,
    threshold_decibels: float = SAR_LOG_RATIO_THRESHOLD_DECIBELS,
) -> SarChangeResult:
    """Log-ratio change between two preprocessed dates of one polarisation, on one grid."""
    if before.polarisation is not after.polarisation:
        raise ValueError(
            f"Both dates must be one polarisation; got {before.polarisation.value} and {after.polarisation.value}."
        )
    ratio = await asyncio.to_thread(log_ratio_decibels, before.terrain_corrected_power, after.terrain_corrected_power)
    unseen = before.obscured_mask | after.obscured_mask
    ratio[unseen] = np.nan
    increase, decrease = await asyncio.to_thread(threshold_log_ratio, ratio, threshold_decibels)
    record = FLEET[ModelId.SAR_CHANGE]
    return SarChangeResult(
        ratio_decibels=ratio,
        increase=increase,
        decrease=decrease,
        observed=np.isfinite(ratio),
        threshold_decibels=threshold_decibels,
        model_id=record.model_id,
        model_version=record.version,
        confidence=None,
    )
