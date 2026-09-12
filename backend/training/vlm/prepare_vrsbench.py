"""Cuts a slice of VRSBench - high-resolution captions, VQA and referring boxes - so the LoRA sees the resolution the judges' Cartosat imagery will have.

what  : `python -m training.vlm.prepare_vrsbench --annotations VRSBench_train.json --images-zip Images_train.zip
        --output <dir> --images 1500` writes `vrsbench.train.jsonl` and extracts only the sampled images.
where : Meant to run **on Kaggle**, inside `03_train_lora.ipynb`: the image archive is 7.8 GB, minutes there
        and hours on the laptop. This file has no `app` imports for that reason - it is copied into the
        Kaggle dataset beside the rows and imported from there. The same code runs on a laptop given a
        local zip.
how   : VRSBench (Li et al. 2024, CC-BY-4.0): 29k DOTA/DIOR images at 0.1-1 m with 20k captions, 86k VQA
        and 36k referring expressions. A slice of `--images` images, each contributing up to one caption,
        two VQA rows and one referring row, keeps the three tasks in proportion and the archive small.
        Referring answers come as `{<x0><y0><x1><y1>}` in hundredths of the image; they are rewritten to
        the `[x0 y0, x1 y1]` normalised form BigEarthNet.txt uses, so one grounding format is taught.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import zipfile
from collections import defaultdict
from pathlib import Path

TAG = re.compile(r"^<image>\n\[(\w+)\]\s*")
BOX = re.compile(r"\{<(\d+)><(\d+)><(\d+)><(\d+)>\}")
REFERRING_TEXT = re.compile(r"<p>(.*?)</p>")
# VRSBench wraps each VQA question in one of a dozen instruction templates ("Given the image, answer the
# following question with no more than three words. ...", "Q: ... A:"). The wrapper is stripped so the
# model is taught the question, and one answer-format sentence of ours replaces all of theirs.
VQA_PREFIXES = re.compile(
    r"^(?:What is the answer to the following question\s*|Based on the image, respond to this question with a "
    r"(?:short|brief) answer:?\s*|Use the provided image to answer the question:?\s*|Given the image, answer the "
    r"following question with no more than three words\.?\s*|The question\s+|Question:\s*|Q:\s*)",
    re.IGNORECASE,
)
VQA_SUFFIXES = re.compile(
    r"\s*(?:\.?\s*A short answer (?:to the question )?is:?|A:?|Short answer:?|(?:Keep|Provide) your answer as short "
    r"as possible\.?|Answer (?:with|using) (?:a single word or phrase|no more than three words)\.?|\.)\s*$",
    re.IGNORECASE,
)
PER_IMAGE = {"caption": 1, "vqa": 2, "refer": 1}
CAPTION_PROMPT = "Describe this aerial image: its land cover, the objects visible and how they lie relative to each other."
ANSWER_FORMAT = {
    "vqa": " Answer briefly.",
    "refer": " Answer as [x0 y0, x1 y1] with coordinates normalised to the image, 0 at the top-left.",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--images-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--images", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=7)
    arguments = parser.parse_args()
    rows = build_rows(arguments.annotations, arguments.images_zip, arguments.output, arguments.images, arguments.seed)
    print(f"vrsbench: {len(rows)} rows")


def build_rows(annotations: Path, images_zip: Path, output: Path, image_count: int, seed: int) -> list[dict]:
    generator = random.Random(seed)
    by_image: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for entry in json.loads(annotations.read_text(encoding="utf-8")):
        match = TAG.match(entry["conversations"][0]["value"])
        if match:
            by_image[entry["image"]][match.group(1)].append(entry)

    with zipfile.ZipFile(images_zip) as archive:
        members = {Path(name).name: name for name in archive.namelist() if name.lower().endswith(".png")}
        candidates = sorted(name for name in by_image if name in members)
        generator.shuffle(candidates)
        chosen = candidates[:image_count]
        images = output / "images"
        images.mkdir(parents=True, exist_ok=True)
        rows: list[dict] = []
        for name in chosen:
            target = images / f"vrsbench_{name}"
            if not target.exists():
                target.write_bytes(archive.read(members[name]))
            for task, cap in PER_IMAGE.items():
                entries = by_image[name].get(task, [])
                generator.shuffle(entries)
                for entry in entries[:cap]:
                    row = _row(entry, task, target.name)
                    if row is not None:
                        rows.append(row)
    generator.shuffle(rows)
    with (output / "vrsbench.train.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def _row(entry: dict, task: str, image_name: str) -> dict | None:
    human = TAG.sub("", entry["conversations"][0]["value"]).strip()
    answer = entry["conversations"][1]["value"].strip()
    if task == "caption":
        prompt, kind = CAPTION_PROMPT, "captioning"
    elif task == "vqa":
        question = VQA_PREFIXES.sub("", human)
        for _ in range(3):
            question = VQA_SUFFIXES.sub("", question).strip()
        question = question.rstrip("?.").strip()
        if not question:
            return None
        prompt = question + "?" + ANSWER_FORMAT["vqa"]
        kind = "binary" if answer.lower() in {"yes", "no"} else "mcq"
    else:
        text = REFERRING_TEXT.search(human)
        box = BOX.search(answer)
        if text is None or box is None:
            return None
        x0, y0, x1, y1 = (int(value) / 100 for value in box.groups())
        prompt = f"Give the bounding box of: {text.group(1).strip().rstrip('.')}." + ANSWER_FORMAT["refer"]
        answer, kind = f"[{x0:.2f} {y0:.2f}, {x1:.2f} {y1:.2f}]", "bounding box"
    return {
        "id": f"vrsbench-{entry['image']}-{task}-{abs(hash(human)) % 10**8}", "source": "vrsbench", "split": "train",
        "category": task, "type": kind, "modality": "aerial", "images": [image_name], "image_notes": [None],
        "prompt": prompt, "answer": answer,
    }


if __name__ == "__main__":
    main()
