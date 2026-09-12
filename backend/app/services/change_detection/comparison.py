"""Refuses to compare two dates that are not on the same ground - the residual gate every change detector runs behind.

what  : `GatedComparison` and `compare_pair()`: measure the co-registration residual on the alignment
        band, refuse above tolerance, and only then run the detector.
where : S13's entry point for an optical pair. 1.10's S13 node calls this and never the detector directly.
how   : `architecture-context.md` §8 rule 2, verbatim: *the co-registration residual gates the comparison.
        Above tolerance the pipeline refuses to run change detection; a residual larger than the feature
        under discussion invalidates the comparison, it does not merely degrade it, and lowering a
        confidence score is not an honest substitute for refusing.* The 1.3 measurement and refusal are
        reused as they are; this module adds nothing to the physics, it puts the gate in front of the model.

        The residual is measured on one band - the caller says which, and it should be the sharpest one
        (red or near-infrared at 10 m for Sentinel-2) - and the refusal is raised as the 1.3
        `InvalidRequestError` with the residual in its details, so a run reports *why* it did not compare.
"""

import logging
from dataclasses import dataclass

import numpy as np

from app.models.manager import ModelManager
from app.services.change_detection.detector import ChangeDetectionResult, detect_change
from app.services.preprocessing.coregistration import (
    CoregistrationResult,
    measure_coregistration,
    require_comparison_ready,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GatedComparison:
    """A change result and the registration measurement that admitted it."""

    registration: CoregistrationResult
    change: ChangeDetectionResult


async def compare_pair(
    before_rgb: np.ndarray,
    after_rgb: np.ndarray,
    *,
    alignment_before: np.ndarray,
    alignment_after: np.ndarray,
    manager: ModelManager,
) -> GatedComparison:
    """Measure the residual, refuse above tolerance, then detect. In that order, only."""
    registration = await measure_coregistration(alignment_before, alignment_after)
    await require_comparison_ready(registration)
    logger.info(
        "pair admitted to change detection",
        extra={"residual_pixels": registration.measurement.residual_pixels},
    )
    change = await detect_change(before_rgb, after_rgb, manager=manager)
    return GatedComparison(registration=registration, change=change)
