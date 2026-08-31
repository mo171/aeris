"""Applies the Lee adaptive speckle filter in linear SAR power.

what  : `lee_filter`, the multiplicative-speckle local-statistics filter.
where : Called by ``sar_calibration.py`` between radiometric calibration and terrain correction.
how   : **Pure, sync, NumPy only** - `architecture-context.md` §12. NaN nodata is preserved, so terrain the
        radar never saw stays unseen rather than being filled from its neighbours.

        **Speckle is multiplicative, and that is not a detail of the formula - it is the formula.** Under
        fully developed speckle the standard deviation of a region scales with its mean, so a bright field
        and a dark lake with identical speckle statistics have local variances differing by two orders of
        magnitude. A filter that compares local variance against one global noise variance therefore reads
        the lake as quiet and smooths it flat, while leaving the field almost untouched.

        Measured on this exact code before it was fixed: two regions of one synthetic scene, both single-
        look with ENL 1.0, differing only in brightness (0.05 against 1.0). The additive-noise form smoothed
        the dark region 25x and the bright region 1.4x. Downstream that is not cosmetic - a change detector
        comparing two dates sees variance collapse over water and reports it as a finding.

        So the criterion is the *coefficient of variation*, which is scale-free:

            Cu^2 = 1 / L                  speckle's own variation at L looks
            Ci^2 = var_local / mean_local^2
            W    = clip(1 - Cu^2 / Ci^2, 0, 1)
            out  = mean_local + W * (x - mean_local)

        Homogeneous ground gives Ci^2 -> Cu^2, so W -> 0 and the pixel becomes its local mean. An edge or a
        point target gives Ci^2 >> Cu^2, so W -> 1 and the pixel is left alone. This is Lee (1980), and it
        is what SNAP applies; the number of looks belongs to the product and is passed in rather than
        assumed, because it differs between GRD and RTC.
"""

import numpy as np
from scipy.ndimage import uniform_filter


def lee_filter(
    power: np.ndarray,
    *,
    window_size: int,
    number_of_looks: float,
    epsilon: float,
) -> np.ndarray:
    """Return a Lee-filtered power raster, preserving NaN nodata and total radiometry."""
    if power.ndim != 2:
        raise ValueError(f"SAR power must be two-dimensional, got {power.shape}")
    if window_size < 3 or window_size % 2 == 0:
        raise ValueError("Lee filter window size must be an odd integer of at least 3")
    if number_of_looks <= 0.0:
        raise ValueError("number of looks must be positive")
    if epsilon <= 0.0:
        raise ValueError("epsilon must be positive")

    # Negative power is unphysical in a calibrated product and is treated as unobserved rather than
    # clamped, so a corrupt band shows up as a hole instead of a plausible dark field.
    valid = np.isfinite(power) & (power >= 0.0)
    values = np.where(valid, power, 0.0).astype(np.float64, copy=False)
    weights = valid.astype(np.float64)

    # `uniform_filter` averages over the full window including the invalid pixels zeroed above, so each
    # sum is rescaled by how many of its neighbours were real. Without this the pixels beside a nodata
    # margin are pulled towards zero, which is §8 rule 4 broken quietly at the scene edge.
    neighbour_count = uniform_filter(weights, size=window_size, mode="nearest") * window_size**2
    divisor = np.maximum(neighbour_count, 1.0)
    mean = uniform_filter(values, size=window_size, mode="nearest") * window_size**2 / divisor
    mean_squared = uniform_filter(values**2, size=window_size, mode="nearest") * window_size**2 / divisor
    local_variance = np.maximum(mean_squared - mean**2, 0.0)

    speckle_variation = 1.0 / number_of_looks
    scene_variation = local_variance / np.maximum(mean**2, epsilon)
    weight = np.clip(1.0 - speckle_variation / np.maximum(scene_variation, epsilon), 0.0, 1.0)

    filtered = mean + weight * (values - mean)
    return np.where(valid, filtered, np.nan).astype(np.float32)
