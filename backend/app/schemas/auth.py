"""Wire models for operator authentication, user profile, and active session.

what  : Defines the wire shape of user identities, permissions, and active session descriptors.
where : Used by `app/controllers/auth_controller.py` and `app/routes/auth.py`.
how   : Inherits from CamelCaseModel so Python snake_case serialises directly to camelCase on the wire.
"""

from datetime import datetime
from pydantic import Field

from app.lib.responses import CamelCaseModel


class UserProfile(CamelCaseModel):
    """The authenticated operator profile."""

    id: str = Field(min_length=1, description="Unique operator identifier")
    username: str = Field(min_length=1, description="Handle or username")
    email: str = Field(min_length=1, description="Primary contact email")
    name: str = Field(min_length=1, description="Display name of the analyst")
    role: str = Field(min_length=1, description="Operator role classification")
    organization: str = Field(min_length=1, description="Affiliated agency or organisation")
    permissions: list[str] = Field(default_factory=list, description="Granted operational scopes")
    avatar_url: str | None = Field(default=None, description="Path or URL to avatar graphic")
    created_at: str | datetime = Field(description="Account creation timestamp")


class UserSession(CamelCaseModel):
    """Active operator session metadata."""

    user: UserProfile
    session_id: str = Field(min_length=1, description="Unique session token or descriptor")
    is_authenticated: bool = Field(default=True, description="Whether the session is active and valid")
    expires_at: datetime | None = Field(default=None, description="Optional session expiration time")
