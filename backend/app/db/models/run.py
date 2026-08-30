"""One execution of the analysis pipeline: the question asked, the intent it routed to, and how it ended.

what  : The `runs` table. The parent of every trace step, claim and piece of evidence produced by one
        invocation of a LangGraph pipeline graph.
where : Created when `POST /investigations/{id}/runs` opens its stream, and in Phase 1 by `aeris investigate`.
        Mirrors the frontend's `analysisRunRequestSchema` inputs and its `run-start` / `run-complete` events.
how   : **`cancelled` is not `failed`.** Barge-in cancels a run mid-flight (`api-contract.md` §5), and the
        interface must not present a deliberate interruption as an incident. The status column carries the
        distinction; nothing infers it from whether `completed_at` is set.

        **`confidence` is nullable and is never defaulted to zero** (`api-contract.md` §1 rule 2). `NULL`
        means AERIS declined to assert one, which renders as a refusal card; `0.0` would be the much
        stronger claim that it looked and found no confidence at all.

        **`insufficient_evidence` is stored on a successful run.** A run that looked honestly and could not
        establish an answer is a product feature (PDF p.38), not an error, so it carries a reason and its
        remedies as JSONB while `status` stays `complete`.

        `intent` is nullable because it is not known until the routing node has run. A run that fails during
        query interpretation genuinely has no intent, and writing a placeholder would make "we never got
        that far" indistinguishable from "we classified it as scene VQA".
"""

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.geo import POLYGON_GEOMETRY, STORAGE_SRID
from app.constants.intents import Intent
from app.constants.statuses import RunStatus
from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH, IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column, wire_enum


class Run(Base, TimestampMixin):
    """One pipeline execution against one investigation."""

    __tablename__ = "runs"

    id: Mapped[str] = identifier_column(IdentifierPrefix.RUN)

    investigation_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )

    query: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Set by the routing node. NULL until then - see the module docstring.
    intent: Mapped[Intent | None] = mapped_column(wire_enum(Intent), nullable=True)

    status: Mapped[RunStatus] = mapped_column(
        wire_enum(RunStatus),
        nullable=False,
        default=RunStatus.RUNNING,
    )

    # The region the operator drew to scope the question, or NULL for the whole scene.
    region_bounds: Mapped[str | None] = mapped_column(
        Geometry(geometry_type=POLYGON_GEOMETRY, srid=STORAGE_SRID, spatial_index=False),
        nullable=True,
    )

    # Set when the run was launched by the autonomous macro or by a named operation rather than typed.
    plan_id: Mapped[str | None] = mapped_column(String(IDENTIFIER_MAXIMUM_LENGTH), nullable=True)
    operation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_duration_ms: Mapped[int | None] = mapped_column(nullable=True)

    # NULL means "declined to assert". Never 0.0 by default.
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    # `{reason, remedies[]}` on a *successful* run that could not establish an answer.
    insufficient_evidence: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    # Populated for `failed` and for `cancelled`, where it carries the cancellation reason rather than a
    # fault - the frontend shows it as context, not as an incident.
    error_message: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # The LangGraph thread this run's checkpoints are written under. Holding it here is what makes
    # `aeris investigate --resume <run_id>` possible: the checkpointer is keyed by thread, and without the
    # mapping a resumable run could not be found from its id (ADR-002).
    checkpoint_thread_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    __table_args__ = (
        # The run list for one investigation, newest first. Both columns, because a run list is always
        # scoped to an investigation and never global.
        Index("ix_runs_investigation_id_started_at", "investigation_id", text("started_at DESC")),
    )
