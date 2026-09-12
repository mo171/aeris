"""Combines per-stage confidences into the one the run reports, by a rule that is named and recorded rather than implied.

what  : `aggregate_confidence()`, the `minimum-of-stated` rule (`constants/evidence.py`).
where : Called by the S18 node through `asyncio.to_thread`; the rule's name is written into the
        provenance record by S19 (PDF §21.2: "aggregation rule recorded, not just shown").
how   : **Pure, sync.** The run is as confident as its least confident stage that said anything. A stage
        that declines to state a confidence - the deterministic engines of 1.4 - neither raises nor
        lowers the result; it is absent, not zero (`architecture-context.md` §8 rule 10). When no stage
        states one, the run has none, and `None` is the answer rather than a default.

        Minimum rather than a product or a mean, because the chain is serial: a claim built on a 0.6 mask
        is not more than 0.6 certain because the arithmetic afterwards was exact. Phase 1.6 adds model
        scores and 1.7 the validation checks the PDF names; the rule's name is what lets a later record be
        told apart from this one.
"""

from collections.abc import Iterable


def aggregate_confidence(stated: Iterable[float | None]) -> float | None:
    """The weakest stated confidence, or `None` when nothing was stated."""
    values = [value for value in stated if value is not None]
    if not values:
        return None
    for value in values:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"A confidence is on [0, 1]; got {value}.")
    return min(values)
