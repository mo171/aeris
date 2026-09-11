"""Oriented boxes as polygons: overlap between two, duplicates across a tile seam removed, predictions matched to truth.

what  : `OrientedBox`; `polygon_iou()`; `suppress_overlaps()` (greedy class-aware NMS); `match_boxes()` and
        `DetectionScore` (counts summed before ratios, like `ChangeScore`).
where : `app/models/detection.py` merges its tiles with `suppress_overlaps`; the evaluation harness scores
        with `match_boxes`. Sync, called via `asyncio.to_thread`.
how   : An oriented box is its four corners, and the overlap of two is the area of their polygon
        intersection over their union - shapely does the clipping, so a box at 37° is measured as it is
        rather than by its axis-aligned envelope, which for a long thin ship would overstate the overlap by
        several times. Suppression is greedy by confidence within a class, the standard rotated NMS; matching
        is the same greed against the truth, each truth box claimed at most once, at `DETECTION_MATCH_IOU`.
"""

from dataclasses import dataclass

import numpy as np
from shapely.geometry import Polygon


@dataclass(frozen=True, slots=True)
class OrientedBox:
    """One detection: its class, the model's score for it, and its four corners in pixels (4, 2)."""

    class_index: int
    confidence: float
    corners: np.ndarray

    @property
    def polygon(self) -> Polygon:
        return Polygon(self.corners)

    def offset(self, column: int, row: int) -> OrientedBox:
        """The same box in the coordinates of a larger image the window was cut from."""
        return OrientedBox(self.class_index, self.confidence, self.corners + np.array([column, row], dtype=np.float32))


def polygon_iou(a: Polygon, b: Polygon) -> float:
    """Intersection over union of two polygons; zero when either is degenerate."""
    if not a.is_valid or not b.is_valid or a.is_empty or b.is_empty:
        return 0.0
    union = a.union(b).area
    return a.intersection(b).area / union if union > 0 else 0.0


def suppress_overlaps(boxes: list[OrientedBox], *, iou_threshold: float) -> list[OrientedBox]:
    """Keep the most confident of every group of same-class boxes that overlap above the threshold."""
    kept: list[OrientedBox] = []
    kept_polygons: list[Polygon] = []
    for box in sorted(boxes, key=lambda b: b.confidence, reverse=True):
        polygon = box.polygon
        duplicate = any(
            other.class_index == box.class_index and polygon_iou(polygon, other_polygon) >= iou_threshold
            for other, other_polygon in zip(kept, kept_polygons, strict=True)
        )
        if not duplicate:
            kept.append(box)
            kept_polygons.append(polygon)
    return kept


@dataclass(frozen=True, slots=True)
class DetectionScore:
    """Hits, false alarms and misses. Precision, recall and F1 follow; accuracy has no meaning here."""

    true_positives: int
    false_positives: int
    false_negatives: int

    def __add__(self, other: DetectionScore) -> DetectionScore:
        return DetectionScore(
            self.true_positives + other.true_positives,
            self.false_positives + other.false_positives,
            self.false_negatives + other.false_negatives,
        )

    @property
    def precision(self) -> float:
        predicted = self.true_positives + self.false_positives
        return self.true_positives / predicted if predicted else 0.0

    @property
    def recall(self) -> float:
        actual = self.true_positives + self.false_negatives
        return self.true_positives / actual if actual else 0.0

    @property
    def f1(self) -> float:
        denominator = self.precision + self.recall
        return 2 * self.precision * self.recall / denominator if denominator else 0.0


def match_boxes(predictions: list[OrientedBox], truths: list[OrientedBox], *, iou_threshold: float) -> DetectionScore:
    """Greedy matching by confidence: a prediction hits the first unclaimed truth of its class it overlaps enough."""
    truth_polygons = [t.polygon for t in truths]
    claimed: set[int] = set()
    hits = 0
    for box in sorted(predictions, key=lambda b: b.confidence, reverse=True):
        polygon = box.polygon
        for index, truth in enumerate(truths):
            if index in claimed or truth.class_index != box.class_index:
                continue
            if polygon_iou(polygon, truth_polygons[index]) >= iou_threshold:
                claimed.add(index)
                hits += 1
                break
    return DetectionScore(hits, len(predictions) - hits, len(truths) - hits)
