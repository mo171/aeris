from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.identifiers import IdentifierPrefix
from app.db.models.base import Base, TimestampMixin, identifier_column


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = identifier_column(IdentifierPrefix.PROJECT)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
