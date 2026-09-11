"""Runs the object detector over an optical image and returns its oriented boxes with the model's stated confidence.

what  : `ObjectDetectionResult` and `detect_objects()`.
where : S13 (and S15 when a detection is the evidence). Called by the evaluation harness and by 1.10's S13
        node. Leases `dota-detector` from `app/models/manager.py`.
how   : The adapter does the windowing and the merge; this module does the lease, the clock and the
        record: which model, which version, how long, and how sure. Confidence is the mean of the
        model's own scores over the boxes it kept - its certainty in what it reported, stated as such,
        and `None` when it reported nothing, because certainty about nothing is not a number.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

import numpy as np

from app.constants.fleet import FLEET
from app.constants.model_ids import ModelId
from app.models.manager import ModelManager
from app.services.detection.math.oriented_boxes import OrientedBox

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ObjectDetectionResult:
    """What the detector found and what it took."""

    boxes: list[OrientedBox]
    class_names: tuple[str, ...]
    model_id: ModelId
    model_version: str
    confidence: float | None
    latency_ms: int

    def count(self, class_name: str) -> int:
        index = self.class_names.index(class_name)
        return sum(1 for box in self.boxes if box.class_index == index)


async def detect_objects(image: np.ndarray, *, manager: ModelManager) -> ObjectDetectionResult:
    """Lease the detector, run it over the image, record the latency."""
    started = time.perf_counter()
    async with manager.lease(ModelId.DOTA_DETECTOR) as model:
        prediction = await asyncio.to_thread(model.predict, image)
    latency_ms = round((time.perf_counter() - started) * 1000)
    await manager.record_latency(ModelId.DOTA_DETECTOR, latency_ms)

    record = FLEET[ModelId.DOTA_DETECTOR]
    boxes = prediction.boxes
    confidence = float(np.mean([box.confidence for box in boxes])) if boxes else None
    logger.info(
        "objects detected",
        extra={"boxes": len(boxes), "latency_ms": latency_ms, "confidence": confidence, "shape": list(image.shape[:2])},
    )
    return ObjectDetectionResult(
        boxes=boxes, class_names=prediction.class_names, model_id=record.model_id,
        model_version=record.version, confidence=confidence, latency_ms=latency_ms,
    )
