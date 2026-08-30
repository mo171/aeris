"""A georeferenced thing the system actually saw, which a claim is allowed to point at.

what  : The `evidence` table. One row per change mask, detection set, index map, crop or statistic that a
        specialist produced and bound to ground.
where : Written by the evidence-generation node (S15), delivered with its layer in the `layer-ready` event so
        nothing renders unattributed, and referenced by `claims.evidence_ids`.
how   : **This table is the reason the product is trustworthy**, so its shape encodes the rules rather than
        relying on the services that write it.

        **`geometry` is nullable, and only for `statistic`.** Every other evidence kind is a place. A change
        mask with no geometry is a picture with nothing behind it, which is precisely the unauditable output
        the whole architecture exists to avoid - so a CHECK constraint requires geometry for the five spatial
        kinds and permits its absence only for a scalar.

        **`area_hectares` is measured, never estimated**, and it is measured through `AREA_MEASUREMENT_SQL`
        or a local equal-area projection (`constants/geo.py`). Stored rather than computed on read because it
        is quoted in reports, and a number in a report must not change because a library was upgraded.

        **`magnitude` drives extrusion** on the globe - how much changed, as a height. It is 0-1 and required;
        an unranked evidence set makes the operator scan instead of look.

        `confidence` is nullable and never zero by default, same rule as everywhere
        (`api-contract.md` §1 rule 2).

        `MULTIPOLYGON` here, unlike the single `POLYGON` of a scene footprint: a change mask over one area is
        genuinely several disjoint patches, and forcing them into one polygon would either merge unrelated
        regions or throw all but the largest away.
"""

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.evidence import EvidenceKind
from app.constants.geo import STORAGE_SRID
from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH, IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column, wire_enum


class Evidence(Base, TimestampMixin):
    """One georeferenced product of a specialist model, bound to the run that produced it."""

    __tablename__ = "evidence"

    id: Mapped[str] = identifier_column(IdentifierPrefix.EVIDENCE)

    run_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    kind: Mapped[EvidenceKind] = mapped_column(wire_enum(EvidenceKind), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)

    # The layer that draws this, and the features within it the spotlight raises. NULL for a `statistic`,
    # which has a value but nothing to draw.
    layer_id: Mapped[str | None] = mapped_column(String(IDENTIFIER_MAXIMUM_LENGTH), nullable=True)
    feature_ids: Mapped[list[str]] = mapped_column(nullable=False, default=list)

    # The outline of what was seen. Required for every spatial kind - see the CHECK below.
    geometry: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=STORAGE_SRID, spatial_index=True),
        nullable=True,
    )

    area_hectares: Mapped[float | None] = mapped_column(nullable=True)
    magnitude: Mapped[float] = mapped_column(nullable=False)
    confidence: Mapped[float | None] = mapped_column(nullable=True)

    # Which scenes this was derived from. A list because change evidence comes from a pair and cross-modal
    # evidence from two sensors, and losing that would break the "what was this computed from" question.
    source_scene_ids: Mapped[list[str]] = mapped_column(nullable=False, default=list)

    __table_args__ = (
        CheckConstraint(
            "kind = 'statistic' OR geometry IS NOT NULL",
            name="spatial_evidence_has_geometry",
        ),
        CheckConstraint("magnitude BETWEEN 0 AND 1", name="magnitude_is_a_fraction"),
        CheckConstraint(
            "confidence IS NULL OR confidence BETWEEN 0 AND 1",
            name="confidence_is_a_fraction_or_null",
        ),
        CheckConstraint(
            "area_hectares IS NULL OR area_hectares >= 0",
            name="area_is_not_negative",
        ),
        Index("ix_evidence_run_id", "run_id"),
    )
