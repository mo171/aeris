"""Scores a change mask against the truth on the change class alone, and measures how much of the observed ground changed.

what  : `score_mask()` - precision, recall, F1 and IoU of the change class; `change_fraction()`.
where : Called by `services/evaluation/change_detection.py` (the 1.6 gate's score) and by the change
        detector's result, through `asyncio.to_thread`.
how   : **Accuracy is deliberately absent.** LEVIR-CD's change class is a few percent of pixels, so a mask
        of all zeros scores 95% accuracy and says nothing. F1 and IoU on the change class are what the PDF's
        evaluation section (§22) and every published LEVIR-CD result report, and they are the only numbers
        here. A count-based definition - true positives over the predicted and true positives over the
        actual - checkable by hand on a 4x4 array.

        Pixels the prediction could not judge (NaN probability, unobserved input) are excluded from every
        count rather than scored as "no change": a cloud is not evidence that nothing was built under it.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class ChangeScore:
    """The change class against the truth, as counts and the four ratios built from them."""

    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int

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
        denominator = 2 * self.true_positives + self.false_positives + self.false_negatives
        return 2 * self.true_positives / denominator if denominator else 0.0

    @property
    def iou(self) -> float:
        union = self.true_positives + self.false_positives + self.false_negatives
        return self.true_positives / union if union else 0.0

    def __add__(self, other: ChangeScore) -> ChangeScore:
        return ChangeScore(
            self.true_positives + other.true_positives,
            self.false_positives + other.false_positives,
            self.false_negatives + other.false_negatives,
            self.true_negatives + other.true_negatives,
        )


def score_mask(predicted: np.ndarray, truth: np.ndarray, observed: np.ndarray | None = None) -> ChangeScore:
    """Counts over the pixels that were observed. Both masks boolean on one grid."""
    if predicted.shape != truth.shape:
        raise ValueError(f"Prediction {predicted.shape} and truth {truth.shape} are not on one grid.")
    if observed is None:
        observed = np.ones(predicted.shape, dtype=bool)
    predicted = predicted & observed
    truth = truth & observed
    return ChangeScore(
        true_positives=int((predicted & truth).sum()),
        false_positives=int((predicted & ~truth).sum()),
        false_negatives=int((~predicted & truth).sum()),
        true_negatives=int((~predicted & ~truth & observed).sum()),
    )


def change_fraction(mask: np.ndarray, observed: np.ndarray) -> float:
    """The share of observed pixels marked changed. Zero, not NaN, when nothing was observed."""
    count = int(observed.sum())
    return float((mask & observed).sum() / count) if count else 0.0
