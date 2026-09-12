"""Scores a VLM's words against a reference: exact match for closed answers, box overlap for grounding, ROUGE-L for captions.

what  : `normalise_answer()`, `exact_match()`, `parse_normalised_box()`, `box_iou()`, `rouge_l()`, and
        `VqaScore` (counts per answer type, summed before ratios).
where : `services/evaluation/vqa.py`. Sync, called via `asyncio.to_thread`.
how   : Closed answers (yes/no, a letter) are compared after lower-casing, stripping punctuation and
        taking the first token - "Yes, there is." is a yes. A box is a hit at IoU >= 0.5 on the normalised
        [x0 y0, x1 y1] form BigEarthNet.txt uses. Captions get ROUGE-L F1 on word tokens (longest common
        subsequence), the customary caption overlap; BLEU would need a tokeniser and a brevity penalty for
        a marginal gain on two-sentence outputs.
"""

import re
from dataclasses import dataclass, field

_PUNCTUATION = re.compile(r"[^\w\s.\-]")
_BOX = re.compile(r"\[?\s*(-?\d*\.?\d+)\s+(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s+(-?\d*\.?\d+)\s*\]?")
BOX_MATCH_IOU = 0.5


def normalise_answer(text: str) -> str:
    cleaned = _PUNCTUATION.sub(" ", text.lower()).split()
    return cleaned[0] if cleaned else ""


def exact_match(prediction: str, reference: str) -> bool:
    return normalise_answer(prediction) == normalise_answer(reference)


def parse_normalised_box(text: str) -> tuple[float, float, float, float] | None:
    match = _BOX.search(text)
    if match is None:
        return None
    x0, y0, x1, y1 = (float(value) for value in match.groups())
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def box_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    width = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = width * height
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union > 0 else 0.0


def rouge_l(prediction: str, reference: str) -> float:
    """ROUGE-L F1 over word tokens."""
    hypothesis = prediction.lower().split()
    truth = reference.lower().split()
    if not hypothesis or not truth:
        return 0.0
    previous = [0] * (len(truth) + 1)
    for token in hypothesis:
        current = [0] * (len(truth) + 1)
        for index, other in enumerate(truth, start=1):
            current[index] = previous[index - 1] + 1 if token == other else max(previous[index], current[index - 1])
        previous = current
    lcs = previous[-1]
    if lcs == 0:
        return 0.0
    precision, recall = lcs / len(hypothesis), lcs / len(truth)
    return 2 * precision * recall / (precision + recall)


@dataclass
class VqaScore:
    """Per-type tallies. `accuracy` for closed types and boxes is hits / asked; captions report mean ROUGE-L."""

    asked: dict[str, int] = field(default_factory=dict)
    hits: dict[str, int] = field(default_factory=dict)
    caption_rouge_total: float = 0.0

    def record(self, kind: str, prediction: str, reference: str) -> bool:
        self.asked[kind] = self.asked.get(kind, 0) + 1
        if kind == "captioning":
            self.caption_rouge_total += rouge_l(prediction, reference)
            return False
        if kind == "bounding box":
            predicted, truth = parse_normalised_box(prediction), parse_normalised_box(reference)
            hit = predicted is not None and truth is not None and box_iou(predicted, truth) >= BOX_MATCH_IOU
        else:
            hit = exact_match(prediction, reference)
        if hit:
            self.hits[kind] = self.hits.get(kind, 0) + 1
        return hit

    def accuracy(self, kind: str) -> float | None:
        asked = self.asked.get(kind, 0)
        if asked == 0:
            return None
        if kind == "captioning":
            return self.caption_rouge_total / asked
        return self.hits.get(kind, 0) / asked

    @property
    def overall(self) -> float:
        """Mean over the types present - each type counts once, so 3,000 yes/no rows cannot hide 100 boxes."""
        values = [self.accuracy(kind) for kind in self.asked]
        return sum(v for v in values if v is not None) / len(values) if values else 0.0
