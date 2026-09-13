"""The labelled query bank the classifier votes over, and its embeddings, computed once per encoder version.

what  : `LabelledQuery`, `load_bank()`, `load_holdout()`, `EmbeddedBank` and `embed_bank()`.
where : `services/query/classifier.py` at first use; `services/evaluation/intent.py` for the gate.
how   : Two files beside this module. `intent_bank.jsonl` is what the kNN learns from; `intent_holdout.jsonl`
        is what it is scored on and is never embedded into the bank - the split is by hash of the text
        (`training/`-style discipline applied to 450 sentences). Embeddings are cached under the weights
        directory keyed by the SHA-256 of the bank file and the encoder version, so a CLI invocation
        costs one tokeniser pass for the question rather than 215.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.config import settings
from app.constants.intents import Intent
from app.constants.routing import (
    INTENT_BANK_FILENAME,
    INTENT_COMPOUND_FILENAME,
    INTENT_COMPOUND_FRESH_FILENAME,
    INTENT_FRESH_FILENAME,
    INTENT_HOLDOUT_FILENAME,
    QUERY_SPELLINGS,
)
from app.models.encoder import SentenceEncoder
from app.services.query.entities import normalise_query
from app.services.query.math.nearest import normalise_rows

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent


@dataclass(frozen=True, slots=True)
class LabelledQuery:
    query: str
    intent: Intent


@dataclass(frozen=True, slots=True)
class LabelledPlan:
    """A compound request and the ordered intents a plan for it must contain."""

    query: str
    intents: tuple[Intent, ...]


@dataclass(frozen=True, slots=True)
class EmbeddedBank:
    rows: list[LabelledQuery]
    # (n, d) unit vectors, one per row, in row order.
    vectors: np.ndarray
    encoder_version: str

    @property
    def labels(self) -> list[str]:
        return [row.intent.value for row in self.rows]


async def load_bank() -> list[LabelledQuery]:
    return await asyncio.to_thread(_read, _HERE / INTENT_BANK_FILENAME)


async def load_holdout() -> list[LabelledQuery]:
    return await asyncio.to_thread(_read, _HERE / INTENT_HOLDOUT_FILENAME)


async def load_fresh() -> list[LabelledQuery]:
    return await asyncio.to_thread(_read, _HERE / INTENT_FRESH_FILENAME)


async def load_compound() -> list[LabelledPlan]:
    return await asyncio.to_thread(_read_plans, _HERE / INTENT_COMPOUND_FILENAME)


async def load_compound_fresh() -> list[LabelledPlan]:
    return await asyncio.to_thread(_read_plans, _HERE / INTENT_COMPOUND_FRESH_FILENAME)


async def embed_bank(encoder: SentenceEncoder, rows: list[LabelledQuery] | None = None) -> EmbeddedBank:
    """The bank as unit vectors, from the disk cache when the bank and the encoder are unchanged."""
    rows = rows if rows is not None else await load_bank()
    # The bank is embedded as the classifier will see a question: normalised. The spellings table is in
    # the key so a change to it re-embeds rather than serving vectors of text the cues no longer see.
    texts = [normalise_query(row.query) for row in rows]
    material = "\n".join(f"{row.intent.value}\t{text}" for row, text in zip(rows, texts, strict=True)) + encoder.version + repr(QUERY_SPELLINGS)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    cache = settings.model_weights_path / "intent-bank" / f"{digest}.npy"
    if cache.exists():
        vectors = await asyncio.to_thread(np.load, cache)
    else:
        vectors = await asyncio.to_thread(encoder.encode, texts)
        vectors = normalise_rows(vectors.astype(np.float32))
        await asyncio.to_thread(_save, cache, vectors)
        logger.info("intent bank embedded", extra={"rows": len(rows), "cache": str(cache)})
    return EmbeddedBank(rows, vectors, encoder.version)


def _read(path: Path) -> list[LabelledQuery]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [LabelledQuery(row["query"], Intent(row["intent"])) for row in rows]


def _read_plans(path: Path) -> list[LabelledPlan]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [LabelledPlan(row["query"], tuple(Intent(name) for name in row["intents"])) for row in rows]


def _save(path: Path, vectors: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, vectors)
