"""Controller for operator authentication and session management.

what  : Loads the hardcoded default user from backend/data/default_user.json and serves session info.
where : Called by app/routes/auth.py and used as dependency injection across API controllers.
how   : As specified in Phase 2.8, operates with zero external auth overhead; loads from JSON and caches in memory.
"""

from datetime import UTC, datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any

from app.schemas.auth import UserProfile, UserSession

logger = logging.getLogger(__name__)

_DEFAULT_USER_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "default_user.json"

_CACHED_USER: UserProfile | None = None


def get_default_user() -> UserProfile:
    """Load and return the hardcoded default operator profile."""
    global _CACHED_USER
    if _CACHED_USER is not None:
        return _CACHED_USER

    if _DEFAULT_USER_FILE.exists():
        try:
            data = json.loads(_DEFAULT_USER_FILE.read_text(encoding="utf-8"))
            _CACHED_USER = UserProfile.model_validate(data)
            return _CACHED_USER
        except Exception as error:
            logger.warning("Failed to parse %s (%s); using fallback user", _DEFAULT_USER_FILE, error)

    # Safe deterministic fallback if file is unreadable
    _CACHED_USER = UserProfile(
        id="usr_01aeris_operator_default",
        username="operator",
        email="operator@aeris.internal",
        name="AERIS Lead Analyst",
        role="lead_analyst",
        organization="National Remote Sensing Agency",
        permissions=[
            "investigations:create",
            "investigations:read",
            "investigations:write",
            "runs:execute",
            "reports:generate",
            "admin",
        ],
        avatar_url="/avatars/lead-analyst.png",
        created_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
    )
    return _CACHED_USER


async def get_current_user_profile() -> UserProfile:
    """Async coordinator returning current authenticated operator."""
    return get_default_user()


async def get_current_session() -> UserSession:
    """Async coordinator returning active operator session descriptor."""
    user = get_default_user()
    return UserSession(
        user=user,
        session_id="ses_01aeris_default_session",
        is_authenticated=True,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
