from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.constants.geo import POINT_GEOMETRY, POLYGON_GEOMETRY, STORAGE_SRID
from app.db.identifiers import IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = identifier_column(IdentifierPrefix.PROJECT)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    area_of_interest_name: Mapped[str] = mapped_column(String(256), nullable=False, server_default="")
    area_of_interest: Mapped[str | None] = mapped_column(
        Geometry(geometry_type=POLYGON_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=True,
    )
    centroid: Mapped[str | None] = mapped_column(
        Geometry(geometry_type=POINT_GEOMETRY, srid=STORAGE_SRID, spatial_index=True),
        nullable=True,
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(nullable=True)
