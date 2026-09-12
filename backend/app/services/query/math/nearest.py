"""Weighted k-nearest-neighbour voting over unit vectors - the arithmetic under intent classification.

what  : `Vote` and `nearest_vote()`; `normalise_rows()`.
where : `services/query/classifier.py`. Sync and pure, like every `math/` module.
how   : Cosine similarity is a dot product once the rows are unit length. The k most similar labelled
        rows vote, each with weight equal to its similarity (a neighbour at 0.9 outweighs one at 0.6),
        restricted to `candidates` when a rule has already narrowed the family. Confidence is the winner's
        share of the total weight; margin is its lead over the runner-up - a margin near zero is two
        intents the bank cannot tell apart for this wording, which is worth saying rather than hiding.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class Vote:
    label: str
    # Winner's share of the summed neighbour weight, in [0, 1].
    confidence: float
    # Winner's share minus the runner-up's; 1.0 when every neighbour agreed.
    margin: float
    # `(row index, similarity)` of the neighbours consulted, most similar first.
    neighbours: tuple[tuple[int, float], ...]


def normalise_rows(matrix: np.ndarray) -> np.ndarray:
    """Every row to unit length; a zero row stays zero rather than becoming NaN."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0.0, 1.0, norms)


def nearest_vote(
    query: np.ndarray, bank: np.ndarray, labels: list[str], k: int, candidates: frozenset[str] | None = None
) -> Vote:
    """The label the `k` most similar bank rows vote for. `bank` rows and `query` are unit vectors."""
    if bank.shape[0] == 0:
        raise ValueError("an empty bank cannot vote")
    allowed = np.ones(bank.shape[0], dtype=bool)
    if candidates is not None:
        allowed = np.fromiter((label in candidates for label in labels), dtype=bool, count=len(labels))
        if not allowed.any():
            raise ValueError(f"no bank row carries any of {sorted(candidates)}")
    similarity = bank @ query
    similarity = np.where(allowed, similarity, -np.inf)
    order = np.argsort(-similarity)[: min(k, int(allowed.sum()))]

    weights: dict[str, float] = {}
    for index in order:
        # A similarity below zero is an anti-vote nobody meant; clamp so a lone far neighbour cannot win.
        weight = max(float(similarity[index]), 0.0)
        weights[labels[index]] = weights.get(labels[index], 0.0) + weight
    total = sum(weights.values())
    ranked = sorted(weights.items(), key=lambda item: -item[1])
    if total == 0.0:
        return Vote(ranked[0][0], 0.0, 0.0, tuple((int(i), float(similarity[i])) for i in order))
    top = ranked[0][1] / total
    second = ranked[1][1] / total if len(ranked) > 1 else 0.0
    return Vote(ranked[0][0], top, top - second, tuple((int(i), float(similarity[i])) for i in order))
