"""Runs the land-cover segmenter over an optical picture and returns a class per pixel with the model's stated confidence.

what  : `SegmentationResult` and `segment_image()`.
where : S13 (`pipeline/nodes/segmentation.py`). Leases `segformer-landcover` from `app/models/manager.py`.
how   : The adapter (`app/models/segmentation.py`) does the windowing, the stitching and the argmax; this
        module does the lease, the clock and the record: which model, which version, how long, and how
        sure. Confidence is the mean winning-class probability over the pixels the model judged - its
        own certainty, averaged, stated as exactly that (the same reading as the change detector's) -
        and `None` when it judged nothing. Pixels the caller marks unobserved (NaN) come back as the
        ignore label with NaN confidence, so an unobserved pixel is never a land cover.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import numpy as np

from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.models.manager import ModelManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SegmentationResult:
    """What the segmenter decided, per pixel, and what it took."""

    class_map: np.ndarray
    confidence: np.ndarray
    class_names: tuple[str, ...]
    model_id: ModelId
    model_version: str
    # Mean winning-class probability over judged pixels: the model's own certainty, stated as such.
    stated_confidence: float | None
    latency_ms: int


async def segment_image(image: np.ndarray, *, manager: ModelManager) -> SegmentationResult:
    """Lease the segmenter, run it over an (H, W, 3) picture, record the latency."""
    started = time.perf_counter()
    async with manager.lease(ModelId.SEGFORMER_LANDCOVER) as model:
        prediction = await asyncio.to_thread(model.predict, image)
    latency_ms = round((time.perf_counter() - started) * 1000)
    await manager.record_latency(ModelId.SEGFORMER_LANDCOVER, latency_ms)

    record = FLEET[ModelId.SEGFORMER_LANDCOVER]
    judged = np.isfinite(prediction.confidence)
    stated = float(prediction.confidence[judged].mean()) if judged.any() else None
    logger.info(
        "land cover segmented",
        extra={"latency_ms": latency_ms, "confidence": stated, "shape": list(image.shape[:2]), "judged": float(judged.mean())},
    )
    return SegmentationResult(
        class_map=prediction.class_map, confidence=prediction.confidence, class_names=prediction.class_names,
        model_id=record.model_id, model_version=record.version, stated_confidence=stated, latency_ms=latency_ms,
    )
