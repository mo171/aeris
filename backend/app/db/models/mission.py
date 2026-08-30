"""A saved, re-runnable investigation over an area the operator wants to keep watching.

what  : The `missions` table. What an investigation is promoted into by `POST /missions`, and what the globe
        draws markers for.
where : Read by `GET /missions` (cursor-paginated, **ordered server-side**) and by `GET /globe/markers`.
        Mirrors the frontend's mission schema.
how   : **Ordering is the backend's job.** The frontend's note is explicit that it deliberately does not
        re-sort: alerts first, then recency. `status_rank` exists so that ordering is an index scan rather
        than a `CASE` expression evaluated over every row, and so that the priority of a status is written in
        one place instead of in every query that needs it.

        `last_run_at` is nullable: a mission saved a minute ago has never run. The frontend shows "not yet
        run", which is different from a run that happened and produced nothing.

        `investigation_id` records what this was promoted from and is `SET NULL` on delete rather than
        cascading. Deleting the original investigation should not delete the standing mission that outlived
        it; the mission keeps its own area and its own history.
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.geo import POINT_GEOMETRY, POLYGON_GEOMETRY, STORAGE_SRID
from app.constants.statuses import MissionStatus
from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH, IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column, wire_enum

# Lower sorts first. Written here rather than in a query so that "alerts come first" is one fact in one
# place; a second query that ordered differently would make the globe and the list disagree about urgency.
MISSION_STATUS_RANK: dict[MissionStatus, int] = {
    MissionStatus.ALERT: 0,
    MissionStatus.MONITORING: 1,
    MissionStatus.ACTIVE: 2,
    MissionStatus.ARCHIVED: 3,
}


class Mission(Base, TimestampMixin):
    """A standing investigation over one area."""

    __tablename__ = "missions"

    id: Mapped[str] = identifier_column(IdentifierPrefix.MISSION)

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    status: Mapped[MissionStatus] = mapped_column(
        wire_enum(MissionStatus),
        nullable=False,
        default=MissionStatus.ACTIVE,
    )

    # Denormalised from `status` through `MISSION_STATUS_RANK`, maintained by the mission service on every
    # status write. Denormalisation is justified here by the ordering being on the hot path of both the list
    # and the globe, and by the rank being derived from a value in the same row.
    status_rank: Mapped[int] = mapped_column(nullable=False, default=MISSION_STATUS_RANK[MissionStatus.ACTIVE])

    area_of_interest: Mapped[str] = mapped_column(
        Geometry(geometry_type=POLYGON_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=False,
    )
    centroid: Mapped[str] = mapped_column(
        Geometry(geometry_type=POINT_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=False,
    )

    # NULL until the mission runs for the first time.
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)

    investigation_id: Mapped[str | None] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("investigations.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        # Exactly the order `GET /missions` returns, so the list is an index scan.
        Index("ix_missions_status_rank_updated_at", "status_rank", text("updated_at DESC")),
    )
