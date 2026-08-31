"""Decides whether a raster is worth analysing at all, by measuring the things that make a confident answer wrong.

what  : `BandStatistics`, `measure_band()`, `nodata_fraction()`, `distinct_value_fraction()` and
        `reflectance_out_of_range_fraction()`.
where : Called by `services/imagery/validation.py` (S4-S5) through `asyncio.to_thread`.
how   : **Pure, sync, NumPy only** - `architecture-context.md` §12. It is handed an array and returns
        numbers; it never opens a file, never decides policy, and never raises on a bad scene. Deciding
        what to *do* about 70% cloud is the service's job, and keeping that out of here is what makes
        these functions testable against arrays whose answers are known by construction.

        **Nodata is never zero** (§8 rule 4), and this file is where that rule is actually implemented.
        Zero is a legitimate reflectance - deep water in the near infrared is near zero - so a nodata
        fraction computed as `(array == 0).mean()` reports every lake as missing data and refuses a
        perfectly good scene. The mask comes from the raster's declared nodata value or from NaN, never
        from a value that looks empty.

        **Every statistic is computed over the valid pixels only.** A mean that includes nodata is a mean
        of the data and the absence of data, which is not a quantity. This is the specific way a
        "confident wrong number" gets produced here, and it is the reason `BandStatistics` carries
        `valid_pixel_count` alongside every figure - so a caller can see what the numbers were computed
        over rather than assuming.
"""

from dataclasses import dataclass

import numpy as np

from app.constants.raster import REFLECTANCE_VALID_RANGE


@dataclass(frozen=True, slots=True)
class BandStatistics:
    """What one band looks like, measured over its valid pixels.

    `valid_pixel_count` is not bookkeeping. Every other number here is computed over exactly those pixels,
    and a caller that reads `mean` without reading how many pixels it covers can quote a figure describing
    3% of a scene as though it described the scene.
    """

    total_pixel_count: int
    valid_pixel_count: int

    minimum: float
    maximum: float
    mean: float
    standard_deviation: float

    # Percentiles rather than min/max for display stretching: a single hot pixel sets the maximum and
    # collapses the visible range of everything else. 2nd and 98th are the conventional robust bounds.
    percentile_2: float
    percentile_98: float

    # How much of the raster carries no data. The first thing S4 refuses on.
    nodata_fraction: float

    # How many distinct valid values the band holds. **A count, not a fraction**: a constant raster has
    # exactly one whatever its size, whereas `distinct / valid` is `1 / N` and therefore means something
    # different at every resolution.
    distinct_value_count: int

    # Kept alongside as a cheap information measure - useful for ranking scenes, never for a threshold.
    distinct_value_fraction: float

    @property
    def is_empty(self) -> bool:
        """True when nothing valid was measured. Every other field is meaningless in that case."""
        return self.valid_pixel_count == 0


def valid_mask(array: np.ndarray, nodata: float | None) -> np.ndarray:
    """Which pixels carry real data.

    **Not `array != 0`.** Zero is a legitimate reflectance value - deep water in the near infrared reads
    near zero - so treating it as missing marks every lake as nodata and refuses a good scene. The mask
    comes from the declared nodata value, plus NaN, which is what a float raster uses (§8 rule 4).
    """
    finite = np.isfinite(array)
    if nodata is None or (isinstance(nodata, float) and np.isnan(nodata)):
        return finite
    return finite & (array != nodata)


def nodata_fraction(array: np.ndarray, nodata: float | None) -> float:
    """The fraction of pixels carrying no data, in [0, 1]."""
    if array.size == 0:
        return 1.0
    return float(1.0 - valid_mask(array, nodata).mean())


def distinct_value_fraction(array: np.ndarray, nodata: float | None) -> float:
    """Distinct valid values divided by valid pixel count.

    A cheap check for a raster that carries no information: a failed download, a band read at the wrong
    index, or a constant fill. Such a raster opens cleanly, renders as a flat image, and produces an index
    map that is uniformly one value - which looks like a finding rather than a fault.
    """
    mask = valid_mask(array, nodata)
    valid_count = int(mask.sum())
    if valid_count == 0:
        return 0.0
    return float(np.unique(array[mask]).size / valid_count)


def reflectance_out_of_range_fraction(array: np.ndarray, nodata: float | None) -> float:
    """How much of a *scaled reflectance* array falls outside plausible bounds.

    The check that catches a scaling mistake, which is the highest-consequence quiet failure in this
    pipeline: applying the L2A offset twice, or not at all, produces an array that is entirely finite,
    entirely plausible-looking, and shifted. Measured on a real scene, forgetting the offset moved the
    vegetated fraction by 13.7 points with no error anywhere.

    Returns a fraction rather than a boolean so the caller decides the threshold - the same separation of
    measurement from policy the rest of this module keeps.
    """
    mask = valid_mask(array, nodata)
    valid_count = int(mask.sum())
    if valid_count == 0:
        return 0.0

    low, high = REFLECTANCE_VALID_RANGE
    values = array[mask]
    return float(((values < low) | (values > high)).sum() / valid_count)


def measure_band(array: np.ndarray, nodata: float | None) -> BandStatistics:
    """Every statistic for one band, in a single pass over the valid pixels.

    One function rather than several because each of these would otherwise recompute the same mask, and on
    a decimated 4-megapixel sample that is four unnecessary passes. The mask is the expensive part.
    """
    mask = valid_mask(array, nodata)
    valid = array[mask]
    total = int(array.size)
    valid_count = int(valid.size)

    if valid_count == 0:
        # Every figure would be a NaN produced by an empty reduction, and NumPy would warn on each one.
        # Returning explicit zeros with `valid_pixel_count == 0` says "nothing was measured" rather than
        # "the measurements are NaN", which a caller can distinguish.
        return BandStatistics(
            total_pixel_count=total,
            valid_pixel_count=0,
            minimum=0.0, maximum=0.0, mean=0.0, standard_deviation=0.0,
            percentile_2=0.0, percentile_98=0.0,
            nodata_fraction=1.0,
            distinct_value_count=0,
            distinct_value_fraction=0.0,
        )

    as_float = valid.astype(np.float64, copy=False)
    low, high = np.percentile(as_float, [2.0, 98.0])
    distinct = int(np.unique(valid).size)

    return BandStatistics(
        total_pixel_count=total,
        valid_pixel_count=valid_count,
        minimum=float(as_float.min()),
        maximum=float(as_float.max()),
        mean=float(as_float.mean()),
        standard_deviation=float(as_float.std()),
        percentile_2=float(low),
        percentile_98=float(high),
        nodata_fraction=float(1.0 - valid_count / total),
        distinct_value_count=distinct,
        distinct_value_fraction=float(distinct / valid_count),
    )


def decimation_step_for(*, width: int, height: int, maximum_pixels: int) -> int:
    """How much to decimate a read so it stays under a pixel budget.

    A full Sentinel-2 10 m band is 10980x10980 - 120 megapixels, 240 MB as uint16 - and reading all of it
    to answer "is this mostly nodata" is minutes of I/O for a number that a regular sample answers to
    within a fraction of a percent.

    **Regular decimation, not random sampling.** Both give a good estimate; only one gives the same answer
    twice. A quality report that varies between runs is one nobody can use to decide whether a scene
    changed or the measurement did.
    """
    if maximum_pixels <= 0:
        raise ValueError(f"maximum_pixels must be positive, got {maximum_pixels}")
    total = width * height
    if total <= maximum_pixels:
        return 1
    return int(np.ceil(np.sqrt(total / maximum_pixels)))
