"""Decides which values a colour ramp is spread across, which is the single choice that most changes what a figure appears to say.

what  : `StretchMethod`, `StretchBounds`, `compute_stretch()` and `apply_stretch()`.
where : Called by `services/rendering/figures.py` through `asyncio.to_thread`. The bounds it returns are
        recorded verbatim in every `figure-ready` event's `renderSpec`.
how   : **Pure, sync, NumPy only** - `architecture-context.md` §12.

        This is the file `architecture-context.md` §8 rule 13 is about: *"the colour ramp and the stretch
        bounds decide what the operator - and the VLM at S14 - actually sees: widen a stretch and a drought
        disappears, narrow it and healthy crop looks stressed."* A stretch is not a display preference. It
        is a claim about which differences matter, made silently, in a picture the vision-language model
        will later be asked to describe.

        So three methods, and the choice between them is the caller's and is recorded:

        **`FIXED`** - the domain comes from the quantity, not the data. Every NDVI is drawn over [-1, 1].
        This is the only method under which two figures are comparable, and it is the default for anything
        with fixed units, because the alternative is subtly worse in the most common case: stretch each
        week's NDVI to its own extremes and every image looks equally varied, which hides exactly the
        change the operator is looking for.

        **`PERCENTILE`** - 2nd to 98th. For imagery with no natural domain, where min-max would be set by
        a single hot pixel. Measured on a real Sentinel-2 band: min/max 252-15747 against p2/p98
        1108-3276, so min-max compresses the entire visible scene into a fifth of the ramp.

        **`MIN_MAX`** - the full observed range. Honest about outliers and almost always the wrong choice
        for display; kept because a diagnostic figure sometimes needs to show that the outlier exists.

        Nodata never participates. A stretch computed over NaN is NaN, and a stretch computed with nodata
        coerced to zero is pulled towards zero by however much of the scene is empty (§8 rule 4).
"""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class StretchMethod(StrEnum):
    """How the display range is chosen. Recorded in `renderSpec` so a figure can be reproduced."""

    FIXED = "fixed"
    PERCENTILE = "percentile"
    MIN_MAX = "min-max"


@dataclass(frozen=True, slots=True)
class StretchBounds:
    """The range a ramp is spread across, and how it was arrived at.

    Carries the method as well as the numbers because the two answer different questions months later:
    the numbers say what was drawn, and the method says whether redrawing the same scene would produce
    them again. A percentile stretch is data-dependent; a fixed one is not.
    """

    minimum: float
    maximum: float
    method: StretchMethod

    @property
    def span(self) -> float:
        return self.maximum - self.minimum

    def as_render_spec(self) -> dict[str, float | str]:
        """The `renderSpec.stretch` fragment of a `figure-ready` event."""
        return {"min": self.minimum, "max": self.maximum, "method": self.method.value}


def compute_stretch(
    array: np.ndarray,
    *,
    method: StretchMethod,
    fixed_domain: tuple[float, float] | None = None,
    lower_percentile: float = 2.0,
    upper_percentile: float = 98.0,
) -> StretchBounds:
    """Work out the display range for one array.

    Raises when `FIXED` is asked for without a domain, rather than quietly falling back to percentiles -
    a figure whose caller believed it was comparable and got a data-dependent stretch is precisely the
    silent failure this module exists to prevent.
    """
    if method is StretchMethod.FIXED:
        if fixed_domain is None:
            raise ValueError(
                "A fixed stretch needs a domain. Falling back to the data's own range would produce a "
                "figure the caller believes is comparable with others and is not."
            )
        return StretchBounds(float(fixed_domain[0]), float(fixed_domain[1]), StretchMethod.FIXED)

    finite = array[np.isfinite(array)]
    if finite.size == 0:
        # Nothing to measure. A degenerate but valid range, so downstream normalisation divides by 1 and
        # produces a uniformly transparent image rather than raising inside a renderer.
        return StretchBounds(0.0, 1.0, method)

    if method is StretchMethod.PERCENTILE:
        low, high = np.percentile(finite, [lower_percentile, upper_percentile])
    else:
        low, high = finite.min(), finite.max()

    # A constant array gives low == high, and normalising by a zero span divides by zero. Widened by a
    # hair so the figure renders as a single flat colour, which is the honest depiction of constant data.
    if float(high) - float(low) < 1e-12:
        return StretchBounds(float(low), float(low) + 1e-12, method)

    return StretchBounds(float(low), float(high), method)


def apply_stretch(array: np.ndarray, bounds: StretchBounds) -> np.ndarray:
    """Map an array onto [0, 1] using `bounds`, keeping NaN as NaN.

    Values outside the bounds are **clipped**, and that is correct here in a way it never is in `math/`
    arithmetic: this is the last step before pixels, and a value beyond the ramp has no colour to be
    given. What must not happen - and does not - is the clipped value flowing back into a statistic.
    The array returned here is for display only and is never measured.
    """
    with np.errstate(invalid="ignore"):
        normalised = (array.astype(np.float32) - bounds.minimum) / bounds.span
        return np.clip(normalised, 0.0, 1.0)
