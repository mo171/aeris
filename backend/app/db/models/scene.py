"""One satellite acquisition as the catalogue knows it: where it is, what sensor made it, and whether it is usable.

what  : The `scenes` table. Metadata extracted at ingest (S1-S6), the geometry the catalogue searches on, and
        the object keys for the raw file and its COG.
where : Written by ingestion, read by catalogue search, by the globe marker feed, and by every pipeline stage
        that must know whether it is looking at reflectance or backscatter. Mirrors the frontend's
        `imagerySceneSchema`.
how   : **`cloud_cover_percentage` is nullable and must stay `NULL` for SAR** - `api-contract.md` §1 rule 3.
        Zero would assert a cloud-free radar scene, which is a claim about the weather rather than a
        statement that the question does not apply. Enforced by a CHECK constraint rather than by convention,
        because "the ingest service remembers" is not a guarantee and this value reaches an operator.

        **`processing_state` gates analysis.** Only `ready` means the raster passed the S6 quality checks;
        `architecture-context.md` §8 forbids a model reading anything else, and a partially-ingested scene
        that looks analysable is how a confidently wrong answer starts.

        Footprint and centroid are both stored although the centroid is derivable. The globe marker feed
        returns the whole collection unpaginated and wants a point per scene without a per-row `ST_Centroid`;
        the footprint is what search intersects against. Both carry a spatial index.
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.geo import POINT_GEOMETRY, POLYGON_GEOMETRY, STORAGE_SRID
from app.constants.scenes import SceneModality, TemporalRole
from app.constants.statuses import SceneProcessingState
from app.db.identifiers import IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column, wire_enum


class Scene(Base, TimestampMixin):
    """A single acquisition. Immutable once `processing_state` reaches `ready`."""

    __tablename__ = "scenes"

    id: Mapped[str] = identifier_column(IdentifierPrefix.SCENE)

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    # When the satellite took it, not when we received it. The temporal comparator scrubs on this axis, so
    # it is indexed and it is timezone-aware (see base.py).
    captured_at: Mapped[datetime] = mapped_column(nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(nullable=False)

    modality: Mapped[SceneModality] = mapped_column(wire_enum(SceneModality), nullable=False)
    sensor_platform: Mapped[str] = mapped_column(String(128), nullable=False)
    band_count: Mapped[int] = mapped_column(nullable=False)
    ground_sample_distance_meters: Mapped[float] = mapped_column(nullable=False)

    # NULL for SAR. See the module docstring and the CHECK constraint below.
    cloud_cover_percentage: Mapped[float | None] = mapped_column(nullable=True)

    # The source raster's own CRS, kept as declared - e.g. `EPSG:32643`. Not the storage CRS of the geometry
    # columns, which is always 4326; this records what the pixels are in, and preprocessing needs it.
    coordinate_reference_system: Mapped[str] = mapped_column(String(64), nullable=False)

    footprint: Mapped[str] = mapped_column(
        Geometry(geometry_type=POLYGON_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=False,
    )
    centroid: Mapped[str] = mapped_column(
        Geometry(geometry_type=POINT_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=False,
    )

    # BIGINT, not INTEGER: a multi-band scene passes INTEGER's 2.147 GB ceiling, and the overflow would
    # fail ingest on precisely the large acquisitions this system exists to handle.
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processing_state: Mapped[SceneProcessingState] = mapped_column(
        wire_enum(SceneProcessingState),
        nullable=False,
        default=SceneProcessingState.QUEUED,
    )
    temporal_role: Mapped[TemporalRole] = mapped_column(
        wire_enum(TemporalRole),
        nullable=False,
        default=TemporalRole.SINGLE,
    )

    thumbnail_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Object storage keys, filled in by ingest. Both nullable because a scene row exists from the moment an
    # upload is ticketed, before any bytes have arrived (`POST /imagery/upload-ticket`), and the COG only
    # exists after S1-S6 succeed. A scene with `processing_state = ready` and a NULL `cog_object_key` is a
    # contradiction, which is what the second CHECK below says.
    raw_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cog_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(modality = 'sar' AND cloud_cover_percentage IS NULL)"
            " OR (modality <> 'sar' AND (cloud_cover_percentage IS NULL"
            " OR cloud_cover_percentage BETWEEN 0 AND 100))",
            name="sar_has_no_cloud_cover",
        ),
        CheckConstraint(
            "processing_state <> 'ready' OR cog_object_key IS NOT NULL",
            name="ready_scene_has_a_cog",
        ),
        CheckConstraint(
            "ground_sample_distance_meters > 0",
            name="ground_sample_distance_is_positive",
        ),
        CheckConstraint("band_count > 0", name="band_count_is_positive"),
        # The catalogue's ordinary query is "acquisitions over this area, in this window, of these
        # modalities". The window is the selective half, so time leads; the spatial predicate is served by
        # the GiST index on `footprint` that `spatial_index=True` creates.
        Index("ix_scenes_captured_at_modality", "captured_at", "modality"),
        Index("ix_scenes_processing_state", "processing_state"),
    )
