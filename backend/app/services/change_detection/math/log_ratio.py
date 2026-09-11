"""The log-ratio change detector for calibrated SAR backscatter - the deterministic half of S13's change models.

what  : `log_ratio_decibels()` - `10 log10(after / before)` over linear power; `threshold_log_ratio()` -
        the increase and decrease masks at a stated dB threshold.
where : Called by `services/change_detection/sar_change.py` through `asyncio.to_thread`, on the
        terrain-corrected linear power the 1.3 SAR chain produces. The `sar-change` model id.
how   : **Pure, sync, NumPy.** A ratio rather than a difference because speckle is multiplicative
        (`preprocessing/math/speckle_filters.py`): dividing two dates cancels the terrain and incidence
        terms that a subtraction leaves in, and the log makes a doubling and a halving the same distance
        from zero. Dekker (1998) is the standard reference; the method predates it.

        The sign carries the physics. An *increase* in backscatter is a rougher or wetter surface - new
        construction's double bounce, a field after ploughing; a *decrease* is smoother or drier - open
        water where there was ground, a cleared forest. The two are returned separately because they are
        different claims, and a magnitude-only mask would merge a flood with a building site.

        Unobserved pixels - NaN in either date, or radar shadow and layover in the retained masks - are
        NaN in the ratio and false in both masks, never zero: zero dB is "unchanged", and that is a claim.
"""

import numpy as np

from app.constants.preprocessing import SAR_POWER_EPSILON


def log_ratio_decibels(before_power: np.ndarray, after_power: np.ndarray) -> np.ndarray:
    """`10 log10(after / before)` in decibels, NaN wherever either input is unobserved or non-positive."""
    if before_power.shape != after_power.shape:
        raise ValueError(f"Dates must share a grid; got {before_power.shape} and {after_power.shape}.")
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = 10.0 * np.log10(after_power / before_power)
    unphysical = ~(np.isfinite(before_power) & np.isfinite(after_power))
    unphysical |= (before_power <= SAR_POWER_EPSILON) | (after_power <= SAR_POWER_EPSILON)
    ratio = ratio.astype(np.float32)
    ratio[unphysical] = np.nan
    return ratio


def threshold_log_ratio(ratio_decibels: np.ndarray, threshold_decibels: float) -> tuple[np.ndarray, np.ndarray]:
    """(increase, decrease): backscatter rose by at least the threshold, or fell by at least it."""
    if threshold_decibels <= 0.0:
        raise ValueError(f"A log-ratio threshold is a positive number of decibels; got {threshold_decibels}.")
    observed = np.isfinite(ratio_decibels)
    with np.errstate(invalid="ignore"):
        increase = observed & (ratio_decibels >= threshold_decibels)
        decrease = observed & (ratio_decibels <= -threshold_decibels)
    return increase, decrease
