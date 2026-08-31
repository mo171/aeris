"""Computes normalised-difference indices, and refuses to return a value its own algebra says is impossible.

what  : `normalised_difference()` and `to_surface_reflectance()`.
where : Called by `cli/ingest.py` today and by Phase 1.4's index engine tomorrow, both through
        `asyncio.to_thread`. The engine will own the *registry* - which bands make an NDWI, what threshold
        means water - and will call this for the arithmetic itself.
how   : **Pure, sync, NumPy only** - `architecture-context.md` §12.

        This file exists because the first NDVI this pipeline produced ranged **[-337, +347]** over a real
        scene, against a mathematical range of [-1, +1]. It wrote a valid COG. It rendered as a plausible
        map. Only 0.055% of pixels were affected - few enough to miss by eye, and more than enough to set
        the colour scale of every figure drawn from the array, because a colour ramp is stretched to the
        extremes it is given.

        Two causes, both handled below.

        **Negative reflectance breaks the bound, and this was the actual cause.** `|a - b| <= |a + b|`
        holds only when `a` and `b` share a sign. Subtracting the L2A offset from a dark pixel - deep
        water, terrain shadow - gives a small *negative* reflectance, which is an atmospheric-correction
        artefact rather than a measurement. Where one band is negative and the other is not, the ratio is
        unbounded and physically meaningless.

        Measured on this scene: 0.52% of valid pixels have a negative reflectance in one band, and
        **100% of the out-of-range values came from exactly those pixels.** Masked, not clamped - a
        clamped zero is a number nobody measured and would be indistinguishable from real dark ground in
        every statistic afterwards (§8 rule 4).

        **The denominator also approaches zero.** `(a - b) / (a + b)` is unbounded as `a + b -> 0`, and
        guarding `denominator == 0` catches nothing because the problem is *near*-zero. Masked at
        `MINIMUM_INDEX_DENOMINATOR`. Raising that threshold was the first fix attempted and it did not
        work, which is what led to the diagnosis above.

        **Nodata treated as a number.** Sentinel-2 declares nodata as 0. Subtract the 1000 offset from a
        nodata pixel and it becomes -0.1 reflectance, which is a perfectly ordinary float that survives
        every subsequent operation (§8 rule 4). The mask is taken from the *raw* digital numbers, before
        any scaling, which is the only point at which nodata is still identifiable.

        **The post-condition is the part worth keeping.** A normalised difference is bounded by its own
        algebra, so a finite value outside [-1, 1] is not unusual data - it is a bug in this function, and
        it raises rather than returning it. That is the §8 rule the whole file serves: a confident wrong
        number is worse than an error.
"""

import numpy as np

from app.constants.raster import (
    MINIMUM_INDEX_DENOMINATOR,
    NORMALISED_INDEX_RANGE,
    REFLECTANCE_OFFSET,
    REFLECTANCE_SCALE,
)


def to_surface_reflectance(
    digital_numbers: np.ndarray,
    *,
    nodata: float | None,
    apply_offset: bool = True,
) -> np.ndarray:
    """Convert stored integers to surface reflectance, with nodata as NaN.

    `reflectance = (digital_number - offset) / scale`. The offset arrived with processing baseline 04.00
    and is zero before it, which is why it is a parameter rather than always applied - and why the caller
    has to know the baseline rather than guessing.

    Measured on a real scene: omitting the offset moves the vegetated fraction from 75.1% to 61.4%
    (`notebooks/02_data_exploration/01_sentinel2_l2a.ipynb`).

    **The nodata mask is taken here, from the raw integers.** It is the last moment nodata is
    identifiable: once the offset is subtracted, a nodata 0 becomes -0.1, which is an ordinary float that
    no downstream check can distinguish from a dark pixel.
    """
    as_float = digital_numbers.astype(np.float32, copy=True)

    if nodata is not None and not np.isnan(nodata):
        as_float[digital_numbers == nodata] = np.nan

    offset = REFLECTANCE_OFFSET if apply_offset else 0.0
    return (as_float - offset) / REFLECTANCE_SCALE


def normalised_difference(high: np.ndarray, low: np.ndarray) -> np.ndarray:
    """`(high - low) / (high + low)`, masked where the result would not be meaningful.

    NDVI is `normalised_difference(nir, red)`; NDWI is `normalised_difference(green, nir)`. The naming is
    positional rather than band-specific because the arithmetic is the same and only the bands differ -
    which is what keeps `math/` sensor-agnostic (`constants/raster.py`, `BandRole`).

    Returns NaN where either input is NaN, or where the denominator is too small for the ratio to mean
    anything. **Masked, not clipped**: a clipped value is a number nobody measured, and it would be
    indistinguishable from a real -1 in every statistic computed afterwards (§8 rule 4).

    Raises when a finite result escapes [-1, 1]. That cannot happen for real inputs, so if it does, this
    function is wrong and the caller must not write the array.
    """
    if high.shape != low.shape:
        raise ValueError(
            f"Bands must share a grid: got {high.shape} and {low.shape}. Bands at different resolutions "
            "have to be resampled onto one grid before any index is computed."
        )

    denominator = high + low
    with np.errstate(divide="ignore", invalid="ignore"):
        index = (high - low) / denominator

    # **The precondition of the [-1, 1] bound.** `|a - b| <= |a + b|` only when `a` and `b` share a sign;
    # a negative reflectance is an atmospheric-correction artefact over dark ground, not a measurement, and
    # the ratio there is unbounded and meaningless. Measured on a real scene: 0.52% of valid pixels, and
    # 100% of the out-of-range values.
    unphysical = (high < 0.0) | (low < 0.0)

    # `abs`, because the denominator may still be near zero from two very dark but positive bands. What
    # makes the ratio meaningless there is its magnitude, not its sign.
    with np.errstate(invalid="ignore"):
        too_small = ~np.isfinite(denominator) | (np.abs(denominator) < MINIMUM_INDEX_DENOMINATOR)

    index[unphysical | too_small] = np.nan

    _require_in_range(index)
    return index.astype(np.float32)


def _require_in_range(index: np.ndarray) -> None:
    """A normalised difference outside [-1, 1] is a bug here, not a finding in the data.

    Checked over the finite values only - NaN is the masked state and is expected everywhere the inputs
    were nodata or the denominator was too small.
    """
    finite = index[np.isfinite(index)]
    if finite.size == 0:
        return

    low, high = NORMALISED_INDEX_RANGE
    out_of_range = (finite < low) | (finite > high)
    if not out_of_range.any():
        return

    offenders = finite[out_of_range]
    raise ValueError(
        f"{out_of_range.sum():,} of {finite.size:,} values fall outside [{low}, {high}] "
        f"(range {offenders.min():.3f} to {offenders.max():.3f}). A normalised difference is bounded by "
        "its own algebra, so this is an arithmetic fault - most likely a denominator guard that is too "
        "small, or reflectance scaling applied twice."
    )
