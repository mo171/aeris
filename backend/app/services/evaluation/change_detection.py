"""Scores the change detector against LEVIR-CD's held-out crops - the half of the 1.6 gate that says whether the model is any good.

what  : `EvaluationReport` and `evaluate_change_detection()`: run the resident detector over a benchmark
        split through the single dataset loader, score every sample on the change class, and sum.
where : `aeris models evaluate changeformer` in Phase 1; 1.14's scorecard calls the same function with
        every split and commits the report. Reads the dataset the 1.1 catalogue enumerates and nothing
        else, so a partial download scores what is there and says how much that was.
how   : Counts are summed across samples before the ratios are taken (`ChangeScore.__add__`), which is
        how LEVIR-CD results are reported - a mean of per-crop F1s rewards easy empty crops. Area is
        reported at the benchmark's nominal pixel size, in hectares, for both the prediction and the
        truth: a model that finds the right pixels in the wrong places scores badly on IoU and well on
        area, and an operator needs both numbers to know which failure they are looking at.

        Each sample is one forward pass. Batching would be faster and is 1.14's optimisation, not this
        gate's; correctness first, and a run of the full test split is a minute on a laptop GPU.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.constants.datasets import DATASET_CATALOGUE, DatasetId, DatasetSplit
from app.constants.geo import SQUARE_METRES_PER_HECTARE
from app.lib.exceptions import InvalidRequestError
from app.models.manager import ModelManager
from app.services.change_detection.detector import detect_change
from app.services.change_detection.math.change_statistics import ChangeScore, score_mask
from app.services.datasets.loader import DatasetSample, load_samples

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """The detector against one split: counts, ratios, areas, and how long it took."""

    dataset_id: DatasetId
    split: DatasetSplit
    samples: int
    score: ChangeScore
    predicted_hectares: float
    truth_hectares: float
    mean_confidence: float | None
    mean_latency_ms: float
    model_version: str


async def evaluate_change_detection(
    *,
    manager: ModelManager,
    dataset_id: DatasetId = DatasetId.LEVIR_CD,
    split: DatasetSplit = DatasetSplit.TEST,
    limit: int | None = None,
) -> EvaluationReport:
    """Score every sample of the split (or the first `limit`), summing counts before taking ratios."""
    record = DATASET_CATALOGUE[dataset_id]
    if record.pixel_size_metres is None:
        raise InvalidRequestError(
            f"{record.title} states no nominal pixel size, so its masks cannot be reported in hectares.",
            details={"datasetId": dataset_id.value},
        )
    pixel_hectares = record.pixel_size_metres**2 / SQUARE_METRES_PER_HECTARE

    total = ChangeScore(0, 0, 0, 0)
    predicted_pixels = truth_pixels = 0
    confidences: list[float] = []
    latencies: list[int] = []
    count = 0
    started = time.perf_counter()

    samples = await asyncio.to_thread(lambda: list(load_samples(dataset_id, split)))
    for sample in samples[:limit] if limit else samples:
        before, after, truth = await asyncio.to_thread(_read_sample, sample)
        result = await detect_change(before, after, manager=manager)
        score = await asyncio.to_thread(score_mask, result.mask, truth, result.observed)
        total = total + score
        predicted_pixels += int(result.mask.sum())
        truth_pixels += int(truth.sum())
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
        "change detection evaluated",
        extra={
            "dataset_id": dataset_id.value, "split": split.value, "samples": count, "f1": total.f1, "iou": total.iou,
            "seconds": round(time.perf_counter() - started, 1),
        },
    )
    return EvaluationReport(
        dataset_id=dataset_id,
        split=split,
        samples=count,
        score=total,
        predicted_hectares=predicted_pixels * pixel_hectares,
        truth_hectares=truth_pixels * pixel_hectares,
        mean_confidence=float(np.mean(confidences)) if confidences else None,
        mean_latency_ms=float(np.mean(latencies)),
        model_version=version,
    )


def _read_sample(sample: DatasetSample) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The pair as 8-bit RGB and the label as a boolean mask. Sync, for `to_thread`."""
    before = _read_rgb(sample.images[0])
    after = _read_rgb(sample.images[1])
    assert sample.label is not None
    # LEVIR-CD labels are 0/255 PNGs; anything above zero is the change class.
    truth = np.asarray(Image.open(sample.label).convert("L")) > 0
    return before, after, truth


def _read_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))
