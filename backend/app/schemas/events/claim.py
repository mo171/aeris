"""Carries one validated assertion - with the number it rests on, the evidence behind it, and the model that made it.

what  : `ClaimEvent`, `Claim` and `ClaimMetric`. Mirrors `claimSchema` in `evidence.schema.ts`.
where : Emitted by the S15 node through `services/evidence/builder.py`; read back by S16 to speak, by
        S19 to record, and by the frontend's answer panel. From 1.7 the constrained generator phrases
        these; it never produces one.
how   : A claim is the unit of trust in this product (PDF §20): every numeric claim traceable to a
        computation, every spatial claim to pixels. The model enforces the parts of that a shape can:

        - **`evidenceIds` may be empty, and an empty list is a statement** - "this claim is unsupported and
          says so". It is never omitted.
        - **`metrics` carry `precision`**, how many decimals the figure is meaningful to, so a model's
          noise is never rendered as precision. The underlying value keeps its full float; the frontend
          rounds for display and speech rounds further (`api-contract.md` §5).
        - **`confidence` is `float | None`**, and `None` is a real answer (§1 rule 2).
        - **`isPrimary`** marks the headline claim. Exactly one per run; the builder, not the model, holds
          that invariant, because the model sees one claim at a time.

        `modelId` and `modelVersion` are the fleet vocabulary (`constants/model_ids.py`) and the version the
        engine declares for itself (`constants/spectral.py`). A claim made under a different version is a
        different measurement, which is why the version travels with the claim rather than being looked up.
"""

from typing import Literal

from pydantic import Field

from app.constants.events import AnalysisEventType
from app.constants.evidence import ClaimKind, MetricDirection
from app.constants.model_ids import ModelId
from app.lib.responses import CamelCaseModel
from app.schemas.events.base import StreamEvent


class ClaimMetric(CamelCaseModel):
    """One number a claim rests on, in the unit it was measured in."""

    label: str = Field(min_length=1)
    value: float
    unit: str
    direction: MetricDirection
    precision: int = Field(ge=0, le=4)


class Claim(CamelCaseModel):
    """One assertion, its numbers, its evidence and its provenance."""

    id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    kind: ClaimKind
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metrics: list[ClaimMetric] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    model_id: ModelId
    model_version: str = Field(min_length=1)
    trace_step_id: str = Field(min_length=1)
    is_primary: bool = False


class ClaimEvent(StreamEvent):
    """`claim`. One validated claim, as soon as it exists."""

    type: Literal[AnalysisEventType.CLAIM] = AnalysisEventType.CLAIM
    run_id: str
    claim: Claim
