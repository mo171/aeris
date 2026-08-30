"""One operator's question about one area, and the scenes bound to the slots that answer it.

what  : The `investigations` table and the `investigation_scenes` link table that carries scene *roles*.
where : Created by `POST /investigations`, read by the workspace, and the parent of every run. Mirrors the
        frontend's `investigationSchema` and `investigationSceneSlotSchema`.
how   : **The role lives on the link, never on the scene** (`constants/scenes.py`). The same Sentinel-2
        acquisition is `t0` in one investigation and `t1` in another; putting `role` on `scenes` would make
        the second investigation overwrite the first one's meaning.

        **One scene per role per investigation, except `aux`.** A unique index enforces it for the three
        singular roles. Two scenes claiming to be `t1` is not a data-entry mistake to tolerate: the
        comparator binds a role to a raster, so an ambiguous `t1` renders a different picture depending on
        row order.

        `trace_id` is the provenance identity the frontend calls "small, permanent, and the most credible
        element on the page". It is unique, it is never regenerated, and it is what a printed report is
        looked up by.

        `camera_bookmark` is JSONB rather than five columns. It is written and read as one opaque blob by
        the viewer, nothing queries inside it, and the frontend's `cameraBookmarkSchema` owns its shape.
"""

from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.geo import POINT_GEOMETRY, POLYGON_GEOMETRY, STORAGE_SRID
from app.constants.investigations import WorkspaceMode
from app.constants.scenes import SceneRole
from app.constants.statuses import InvestigationStatus
from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH, IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column, wire_enum


class Investigation(Base, TimestampMixin):
    """An area, a question, and the scenes chosen to answer it. Outlives the runs inside it."""

    __tablename__ = "investigations"

    id: Mapped[str] = identifier_column(IdentifierPrefix.INVESTIGATION)

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # The human name of the place - "Vellore District, Tamil Nadu". Resolved at creation from the scene
    # footprints, because `POST /investigations` must return it fast enough that the camera is already
    # flying (`api-contract.md` §1 rule 6).
    area_of_interest_name: Mapped[str] = mapped_column(String(256), nullable=False)

    area_of_interest: Mapped[str] = mapped_column(
        Geometry(geometry_type=POLYGON_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=False,
    )
    centroid: Mapped[str] = mapped_column(
        Geometry(geometry_type=POINT_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=False,
    )

    status: Mapped[InvestigationStatus] = mapped_column(
        wire_enum(InvestigationStatus),
        nullable=False,
        default=InvestigationStatus.DRAFT,
    )
    mode: Mapped[WorkspaceMode] = mapped_column(
        wire_enum(WorkspaceMode),
        nullable=False,
        default=WorkspaceMode.TEMPORAL,
    )

    # The question that started this, carried down from Mission Command. Nullable because an investigation
    # can be opened from the catalogue with no question yet.
    seed_query: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # `use_alter` breaks a genuine cycle: an investigation names the mission it belongs to, and a mission
    # names the investigation it was promoted from. Both references are real and neither is redundant, so one
    # of the two constraints is added after both tables exist rather than during their creation.
    mission_id: Mapped[str | None] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("missions.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )

    # Provenance identity. Unique, permanent, quoted in reports.
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # The saved camera position, or NULL. Written only on an explicit save, never on camera movement.
    camera_bookmark: Mapped[dict[str, Any] | None] = mapped_column(nullable=True)

    __table_args__ = (
        # The index list is ordered by recency for the workspace's "recent investigations".
        Index("ix_investigations_updated_at", text("updated_at DESC")),
        Index("ix_investigations_status", "status"),
    )


class InvestigationScene(Base):
    """The binding of one scene to one slot in one investigation.

    No `TimestampMixin`: a slot binding is replaced rather than edited, and `POST /investigations/{id}/scenes`
    returns the whole updated investigation precisely so that no client has to reason about when a binding
    last changed.
    """

    __tablename__ = "investigation_scenes"

    investigation_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    scene_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        # RESTRICT, not CASCADE: deleting a scene that an investigation is built on would silently change
        # what that investigation's completed runs were computed from, which breaks provenance.
        ForeignKey("scenes.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[SceneRole] = mapped_column(wire_enum(SceneRole), primary_key=True)

    __table_args__ = (
        # `t0`, `t1` and `sar` are singular slots; `aux` is excluded, since an investigation may carry
        # several reference scenes. A *partial* unique index is what expresses "unique except for one value"
        # in the schema rather than in application code that a second call site can bypass.
        Index(
            "uq_investigation_scenes_singular_role",
            "investigation_id",
            "role",
            unique=True,
            postgresql_where=text("role <> 'aux'"),
        ),
        Index("ix_investigation_scenes_scene_id", "scene_id"),
    )
