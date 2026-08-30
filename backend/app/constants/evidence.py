"""The kinds of assertion AERIS can make, and the kinds of proof it can attach to them.

what  : `ClaimKind`, `EvidenceKind`, `MetricDirection`.
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
