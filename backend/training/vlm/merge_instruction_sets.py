"""Joins the per-dataset instruction files into the `train.jsonl` / `validation.jsonl` the Kaggle notebook reads, and says what is in them.

what  : `python -m training.vlm.merge_instruction_sets --output data/training/vlm` writes `train.jsonl`,
        `validation.jsonl` and `manifest.json` from every `<source>.{train,validation}.jsonl` present.
where : After the `prepare_*.py` scripts, before `kaggle.py upload-data`.
how   : Concatenate and shuffle with a fixed seed; nothing is re-balanced here - each prep script already
        capped its own buckets, and the manifest records the per-source, per-type counts so the training
        record can name exactly what the adapter saw. Test and bench files are left as they are: they are
        scored one file at a time, never merged, so a number is always attributable to one benchmark.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=Path("data/training/vlm"))
    parser.add_argument("--seed", type=int, default=7)
    arguments = parser.parse_args()
    generator = random.Random(arguments.seed)
    manifest: dict[str, dict[str, int]] = {}

    for split in ("train", "validation"):
        rows: list[str] = []
        counts: Counter[str] = Counter()
        for file in sorted(arguments.output.glob(f"*.{split}.jsonl")):
            if file.name in {f"{split}.jsonl"}:
                continue
            for line in file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(line)
                    row = json.loads(line)
                    counts[f"{row['source']}/{row['type']}/{row['modality']}"] += 1
        generator.shuffle(rows)
        (arguments.output / f"{split}.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
        manifest[split] = dict(sorted(counts.items()))
        print(f"{split}: {len(rows)} rows from {len(counts)} buckets")
    (arguments.output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
