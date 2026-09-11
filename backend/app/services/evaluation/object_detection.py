"""Scores the object detector against oriented-box ground truth - counts summed over a split, ratios taken once.

what  : `DetectionReport` and `evaluate_object_detection()`.
where : `aeris models evaluate --model dota-detector`; 1.14's scorecard. Reads whatever split the 1.1
        loader enumerates, so DOTA8 (the smoke test) and DOTA proper (when acquired) go through one path.
how   : Each sample is one forward pass; predictions are matched to truth at `DETECTION_MATCH_IOU`, class
        by class, and hits, false alarms and misses are summed before precision, recall and F1 are taken -
        a mean of per-image F1s would let an empty image score a perfect nothing. This is F1 at one
        confidence threshold, the number the pipeline runs at; mAP over the whole curve is 1.14's, when
        DOTA's own evaluation server protocol is worth reproducing.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.constants.datasets import DATASET_CATALOGUE, DatasetId, DatasetSplit
from app.constants.detection import DETECTION_MATCH_IOU
from app.lib.exceptions import InvalidRequestError
from app.models.manager import ModelManager
from app.services.datasets.loader import load_samples
from app.services.detection.detector import detect_objects
from app.services.detection.labels import read_dota_labels, read_yolo_obb_labels
from app.services.detection.math.oriented_boxes import DetectionScore, OrientedBox, match_boxes

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DetectionReport:
    """The detector against one split: counts, ratios, and how long it took."""

    dataset_id: DatasetId
    split: DatasetSplit
    samples: int
    score: DetectionScore
    predicted_boxes: int
    truth_boxes: int
    mean_confidence: float | None
    mean_latency_ms: float
    model_version: str


async def evaluate_object_detection(
    *,
    manager: ModelManager,
    dataset_id: DatasetId = DatasetId.DOTA8,
    split: DatasetSplit = DatasetSplit.VALIDATION,
    limit: int | None = None,
) -> DetectionReport:
    """Score every sample of the split (or the first `limit`) at the pipeline's own confidence threshold."""
    record = DATASET_CATALOGUE[dataset_id]
    total = DetectionScore(0, 0, 0)
    predicted = truth_count = count = 0
    confidences: list[float] = []
    latencies: list[int] = []
    started = time.perf_counter()

    samples = await asyncio.to_thread(lambda: list(load_samples(dataset_id, split)))
    for sample in samples[:limit] if limit else samples:
        if sample.label is None:
            raise InvalidRequestError(
                f"{sample.sample_id} has no annotation file.", details={"datasetId": dataset_id.value}
            )
        image = await asyncio.to_thread(_read_rgb, sample.images[0])
        truths = await _read_truth(dataset_id, sample.label, width=image.shape[1], height=image.shape[0])
        result = await detect_objects(image, manager=manager)
        total = total + await asyncio.to_thread(match_boxes, result.boxes, truths, iou_threshold=DETECTION_MATCH_IOU)
        predicted += len(result.boxes)
        truth_count += len(truths)
        if result.confidence is not None:
            confidences.append(result.confidence)
        latencies.append(result.latency_ms)
        count += 1
        version = result.model_version

    if count == 0:
        raise InvalidRequestError(
            f"{record.title} {split.value} split holds no samples on disk.", details={"datasetId": dataset_id.value}
        )
    logger.info(
        "object detection evaluated",
        extra={
            "dataset_id": dataset_id.value, "split": split.value, "samples": count, "f1": total.f1,
            "seconds": round(time.perf_counter() - started, 1),
        },
    )
    return DetectionReport(
        dataset_id=dataset_id, split=split, samples=count, score=total, predicted_boxes=predicted,
        truth_boxes=truth_count, mean_confidence=float(np.mean(confidences)) if confidences else None,
        mean_latency_ms=float(np.mean(latencies)), model_version=version,
    )


async def _read_truth(dataset_id: DatasetId, label: Path, *, width: int, height: int) -> list[OrientedBox]:
    if dataset_id is DatasetId.DOTA:
        return await read_dota_labels(label)
    return await read_yolo_obb_labels(label, width=width, height=height)


def _read_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))
