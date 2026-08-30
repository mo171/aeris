"""One stage of S1-S20 inside a run: what ran, how long it took, which model did it, and what it left behind.

what  : The `trace_steps` table. The persisted form of the `trace-step` stream event, and the row the
        execution spine draws.
where : Written by every pipeline node as it enters and leaves. Read by the execution trace, by the report's
        provenance section, and by any question of the form "why does this claim say what it says".
how   : **This table is the provenance record**, and provenance that is reconstructed after the fact is not
        provenance (`architecture-context.md` §8 rule 12). A step is written when it starts and updated when
        it finishes, so a run that crashed still shows exactly how far it got and which stage was in flight.

        `stage_code` carries `S1`-`S20` and nothing else. The label and description live in the frontend's
        `pipeline-stages.ts`; sending "Specialist analysis" over the wire would put display copy in the
        database and require a deploy to reword it (`code-standards.md` §5).

        `artefact_object_key` is the intermediate this stage produced - the cloud mask, the registration
        residual, the index map - for the five stages that produce one. It is what makes a trace step
        clickable, and PDF §21.2 already obliges us to retain it, so surfacing it costs a key we hold.

        `sequence` exists because `created_at` is not a safe ordering key. Several stages can be written
        inside the same millisecond, and the spine renders in pipeline order, not in clock order.
"""

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.model_ids import ModelId
from app.constants.stages import PipelineStage
from app.constants.statuses import TraceStepState
from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH, IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column, wire_enum


class TraceStep(Base, TimestampMixin):
    """One S1-S20 stage execution within one run."""

    __tablename__ = "trace_steps"

    id: Mapped[str] = identifier_column(IdentifierPrefix.TRACE_STEP)

    run_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Position in the run, from zero. The spine's ordering key - see the module docstring.
    sequence: Mapped[int] = mapped_column(nullable=False)

    stage_code: Mapped[PipelineStage] = mapped_column(wire_enum(PipelineStage), nullable=False)

    state: Mapped[TraceStepState] = mapped_column(
        wire_enum(TraceStepState),
        nullable=False,
        default=TraceStepState.PENDING,
    )

    # One line of what this stage actually did with this data - "Masked 12.4% cloud over the northern third".
    # Written for an operator reading the spine, so it names quantities rather than function calls.
    detail: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # NULL until the step completes. The `running` -> `completed` transition carrying this number is the
    # execution-trace UI (`api-contract.md` §3.1).
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)

    # NULL for the stages no model serves - tiling, provenance logging, the final response.
    model_id: Mapped[ModelId | None] = mapped_column(wire_enum(ModelId), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # The inspectable intermediate, for the artefact-producing stages. NULL for the rest.
    artefact_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # The layer that draws that artefact, so clicking a step raises the right thing on the scene.
    artefact_layer_id: Mapped[str | None] = mapped_column(String(IDENTIFIER_MAXIMUM_LENGTH), nullable=True)

    __table_args__ = (
        # A run's steps are always read in full and in order.
        Index("ix_trace_steps_run_id_sequence", "run_id", "sequence"),
        # Two steps at the same position in one run is a producer bug, and it is worth catching at the
        # database rather than discovering as a spine that renders two rows on top of each other.
        UniqueConstraint("run_id", "sequence", name="one_step_per_position"),
    )
