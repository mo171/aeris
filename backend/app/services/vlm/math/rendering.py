"""Turns Sentinel-2 reflectance and Sentinel-1 backscatter into the 8-bit pictures the VLM is trained and served on - one fixed stretch each.

what  : `render_s2_true_colour(b04, b03, b02)` and `render_s1_false_colour(vv, vh)`, both (H, W, 3) uint8.
where : `training/vlm/prepare_bigearthnet_txt.py` at training time and the S14 services at inference -
        one module, so the two cannot drift. Sync; callers use `asyncio.to_thread`.
how   : Fixed stretches, never per-image percentiles: a percentile stretch makes a uniform field of wheat
        look like a mosaic and a cloudy patch look clear, and it makes the same ground render differently
        on two dates. The windows are constants (`color_ramps.TRUE_COLOR_REFLECTANCE_DOMAIN`,
        `preprocessing.SAR_FALSE_COLOUR_DOMAINS`). S1 is taken in dB, converted from linear sigma-0 when
        the caller says it is linear; BigEarthNet v2.0 stores dB already.
"""

import numpy as np

from app.constants.color_ramps import TRUE_COLOR_GAMMA, TRUE_COLOR_REFLECTANCE_DOMAIN
from app.constants.preprocessing import SAR_FALSE_COLOUR_DOMAINS

S2_REFLECTANCE_WINDOW = TRUE_COLOR_REFLECTANCE_DOMAIN
S1_VV_DECIBEL_WINDOW, S1_VH_DECIBEL_WINDOW, S1_RATIO_DECIBEL_WINDOW = SAR_FALSE_COLOUR_DOMAINS
LINEAR_FLOOR = 1e-6


def _stretch(values: np.ndarray, window: tuple[float, float], gamma: float = 1.0) -> np.ndarray:
    low, high = window
    scaled = np.clip(np.nan_to_num((np.asarray(values, dtype=np.float32) - low) / (high - low), nan=0.0), 0.0, 1.0)
    return (scaled**gamma * 255.0).round().astype(np.uint8)


def render_s2_true_colour(b04: np.ndarray, b03: np.ndarray, b02: np.ndarray) -> np.ndarray:
    return np.stack([_stretch(band, S2_REFLECTANCE_WINDOW, TRUE_COLOR_GAMMA) for band in (b04, b03, b02)], axis=-1)


def to_decibels(linear: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(np.asarray(linear, dtype=np.float32), LINEAR_FLOOR))


def render_s1_false_colour(vv: np.ndarray, vh: np.ndarray, *, already_decibels: bool = False) -> np.ndarray:
    vv_db = np.asarray(vv, dtype=np.float32) if already_decibels else to_decibels(vv)
    vh_db = np.asarray(vh, dtype=np.float32) if already_decibels else to_decibels(vh)
    return np.stack(
        [_stretch(vv_db, S1_VV_DECIBEL_WINDOW), _stretch(vh_db, S1_VH_DECIBEL_WINDOW), _stretch(vv_db - vh_db, S1_RATIO_DECIBEL_WINDOW)],
        axis=-1,
    )
