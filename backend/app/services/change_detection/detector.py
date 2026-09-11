"""Runs the learned change detector over a co-registered optical pair and returns a mask with the model's stated confidence behind it.

what  : `ChangeDetectionResult` and `detect_change()`.
where : S13. Called by `services/change_detection/comparison.py` after the residual gate, by the
        evaluation harness, and by 1.10's S13 node. Leases `changeformer` from `app/models/manager.py`.
how   : The adapter (`app/models/change.py`) gives a probability per pixel; this service decides what a
        probability *means*: above `CHANGE_PROBABILITY_THRESHOLD` it is change, NaN it is unobserved, and
        the run's stated confidence is the mean of the model's winning-class probability over the pixels
        it judged. That last number is the model's own certainty, averaged, stated as exactly that - not
        a calibrated accuracy - and S18 aggregates it with whatever the other stages state.

        **Nothing here checks that the pair is aligned.** That is `comparison.py`'s job, and it runs
        before this by construction; a caller that skips it has skipped §8 rule 2, which is why the node
        goes through `comparison.py` and never here directly.

        Inference is offloaded with `asyncio.to_thread`: a forward pass over a Sentinel-2 subset is
        seconds of GPU time, and the voice stream keeps serving while it runs.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import numpy as np

from app.constants.change import CHANGE_PROBABILITY_THRESHOLD
from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.models.manager import ModelManager
from app.services.change_detection.math.change_statistics import change_fraction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ChangeDetectionResult:
    """A change mask, the probability it was cut from, and the model that produced both."""

    probability: np.ndarray
    mask: np.ndarray
    observed: np.ndarray
    model_id: ModelId
    model_version: str
    # The model's mean winning-class probability over observed pixels. Its own certainty, stated as such.
    confidence: float | None
    latency_ms: int

    @property
    def changed_fraction(self) -> float:
        return change_fraction(self.mask, self.observed)


async def detect_change(before: np.ndarray, after: np.ndarray, *, manager: ModelManager) -> ChangeDetectionResult:
    """Change between two (H, W, 3) RGB arrays on one grid, from the resident ChangeFormer."""
    record = FLEET[ModelId.CHANGEFORMER]
    started = time.perf_counter()
    async with manager.lease(ModelId.CHANGEFORMER) as model:
        probability = await asyncio.to_thread(model.predict, before, after)
    latency_ms = round((time.perf_counter() - started) * 1000)
    await manager.record_latency(ModelId.CHANGEFORMER, latency_ms)

    observed = np.isfinite(probability)
    mask = observed & (np.nan_to_num(probability, nan=0.0) >= CHANGE_PROBABILITY_THRESHOLD)
    confidence = _stated_confidence(probability, observed)

    logger.info(
        "change detected",
        extra={
            "model_id": record.model_id.value, "version": record.version, "latency_ms": latency_ms,
            "changed_fraction": change_fraction(mask, observed), "confidence": confidence,
        },
    )
    return ChangeDetectionResult(
        probability=probability, mask=mask, observed=observed,
        model_id=record.model_id, model_version=record.version, confidence=confidence, latency_ms=latency_ms,
    )


def _stated_confidence(probability: np.ndarray, observed: np.ndarray) -> float | None:
    """Mean of max(p, 1 - p) over observed pixels: how sure the model was, whichever way it decided."""
    if not observed.any():
        return None
    judged = probability[observed]
    return float(np.maximum(judged, 1.0 - judged).mean())
