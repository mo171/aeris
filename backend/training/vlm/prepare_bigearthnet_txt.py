"""Builds the BigEarthNet.txt instruction set the LoRA is trained on: rendered S2/S1 pictures plus prompt/answer rows, balanced and licence-gated.

what  : `python -m training.vlm.prepare_bigearthnet_txt --output data/training/vlm` writes
        `images/<patch>_s2.png`, `images/<s1>_s1.png`, and `bigearthnet_txt.{train,validation,test,bench}.jsonl`.
where : Run on the laptop; the output directory is uploaded to Kaggle as a dataset and read by
        `notebooks/08_vlm_finetuning/03_train_lora.ipynb`. The same renders are what `aeris` will feed the
        model at inference (`services/vlm/math/rendering.py`), so training and serving see the same pixels.
how   : Images come from the BigEarthNet v2.0 Lithuania-summer LMDB (8,775 patches; the full archive is
        145 GB) joined to BigEarthNet.txt on `patch_id`. Decisions, each recorded in the teaching notebook:

        - **Country, season and climate zone are dropped**: in a one-country one-season subset they are
          constants, and a model trained on them learns "Lithuania" as the answer to every image.
        - **Balanced per (category, type)**: the raw file is 38% binary and 34% MCQ over 1.4 M rows per
          category; a cap per bucket keeps captions and boxes from being drowned.
        - **Three modalities per patch**: S2 true colour, S1 false colour, and the pair shown together with
          a note saying which is which. Roughly 55 / 15 / 30 for questions; boxes on S2 only, because the
          annotation was drawn on the optical patch.
        - **Deterministic stretches**, fixed rather than per-image percentiles, so the same ground renders
          the same bytes on any machine: S2 reflectance 0-3000 (L2A x10,000), S1 VV -25..0 dB, VH -30..-5 dB,
          VV/VH ratio 0..15 dB.
        - **Licence gate**: `require_trainable()` refuses to write the train split until the record says a
          human read the terms (CDLA-Permissive-1.0).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from PIL import Image

from app.constants.datasets import DatasetId, DatasetSplit
from app.constants.vlm import BEN_TXT_CONSTANT_CATEGORIES, BEN_TXT_TRAINED_CATEGORIES
from app.services.datasets.catalogue import require_trainable
from app.services.datasets.loader import split_directory
from app.prompts.vlm import SAR_IMAGE_NOTE
from app.services.vlm.math.rendering import render_s1_false_colour, render_s2_true_colour

logger = logging.getLogger(__name__)

LMDB_REPOSITORY = "hackelle/BigEarthNetV2-Lithuania-Summer-LMDB"
LMDB_NAME = "BENv2_lithuania_summer.lmdb"
LMDB_METADATA = "metadata_lithuania_summer.parquet"

# Rows kept per (category, type) bucket in the training split. ~10 buckets -> ~30k examples: one epoch is
# an evening on a T4, and more rows of the same templates teach nothing new.
TRAIN_CAP_PER_BUCKET = 3_000
EVAL_CAP_PER_BUCKET = 150
MODALITY_WEIGHTS = {"s2": 0.55, "pair": 0.30, "s1": 0.15}

# How each type is asked, so the answer format is unambiguous and the same at inference.
ANSWER_FORMAT = {
    "binary": " Answer yes or no.",
    "mcq": " Answer with the letter only.",
    "bounding box": " Answer as [x0 y0, x1 y1] with coordinates normalised to the image, 0 at the top-left.",
    "captioning": "",
}
PAIR_NOTE = "The first image is the optical (Sentinel-2 true colour) view; the second is the SAR view of the same ground. "

# Captions open with the country, the season and the climate zone - the three constants of a one-country
# one-season subset. Dropping the *categories* was not enough: the first adapter learned to open every
# caption with "captured during the summer in Lithuania" (10 of 10 on the bench rows), which is exactly
# the reflex a Cartosat scene of Gujarat must not trigger. The clauses are scrubbed from the target text.
CAPTION_SCRUBS = (
    re.compile(r",\s*captured (?:during|in) [^,]*?(?:season|summer|winter|spring|fall|autumn)[^,]*,"),
    re.compile(r",\s*captured in [A-Z][A-Za-z ]+,"),
    re.compile(r"\s*(?:set |located |situated )?within the \"[^\"]*\" climate zone"),
    re.compile(r"\s*in the \"[^\"]*\" climate zone"),
)


LEAK_WORDS = re.compile(
    r"(?:summer|winter|spring|fall|autumn|climate zone|Lithuania|Lithuanian|Finland|Finnish|Ireland|Irish|Austria|"
    r"Austrian|Serbia|Serbian|Portugal|Portuguese|Belgium|Belgian|Luxembourg|Switzerland|Swiss|Kosovo|Slovenia|Slovenian|"
    r"Latvia|Latvian|Estonia|Estonian|Croatia|Croatian|Slovakia|Slovak)",
    re.IGNORECASE,
)


def scrub_caption(text: str) -> str:
    """The caption without the openers that name the country, the season or the climate zone; a later
    sentence that still names one is dropped whole, and a caption left with nothing is dropped by the
    caller."""
    for pattern in CAPTION_SCRUBS:
        text = pattern.sub(lambda match: "," if match.group(0).startswith(",") and match.group(0).endswith(",") else "", text)
    text = text.replace("This satellite image, showcases", "This satellite image showcases").replace("This satellite image, presents", "This satellite image presents")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    kept = [s for s in sentences if not LEAK_WORDS.search(s)]
    return re.sub(r"\s{2,}", " ", " ".join(kept)).replace(" ,", ",").replace(",.", ".").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=Path("data/training/vlm"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--skip-licence-gate", action="store_true", help="Evaluation splits only; never for training.")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not arguments.skip_licence_gate:
        require_trainable(DatasetId.BIGEARTHNET_TXT, DatasetSplit.ALL)

    text = pd.read_parquet(split_directory(DatasetId.BIGEARTHNET_TXT, DatasetSplit.ALL) / "BigEarthNet.txt.parquet")
    lmdb_root = _lmdb_snapshot()
    metadata = pd.read_parquet(lmdb_root / LMDB_METADATA)
    usable = metadata[~metadata.contains_cloud_or_shadow & ~metadata.contains_seasonal_snow]
    rows = text[text.patch_id.isin(set(usable.patch_id)) & text.category.isin(BEN_TXT_TRAINED_CATEGORIES)]
    logger.info("rows on usable Lithuania patches: %d of %d; dropped constant categories %s",
                len(rows), len(text), sorted(BEN_TXT_CONSTANT_CATEGORIES))

    generator = random.Random(arguments.seed)
    images = arguments.output / "images"
    images.mkdir(parents=True, exist_ok=True)
    rendered: set[str] = set()
    counts: Counter[str] = Counter()

    import lmdb
    from safetensors.numpy import load as load_safetensors

    environment = lmdb.open(str(lmdb_root / LMDB_NAME), readonly=True, lock=False, readahead=False)
    with environment.begin(write=False) as transaction:
        for split, cap in (("train", TRAIN_CAP_PER_BUCKET), ("validation", EVAL_CAP_PER_BUCKET),
                           ("test", EVAL_CAP_PER_BUCKET), ("bench", None)):
            if arguments.skip_licence_gate and split == "train":
                continue
            subset = rows[rows.split == split]
            selected = _balanced(subset, cap, generator) if cap else subset
            with (arguments.output / f"bigearthnet_txt.{split}.jsonl").open("w", encoding="utf-8") as handle:
                for record in selected.itertuples(index=False):
                    example = _example(record, generator, images, rendered, transaction, load_safetensors)
                    handle.write(json.dumps(example, ensure_ascii=False) + "\n")
                    counts[f"{split}/{record.category}/{record.type}/{example['modality']}"] += 1
            logger.info("%s: %d rows", split, len(selected))
    (arguments.output / "counts.json").write_text(json.dumps(dict(sorted(counts.items())), indent=2), encoding="utf-8")
    logger.info("wrote %d images to %s", len(rendered), images)


def _lmdb_snapshot() -> Path:
    from huggingface_hub import snapshot_download

    from app.config import settings

    return Path(snapshot_download(LMDB_REPOSITORY, repo_type="dataset", cache_dir=settings.model_weights_path))


def _balanced(rows: pd.DataFrame, cap: int, generator: random.Random) -> pd.DataFrame:
    parts = []
    for _, bucket in rows.groupby(["category", "type"]):
        parts.append(bucket.sample(n=min(cap, len(bucket)), random_state=generator.randrange(1 << 30)))
    return pd.concat(parts).sample(frac=1.0, random_state=generator.randrange(1 << 30))


def _example(record, generator, images: Path, rendered: set[str], transaction, load_safetensors) -> dict | None:
    kind = record.type
    modality = "s2" if kind == "bounding box" else generator.choices(list(MODALITY_WEIGHTS), weights=list(MODALITY_WEIGHTS.values()))[0]
    s2_path = images / f"{record.patch_id}_s2.png"
    s1_path = images / f"{record.s1_name}_s1.png"
    if modality in {"s2", "pair"} and record.patch_id not in rendered:
        bands = load_safetensors(transaction.get(record.patch_id.encode()))
        Image.fromarray(render_s2_true_colour(bands["B04"], bands["B03"], bands["B02"])).save(s2_path)
        rendered.add(record.patch_id)
    if modality in {"s1", "pair"} and record.s1_name not in rendered:
        bands = load_safetensors(transaction.get(record.s1_name.encode()))
        # BigEarthNet v2.0 stores S1 already in dB (measured: VV median -18, VH -27 on the first patch).
        Image.fromarray(render_s1_false_colour(bands["VV"], bands["VH"], already_decibels=True)).save(s1_path)
        rendered.add(record.s1_name)

    prompt = (record.input if kind != "captioning" else "Describe this satellite image: its land cover, the "
              "features visible and how they lie relative to each other.") + ANSWER_FORMAT[kind]
    answer = scrub_caption(str(record.output).strip()) if kind == "captioning" else str(record.output).strip()
    if not answer:
        return None
    if modality == "s2":
        image_list, notes = [s2_path.name], [None]
    elif modality == "s1":
        image_list, notes = [s1_path.name], [SAR_IMAGE_NOTE]
    else:
        image_list, notes = [s2_path.name, s1_path.name], [PAIR_NOTE, SAR_IMAGE_NOTE]
    return {
        "id": str(record.ID), "source": "bigearthnet-txt", "split": record.split, "category": record.category,
        "type": kind, "modality": modality, "images": image_list, "image_notes": notes,
        "prompt": prompt, "answer": answer,
    }


if __name__ == "__main__":
    main()
