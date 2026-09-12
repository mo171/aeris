"""Scores the VLM on an instruction file - the rows `training/vlm/prepare_*.py` writes - so the base and the LoRA are compared on the same questions.

what  : `VqaReport` and `evaluate_vqa()`.
where : `aeris models evaluate --model rs-vlm --file <jsonl>`; the training notebooks call the same function
        for the zero-shot baseline before training and for the adapter after, and the difference between
        those two numbers is the fine-tune's whole justification.
how   : One generation per row, the prompt and images exactly as the file states them (the same notes, the
        same resize), scored by type: exact match for yes/no and letters, IoU >= 0.5 for boxes, ROUGE-L for
        captions. Per-type accuracies are reported separately and `overall` is their mean, because the file
        is balanced by construction and a single pooled accuracy would still be dominated by whichever
        type has the most rows. Mean stated confidence is reported beside accuracy so calibration can be
        eyeballed: a model that is 90% sure and 60% right is a worse instrument than one that says 60%.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.constants.model_ids import ModelId
from app.constants.vlm import VLM_MAX_NEW_TOKENS, VLM_MAX_NEW_TOKENS_SHORT
from app.lib.exceptions import InvalidRequestError
from app.models.manager import ModelManager
from app.services.evaluation.math.text_scores import VqaScore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VqaReport:
    file: Path
    samples: int
    score: VqaScore
    mean_confidence: float
    mean_latency_ms: float
    model_version: str
    # (kind, prompt, reference, prediction, hit) for the rows kept for the write-up.
    examples: list[tuple[str, str, str, str, bool]]


async def evaluate_vqa(
    *,
    manager: ModelManager,
    file: Path,
    limit: int | None = None,
    keep_examples: int = 12,
    predictions_path: Path | None = None,
) -> VqaReport:
    """Generate for every row (or the first `limit`) and score by type. With `predictions_path`, every
    row's prediction is written out, so two models can be compared row by row (paired) and not only by
    their means."""
    rows = await asyncio.to_thread(_read_rows, file)
    if not rows:
        raise InvalidRequestError(f"{file} holds no rows.", details={"path": str(file)})
    rows = rows[:limit] if limit else rows
    images_root = file.parent / "images"

    score = VqaScore()
    confidences: list[float] = []
    latencies: list[float] = []
    examples: list[tuple[str, str, str, str, bool]] = []
    predictions: list[dict] = []
    started = time.perf_counter()
    async with manager.lease(ModelId.REMOTE_SENSING_VLM) as model:
        version = model.version
        for index, row in enumerate(rows):
            images = [await asyncio.to_thread(_read_rgb, images_root / name) for name in row["images"]]
            budget = VLM_MAX_NEW_TOKENS if row["type"] == "captioning" else VLM_MAX_NEW_TOKENS_SHORT
            tick = time.perf_counter()
            generation = await asyncio.to_thread(
                model.generate, images, row["prompt"], image_notes=row.get("image_notes"), max_new_tokens=budget
            )
            latencies.append((time.perf_counter() - tick) * 1000)
            hit = await asyncio.to_thread(score.record, row["type"], generation.text, row["answer"])
            confidences.append(generation.mean_token_probability)
            predictions.append({
                "id": row["id"], "source": row.get("source"), "category": row.get("category"), "type": row["type"],
                "modality": row.get("modality"), "reference": row["answer"], "prediction": generation.text,
                "hit": hit, "confidence": generation.mean_token_probability, "model_version": version,
            })
            if len(examples) < keep_examples and index % max(1, len(rows) // keep_examples) == 0:
                examples.append((row["type"], row["prompt"], row["answer"], generation.text, hit))
            if (index + 1) % 50 == 0:
                logger.info("vqa evaluation progress", extra={"done": index + 1, "of": len(rows), "overall": round(score.overall, 3)})
    await manager.record_latency(ModelId.REMOTE_SENSING_VLM, round(float(np.mean(latencies))))
    if predictions_path is not None:
        await asyncio.to_thread(_write_rows, predictions_path, predictions)
    logger.info(
        "vqa evaluated",
        extra={"file": str(file), "samples": len(rows), "overall": score.overall, "seconds": round(time.perf_counter() - started, 1)},
    )
    return VqaReport(
        file=file, samples=len(rows), score=score, mean_confidence=float(np.mean(confidences)),
        mean_latency_ms=float(np.mean(latencies)), model_version=version, examples=examples,
    )


def _write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def _read_rows(file: Path) -> list[dict]:
    return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]


def _read_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))
