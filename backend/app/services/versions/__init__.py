"""Investigation workspace versioning and snapshot management.

what  : Save, list, get, diff, and restore investigation versions.
where : Called by API routes and background execution services.
how   : Uses SQLAlchemy InvestigationVersion and InvestigationHistory models with JSONB snapshot persistence.
"""

from app.services.versions.manager import (
    compare_version_snapshots,
    get_version,
    list_versions,
    restore_version,
    save_version,
)

__all__ = [
    "compare_version_snapshots",
    "get_version",
    "list_versions",
    "restore_version",
    "save_version",
]
