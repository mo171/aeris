from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, JSON, text, Index
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB

from app.db.identifiers import IDENTIFIER_MAXIMUM_LENGTH
from app.db.models.base import Base, TimestampMixin, identifier_column


class InvestigationHistory(Base):
    __tablename__ = "investigation_history"

    id: Mapped[str] = identifier_column("his_")
    investigation_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    at: Mapped[datetime] = mapped_column(nullable=False)
    actor: Mapped[str] = mapped_column(String(256), nullable=False)
    command_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str] = mapped_column(String(2048), nullable=False)

    __table_args__ = (
        Index("ix_investigation_history_investigation_id_at", "investigation_id", text("at ASC")),
    )

    def to_wire(self) -> dict[str, Any]:
        dt = self.at or datetime.now()
        iso = dt.isoformat()
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        elif not iso.endswith("Z"):
            iso += "Z"
        return {
            "id": self.id,
            "investigationId": self.investigation_id,
            "at": iso,
            "actor": self.actor,
            "commandId": self.command_id,
            "params": self.params,
            "summary": self.summary,
        }


class InvestigationVersion(Base, TimestampMixin):
    __tablename__ = "investigation_versions"

    id: Mapped[str] = identifier_column("ver_")
    investigation_id: Mapped[str] = mapped_column(
        String(IDENTIFIER_MAXIMUM_LENGTH),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    state: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    
    __table_args__ = (
        Index("ix_investigation_versions_investigation_id_created_at", "investigation_id", text("created_at DESC")),
    )

    def to_wire(self) -> dict[str, Any]:
        state_dict = self.state or {}
        snapshot = state_dict.get("snapshot", state_dict)
        dt = self.created_at or datetime.now()
        iso = dt.isoformat()
        if iso.endswith("+00:00"):
            iso = iso[:-6] + "Z"
        elif not iso.endswith("Z"):
            iso += "Z"
        return {
            "id": self.id,
            "label": self.name or "Version Snapshot",
            "createdAt": iso,
            "actor": state_dict.get("actor", "operator"),
            "parentVersionId": state_dict.get("parentVersionId"),
            "snapshot": snapshot,
        }

