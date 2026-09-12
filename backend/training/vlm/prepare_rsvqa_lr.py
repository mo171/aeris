"""Builds the RSVQA-LR instruction rows: Sentinel-2 questions over the Netherlands, so the LoRA sees more than one country.

what  : `python -m training.vlm.prepare_rsvqa_lr --output data/training/vlm` writes `rsvqa_lr.{train,validation,test}.jsonl`
        and copies the 256-pixel images it references into `images/`.
where : Beside `prepare_bigearthnet_txt.py`; `merge_instruction_sets.py` joins their rows into the file the
        Kaggle notebook trains on. `aeris models evaluate --model rs-vlm --file` scores the test rows.
how   : RSVQA-LR (Lobry et al. 2020, CC-BY-4.0): 772 Sentinel-2 RGB images at 10 m, 77k questions of four
        types - presence, comparison, count, rural/urban. Its published splits are by *image*, and so are
        ours: a question on a training image never appears in test. Two things the prep corrects for:

        - **Rural/urban is 1% of the questions** (one per image) and count is 25%; buckets are capped so the
          model sees each type in comparable numbers.
        - **Counts are open-ended integers**; the answer is asked for as a number and scored by exact match,
          which is what the benchmark's own protocol does.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from app.constants.datasets import DatasetId, DatasetSplit
from app.services.datasets.catalogue import require_trainable
from app.services.datasets.loader import split_directory

logger = logging.getLogger(__name__)

TRAIN_CAP_PER_TYPE = 2_500
EVAL_CAP_PER_TYPE = 150
ANSWER_FORMAT = {
    "presence": " Answer yes or no.",
    "comp": " Answer yes or no.",
    "rural_urban": " Answer rural or urban.",
    "count": " Answer with a number.",
}
SPLIT_FILES = {"train": "LR_split_train_images.json", "validation": "LR_split_val_images.json", "test": "LR_split_test_images.json"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=Path("data/training/vlm"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--skip-licence-gate", action="store_true", help="Evaluation splits only; never for training.")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not arguments.skip_licence_gate:
        require_trainable(DatasetId.RSVQA_LR, DatasetSplit.TRAIN)

    root = split_directory(DatasetId.RSVQA_LR, DatasetSplit.TRAIN)
    questions = {q["id"]: q for q in json.loads((root / "all_questions.json").read_text(encoding="utf-8"))["questions"] if q["active"]}
    answers: dict[int, str] = {}
    for answer in json.loads((root / "all_answers.json").read_text(encoding="utf-8"))["answers"]:
        if answer["active"]:
            answers[answer["question_id"]] = str(answer["answer"]).strip()
    generator = random.Random(arguments.seed)
    images = arguments.output / "images"
    images.mkdir(parents=True, exist_ok=True)
    counts: Counter[str] = Counter()

    for split, filename in SPLIT_FILES.items():
        if arguments.skip_licence_gate and split == "train":
            continue
        listing = json.loads((root / filename).read_text(encoding="utf-8"))["images"]
        by_type: dict[str, list[dict]] = defaultdict(list)
        for image in listing:
            if not image["active"]:
                continue
            for question_id in image["questions_ids"]:
                question = questions.get(question_id)
                if question is None or question_id not in answers:
                    continue
                by_type[question["type"]].append({"image_id": image["id"], **question, "answer": answers[question_id]})
        cap = TRAIN_CAP_PER_TYPE if split == "train" else EVAL_CAP_PER_TYPE
        selected = []
        for _, rows in sorted(by_type.items()):
            generator.shuffle(rows)
            selected.extend(rows[:cap])
        generator.shuffle(selected)
        with (arguments.output / f"rsvqa_lr.{split}.jsonl").open("w", encoding="utf-8") as handle:
            for row in selected:
                name = f"rsvqa_lr_{row['image_id']}.tif"
                if not (images / name).exists():
                    shutil.copyfile(root / "Images_LR" / f"{row['image_id']}.tif", images / name)
                handle.write(json.dumps({
                    "id": f"rsvqa-lr-{row['id']}", "source": "rsvqa-lr", "split": split, "category": row["type"],
                    "type": _score_type(row["type"]), "modality": "s2", "images": [name], "image_notes": [None],
                    "prompt": _question(row["question"]) + ANSWER_FORMAT[row["type"]], "answer": row["answer"],
                }, ensure_ascii=False) + "\n")
                counts[f"{split}/{row['type']}"] += 1
        logger.info("%s: %d rows %s", split, len(selected), {k: len(v) for k, v in by_type.items()})
    (arguments.output / "counts_rsvqa_lr.json").write_text(json.dumps(dict(sorted(counts.items())), indent=2), encoding="utf-8")


def _question(text: str) -> str:
    """RSVQA questions carry no question mark; the model is asked a question, not handed a fragment."""
    text = text.strip()
    return text if text.endswith("?") else text + "?"


def _score_type(rsvqa_type: str) -> str:
    """The scorer's vocabulary: closed answers are `binary`-scored by first token, counts likewise."""
    return "binary" if rsvqa_type in {"presence", "comp"} else "mcq"


if __name__ == "__main__":
    main()
