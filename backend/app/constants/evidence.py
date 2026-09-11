"""The kinds of assertion AERIS can make, and the kinds of proof it can attach to them.

what  : `ClaimKind`, `EvidenceKind`, `MetricDirection`, and the byte values of the S15 mask artefact.
where : Read by the claim validator (Phase 1.5) and by every stream event that carries a claim or an
        evidence record. Transcribed from the frontend's investigation schema.
how   : `ClaimKind.NEGATIVE` is the one that makes the product honest. "No new construction was detected in
        the north-east" is a claim with evidence behind it - an absence the system looked for and did not
        find - and it is not the same thing as saying nothing. A system that can only assert presence will
        quietly omit the answer the operator most needs, and `INSUFFICIENT_EVIDENCE` is a different response
        again (`api-contract.md` §1 rule 7: it is a success, not an error).

        `MetricDirection.NEUTRAL` exists so that "measured, and it did not move" is expressible. Without it,
        a measured non-change has to be encoded as an increase of zero, which reads as a finding.
"""

from enum import StrEnum
from typing import Final


class ClaimKind(StrEnum):
    """The kind of assertion a claim makes."""

    QUANTITATIVE = "quantitative"
    SPATIAL = "spatial"
    CATEGORICAL = "categorical"
    NEGATIVE = "negative"


class EvidenceKind(StrEnum):
    """The kind of artefact backing a claim. Every claim has at least one."""

    CHANGE_MASK = "change-mask"
    DETECTION = "detection"
    INDEX_MAP = "index-map"
    SCENE_CROP = "scene-crop"
    STATISTIC = "statistic"
    CROSS_MODAL = "cross-modal"


class MetricDirection(StrEnum):
    """Which way a measured quantity moved between T0 and T1."""

    INCREASE = "increase"
    DECREASE = "decrease"
    NEUTRAL = "neutral"


# The S15 mask artefact, one uint8 per pixel. `UNOBSERVED` is distinct from `NOT_DETECTED` for the reason
# `services/evidence/spatial.py` gives: ground under cloud was not searched, and a mask that recorded it as
# "nothing found" would be reporting an absence nobody measured.
DETECTION_MASK_NOT_DETECTED: Final[int] = 0
DETECTION_MASK_DETECTED: Final[int] = 1
DETECTION_MASK_UNOBSERVED: Final[int] = 255

# --- Building evidence from a mask (Phase 1.5) ------------------------------------------------------------

# Vertices closer than this to the line that replaces them are removed when a region polygon is simplified.
# Half a 10 m pixel: the raster's staircase edge is not a property of the ground, and keeping it multiplies
# the vertex count of every feature by the pixel perimeter. Douglas-Peucker with topology preserved.
POLYGON_SIMPLIFICATION_TOLERANCE_METRES: Final[float] = 5.0

# Regions smaller than this are measured and counted but not drawn as individual features. The claim's
# hectares are the whole mask - nothing is dropped from the number - and the raster-mask layer shows every
# pixel; what the floor bounds is the vector payload, which otherwise carries thousands of one-pixel rings.
MINIMUM_FEATURE_REGION_PIXELS: Final[int] = 25

# How many decimals each metric is meaningful to (`claimMetricSchema.precision`). Hectares to one decimal:
# a 10 m pixel is 0.01 ha, so the second decimal is one pixel and the third is noise.
HECTARES_PRECISION: Final[int] = 1
PERCENTAGE_PRECISION: Final[int] = 1
COUNT_PRECISION: Final[int] = 0
INDEX_VALUE_PRECISION: Final[int] = 2

# The rule S18 applies and S19 records (PDF §21.2: "aggregation rule recorded, not just shown"). The run's
# confidence is the weakest stated stage confidence; a stage that declines to state one does not lower
# it, and a run where no stage states one has none. Named so the record can say which rule produced it.
CONFIDENCE_AGGREGATION_RULE: Final[str] = "minimum-of-stated"
