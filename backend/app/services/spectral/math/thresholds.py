"""Turns an index array into a mask and a handful of numbers, with the unobserved pixels kept out of both.

what  : `within_range()` - the fixed cut-off that makes a mask; `otsu_threshold()` - the data-driven one;
        `summarise()` - the distribution an operator reads and the fraction in each interpretation band.
where : Called by the S15 node through `asyncio.to_thread`, with the ranges from `constants/spectral.py`.
how   : **NaN is never detected and never observed.** A masked pixel - cloud, shadow, nodata, an
        unphysical value - falls outside every range and outside every statistic. The alternative, where
        `nan > 0.2` is quietly `False` and the pixel counts as "not vegetated", is how an obscured field
        becomes a reported absence of vegetation. Every function here separates the two.

        Ranges are `[lower, upper)`, closed at the top of the domain so a value of exactly 1.0 has a band.
        That convention is `constants/spectral.py`'s, and it is stated once, here, rather than at each
        comparison.

        Otsu (1979) comes from scikit-image rather than being reimplemented. It assumes a bimodal
        histogram; on a scene that is all water or all canopy it returns a threshold that splits noise,
        and a caller that wants a data-driven cut-off must know that.
"""

from dataclasses import dataclass

import numpy as np
from skimage.filters import threshold_otsu

from app.constants.raster import MINIMUM_DISTINCT_VALUES
from app.constants.spectral import INDEX_DOMAIN, InterpretationBand


def within_range(index: np.ndarray, lower: float, upper: float) -> np.ndarray:
    """`lower <= value < upper`, inclusive at the top of the domain. NaN is `False`."""
    with np.errstate(invalid="ignore"):
        inside = (index >= lower) & ((index <= upper) if upper >= INDEX_DOMAIN[1] else (index < upper))
    return inside & np.isfinite(index)


def otsu_threshold(index: np.ndarray) -> float:
    """The cut-off that best separates a bimodal index into two classes. Otsu 1979."""
    observed = index[np.isfinite(index)]
    if np.unique(observed).size < MINIMUM_DISTINCT_VALUES:
        raise ValueError(
            "Otsu needs at least two distinct observed values; a constant array has no classes to separate."
        )
    return float(threshold_otsu(observed))


@dataclass(frozen=True, slots=True)
class IndexSummary:
    """What an index looks like over its observed pixels."""

    observed_count: int
    total_count: int
    mean: float
    median: float
    percentile_2: float
    percentile_98: float
    # Interpretation band label -> fraction of *observed* pixels inside it. Sums to 1 over a band set that
    # covers the domain, which is how a caller can tell the bands were contiguous.
    band_fractions: dict[str, float]

    @property
    def observed_fraction(self) -> float:
        return self.observed_count / self.total_count if self.total_count else 0.0


def summarise(index: np.ndarray, bands: tuple[InterpretationBand, ...]) -> IndexSummary:
    """Distribution statistics and the share of observed pixels in each interpretation band."""
    observed = index[np.isfinite(index)]
    if observed.size == 0:
        return IndexSummary(0, int(index.size), float("nan"), float("nan"), float("nan"), float("nan"),
                            {band.label: 0.0 for band in bands})

    percentile_2, median, percentile_98 = np.percentile(observed, (2, 50, 98))
    fractions = {
        band.label: float(within_range(observed, band.lower, band.upper).sum()) / observed.size
        for band in bands
    }
    return IndexSummary(
        observed_count=int(observed.size),
        total_count=int(index.size),
        mean=float(observed.mean()),
        median=float(median),
        percentile_2=float(percentile_2),
        percentile_98=float(percentile_98),
        band_fractions=fractions,
    )
