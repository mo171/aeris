"""Compares two models' per-row predictions on the same rows: per-type accuracy, the paired count of who-fixed-what, and a McNemar test.

what  : `python -m training.vlm.compare --base <base.jsonl> --adapter <adapter.jsonl>`; `compare()` for notebook 04.
where : After `aeris models evaluate --model rs-vlm --file <rows> --predictions <out>` has been run once
        with the base and once with the adapter on the *same* file and limit.
how   : Means hide the story. Two models can both score 60% while agreeing on nothing; what proves an
        adapter is better is the *paired* count - rows the adapter got right that the base got wrong
        (b) against the reverse (c) - and McNemar's exact test on that pair: the p-value is the chance of
        a split at least as lopsided as b:c if the two models were really equally good. Captions are
        compared on ROUGE-L difference per row rather than hits. Calibration is reported as the gap
        between mean stated confidence and accuracy, per model: an adapter that is more accurate but
        more over-confident has traded one problem for another.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from app.services.evaluation.math.text_scores import rouge_l


def read(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["id"]: row for row in rows}


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value: binomial test of b successes in b + c trials at p = 0.5."""
    from scipy.stats import binomtest

    if b + c == 0:
        return 1.0
    return float(binomtest(b, b + c, 0.5).pvalue)


def compare(base_path: Path, adapter_path: Path) -> list[dict]:
    base, adapter = read(base_path), read(adapter_path)
    shared = [key for key in base if key in adapter]
    by_type: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for key in shared:
        by_type[base[key]["type"]].append((base[key], adapter[key]))

    table: list[dict] = []
    for kind, pairs in sorted(by_type.items()):
        if kind == "captioning":
            base_scores = [rouge_l(b["prediction"], b["reference"]) for b, _ in pairs]
            adapter_scores = [rouge_l(a["prediction"], a["reference"]) for _, a in pairs]
            better = sum(1 for x, y in zip(base_scores, adapter_scores, strict=True) if y > x)
            worse = sum(1 for x, y in zip(base_scores, adapter_scores, strict=True) if y < x)
            table.append({
                "type": kind, "n": len(pairs), "base": sum(base_scores) / len(pairs), "adapter": sum(adapter_scores) / len(pairs),
                "adapter_better_rows": better, "adapter_worse_rows": worse, "p_value": mcnemar_exact(better, worse),
                "base_confidence": sum(b["confidence"] for b, _ in pairs) / len(pairs),
                "adapter_confidence": sum(a["confidence"] for _, a in pairs) / len(pairs),
            })
            continue
        b = sum(1 for x, y in pairs if y["hit"] and not x["hit"])
        c = sum(1 for x, y in pairs if x["hit"] and not y["hit"])
        table.append({
            "type": kind, "n": len(pairs),
            "base": sum(1 for x, _ in pairs if x["hit"]) / len(pairs), "adapter": sum(1 for _, y in pairs if y["hit"]) / len(pairs),
            "adapter_better_rows": b, "adapter_worse_rows": c, "p_value": mcnemar_exact(b, c),
            "base_confidence": sum(x["confidence"] for x, _ in pairs) / len(pairs),
            "adapter_confidence": sum(y["confidence"] for _, y in pairs) / len(pairs),
        })
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    arguments = parser.parse_args()
    rows = compare(arguments.base, arguments.adapter)
    print(f"{'type':<14}{'n':>5}{'base':>8}{'adapter':>9}{'delta':>8}{'fixed':>7}{'broken':>8}{'p':>9}{'conf base':>11}{'conf adpt':>11}")
    for row in rows:
        print(
            f"{row['type']:<14}{row['n']:>5}{row['base']:>8.3f}{row['adapter']:>9.3f}{row['adapter'] - row['base']:>+8.3f}"
            f"{row['adapter_better_rows']:>7}{row['adapter_worse_rows']:>8}{row['p_value']:>9.4f}"
            f"{row['base_confidence']:>11.3f}{row['adapter_confidence']:>11.3f}"
        )


if __name__ == "__main__":
    main()
