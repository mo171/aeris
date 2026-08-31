"""Names every colour ramp a figure may be drawn with, because the ramp decides what the operator and the VLM actually see.

what  : `ColorRampId` - the eight ramps the frontend's `colorRampIdSchema` declares - the matplotlib
        colormap each maps onto, and the default stretch domain for the ones whose units are fixed.
where : Read by `services/rendering/math/color_ramps.py` (which turns a name into a lookup table) and by
        `services/rendering/figures.py` (which chooses one). Emitted on every `figure-ready` event, in both
        `legend.colorRamp` and `renderSpec.colorRamp`.
how   : **This vocabulary is the frontend's, not ours** (`api-contract.md` §0, §7). Phase 0.7 recorded
        `colorRampIdSchema` in `FRONTEND_ONLY_VOCABULARIES` as owed to this sub-phase; the values below
        are transcribed from it exactly, and `tests/contracts/test_shared_vocabularies.py` now pairs the
        two so they cannot drift.

        **Why a named ramp rather than a matplotlib name on the wire.** `architecture-context.md` §8 rule
        13: the ramp and the stretch decide what is seen - widen a stretch and a drought disappears,
        narrow it and healthy crop looks stressed. So the ramp is part of the evidence chain and has to
        mean the same thing to the frontend's legend component as it does to the renderer. `RdYlGn` is a
        matplotlib implementation detail that could be swapped; `index-vegetation` is a *commitment* that
        vegetation indices are always drawn red-to-green, in this product, everywhere.

        The frontend draws its own legends from these ids. Sending `viridis` would render a colourbar the
        frontend cannot label.
"""

from enum import StrEnum
from typing import Final


class ColorRampId(StrEnum):
    """The eight ramps this product draws with. Mirrors `colorRampIdSchema` on the frontend, exactly."""

    # Natural colour from red, green and blue. Not a ramp in the colormap sense - it is the absence of
    # one - and it is in this enum because `renderSpec.colorRamp` must record *something* for every figure.
    TRUE_COLOR = "true-color"

    # SAR backscatter in decibels. Grey because radar has no colour and colouring it invents an
    # interpretation the sensor did not make.
    SAR_GRAYSCALE = "sar-grayscale"

    # Bi-temporal change. **Diverging, and that is the point**: change has a sign, so the ramp needs a
    # neutral midpoint at zero with loss and gain running in opposite directions. A sequential ramp over
    # signed change makes "no change" look like an extreme.
    CHANGE_DIVERGING = "change-diverging"

    # Vegetation indices. Red-to-green because that is the convention every agronomist already reads, and
    # a product that inverted it would be misread at a glance by exactly the people it is for.
    INDEX_VEGETATION = "index-vegetation"

    # Confidence and uncertainty surfaces. Perceptually uniform, so equal steps in confidence look like
    # equal steps - which a rainbow ramp does not deliver and is the reason rainbow is absent here.
    CONFIDENCE_MAGMA = "confidence-magma"

    # Object detections. A single hue, because a detection is present or it is not.
    DETECTION_TEAL = "detection-teal"

    # Binary masks drawn over imagery. Amber for visibility against both vegetation and built-up ground.
    MASK_AMBER = "mask-amber"

    # Intermediate artefacts - a cloud mask, a co-registration residual. Deliberately dull, so a
    # diagnostic figure never looks like a finding.
    ARTEFACT_NEUTRAL = "artefact-neutral"


# Our ramp id -> the matplotlib colormap that implements it.
#
# The indirection is the point. matplotlib is where the perceptually-tested colour science already lives,
# and reimplementing it would mean hand-picking control points; but its names are an implementation detail
# that must not reach the wire, because the frontend labels its legends from *our* ids.
MATPLOTLIB_COLORMAPS: Final[dict[ColorRampId, str]] = {
    ColorRampId.TRUE_COLOR: "gray",  # unused - a true-colour composite bypasses the LUT entirely
    ColorRampId.SAR_GRAYSCALE: "gray",
    ColorRampId.CHANGE_DIVERGING: "RdBu_r",
    ColorRampId.INDEX_VEGETATION: "RdYlGn",
    ColorRampId.CONFIDENCE_MAGMA: "magma",
    ColorRampId.DETECTION_TEAL: "GnBu",
    ColorRampId.MASK_AMBER: "Oranges",
    ColorRampId.ARTEFACT_NEUTRAL: "cividis",
}

# Ramps whose domain is fixed by the quantity itself rather than by the data in front of us.
#
# **A normalised index is always drawn over [-1, 1], never over its own min and max.** Two NDVI maps of the
# same field in different weeks are only comparable if they share a scale; stretching each to its own
# extremes makes every image look equally varied and hides the change between them. This is the specific
# way `architecture-context.md` §8 rule 13 gets violated by a reasonable-looking default.
FIXED_DOMAINS: Final[dict[ColorRampId, tuple[float, float]]] = {
    ColorRampId.INDEX_VEGETATION: (-1.0, 1.0),
    ColorRampId.CHANGE_DIVERGING: (-1.0, 1.0),
    ColorRampId.CONFIDENCE_MAGMA: (0.0, 1.0),
}

# How many entries a ramp's lookup table holds. 256 because the output is 8-bit RGBA, so a finer table
# would quantise to the same bytes; coarser would band a smooth gradient visibly.
COLOR_RAMP_RESOLUTION: Final[int] = 256

# What a fully transparent pixel is. Nodata is transparent rather than black: a black nodata margin over a
# globe reads as burnt ground, and over a white report page it reads as data.
TRANSPARENT_ALPHA: Final[int] = 0
OPAQUE_ALPHA: Final[int] = 255

# The alpha a mask overlay is drawn at over its base image. High enough to read the mask, low enough to
# see what it covers - an operator judging a mask needs to see what it agrees and disagrees with.
MASK_OVERLAY_ALPHA: Final[int] = 140
