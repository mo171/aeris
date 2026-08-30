"""A statement AERIS is prepared to make, with the evidence, the model and the stage that produced it attached.

what  : The `claims` table. One row per assertion in an answer, each pointing at the evidence that supports
        it, the model and version that produced it, and the trace step it came out of.
where : Written by the evidence-generation and synthesis nodes, emitted as `claim` events, rendered as claim
        cards, and quoted in reports. Mirrors the frontend's `claimSchema`.
how   : **A claim is not a sentence, it is a sentence plus its receipts.** Every column after `text` exists so
        that "why do you say that" is answerable without re-running anything: `evidence_ids` says what was
        seen, `model_id` and `model_version` say what saw it, `trace_step_id` says at which stage.

        **`evidence_ids` may be empty, and that means something.** An empty list is an unsupported claim, and
        the frontend renders it as one. It is not an error and it is not scrubbed - a system that silently
        dropped its unsupported statements would be hiding exactly what an auditor is looking for.

        **`metrics` is JSONB, and carries `precision`.** A metric is `{label, value, unit, direction,
        precision}`, and `precision` is how many decimals the figure is *meaningful* to. Rendering a model's
        noise as significant digits is a way of lying with true numbers, so the producer states the precision
        and the frontend obeys it.

        **`is_primary` is unique per run.** Exactly one headline claim; the rest are supporting detail. A run
        with two headlines has no headline, so a partial unique index enforces it rather than the synthesis
        node being trusted to.

        The reference to evidence is JSONB rather than an association table on purpose: the list is written
        once with the claim, read whole, and never queried across. A join table would add a migration and a
        join for a list that is always fetched in full alongside its owner.
"""

from typing import Any

# Imported under an alias: this model has a column called `text`, which shadows `sqlalchemy.text`
# inside the class body. The column name is fixed by the wire contract (`claimSchema.text`), so the
# import moves rather than the field.
from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.evidence import ClaimKind
from app.constants.model_ids import ModelId
from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH, IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column, wire_enum


class Claim(Base, TimestampMixin):
    """One assertion in an answer, with its provenance."""

    __tablename__ = "claims"

    id: Mapped[str] = identifier_column(IdentifierPrefix.CLAIM)

    run_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    text: Mapped[str] = mapped_column(String(2048), nullable=False)
    kind: Mapped[ClaimKind] = mapped_column(wire_enum(ClaimKind), nullable=False)

    confidence: Mapped[float | None] = mapped_column(nullable=True)

    # `[{label, value, unit, direction, precision}]`. See the module docstring on `precision`.
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(nullable=False, default=list)

    # Empty means unsupported, and is rendered as such rather than hidden.
    evidence_ids: Mapped[list[str]] = mapped_column(nullable=False, default=list)

    model_id: Mapped[ModelId] = mapped_column(wire_enum(ModelId), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)

    trace_step_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("trace_steps.id", ondelete="CASCADE"),
        nullable=False,
    )

    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="confidence_is_a_fraction_or_null",
        ),
        Index("ix_claims_run_id", "run_id"),
        # Exactly one headline per run. Partial, so the many supporting claims are unconstrained.
        Index(
            "uq_claims_one_primary_per_run",
            "run_id",
            unique=True,
            postgresql_where=sql_text("is_primary"),
        ),
    )
