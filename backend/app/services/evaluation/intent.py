"""Scores the intent classifier on the held-out questions - the 1.8 gate - and on each half of the cascade alone.

what  : `IntentReport`, `IntentError`, `evaluate_intents()` for one intent per question; `PlanReport`,
        `evaluate_plans()` for compound requests scored as ordered intent sequences.
where : `aeris route --evaluate`; the integration test asserts the gate from the same function.
how   : The held-out file is never in the bank the kNN votes over, so the number is out-of-sample for the
        kNN. It is *not* out-of-author: bank and held-out were written by the same hand, and a
        classifier that only had to learn one author's phrasing will score higher here than on operators'
        questions. The ablation is the honest part: `rules` (no encoder) says how far the cues alone
        reach; `knn` (no cues) says what the bank alone does; `cascade` is what ships. Every error is
        returned with the method that made it, so a wrong rule is found by name.
"""

import logging
from collections import Counter
from dataclasses import dataclass

from app.constants.intents import Intent
from app.models.encoder import SentenceEncoder
from app.services.query.bank import EmbeddedBank, LabelledPlan, LabelledQuery, load_holdout
from app.services.query.classifier import Arbiter, classify_intent

logger = logging.getLogger(__name__)

RULES_ONLY = "rules"
KNN_ONLY = "knn"
CASCADE = "cascade"


@dataclass(frozen=True, slots=True)
class IntentError:
    query: str
    expected: Intent
    predicted: Intent
    method: str
    rule: str | None


@dataclass(frozen=True, slots=True)
class IntentReport:
    configuration: str
    samples: int
    accuracy: float
    per_intent: dict[Intent, tuple[int, int]]
    # How many decisions each method made: rule / knn / default.
    methods: dict[str, int]
    uncertain: int
    errors: tuple[IntentError, ...]


async def evaluate_intents(
    *, encoder: SentenceEncoder | None, bank: EmbeddedBank | None, configuration: str = CASCADE,
    rows: list[LabelledQuery] | None = None, arbiter: Arbiter | None = None,
) -> IntentReport:
    rows = rows if rows is not None else await load_holdout()
    hits: Counter[Intent] = Counter()
    totals: Counter[Intent] = Counter()
    methods: Counter[str] = Counter()
    uncertain = 0
    errors: list[IntentError] = []
    for row in rows:
        decision = await classify_intent(
            row.query,
            encoder=None if configuration == RULES_ONLY else encoder,
            bank=None if configuration == RULES_ONLY else bank,
            use_rules=configuration != KNN_ONLY, arbiter=arbiter,
        )
        totals[row.intent] += 1
        methods[decision.method] += 1
        uncertain += decision.uncertain
        if decision.intent == row.intent:
            hits[row.intent] += 1
        else:
            errors.append(IntentError(row.query, row.intent, decision.intent, decision.method, decision.rule))
    accuracy = sum(hits.values()) / len(rows) if rows else 0.0
    return IntentReport(
        configuration, len(rows), accuracy, {intent: (hits[intent], totals[intent]) for intent in Intent},
        dict(methods), uncertain, tuple(errors),
    )


@dataclass(frozen=True, slots=True)
class PlanError:
    query: str
    expected: tuple[Intent, ...]
    predicted: tuple[Intent, ...]
    clauses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PlanReport:
    samples: int
    # Share of requests whose ordered intent sequence matched exactly.
    exact: float
    # Share of expected steps found in the predicted sequence, in order (a lenient credit for partial plans).
    steps_found: float
    errors: tuple[PlanError, ...]


async def evaluate_plans(*, encoder: SentenceEncoder | None, bank: EmbeddedBank | None, rows: list[LabelledPlan], arbiter: Arbiter | None = None) -> PlanReport:
    """Compound requests: the ordered intents the plan must contain."""
    from app.agents.router import route_plan

    exact = 0
    found = 0
    expected_total = 0
    errors: list[PlanError] = []
    for row in rows:
        plan = await route_plan(row.query, encoder=encoder, bank=bank, arbiter=arbiter)
        predicted = plan.intents
        if predicted == row.intents:
            exact += 1
        else:
            errors.append(PlanError(row.query, row.intents, predicted, tuple(clause.text for clause in plan.clauses)))
        expected_total += len(row.intents)
        cursor = 0
        for intent in row.intents:
            while cursor < len(predicted) and predicted[cursor] != intent:
                cursor += 1
            if cursor < len(predicted):
                found += 1
                cursor += 1
    return PlanReport(len(rows), exact / len(rows) if rows else 0.0, found / expected_total if expected_total else 0.0, tuple(errors))
