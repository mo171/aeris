"""Route declarations for operator authentication and session management.

what  : Declares HTTP endpoints for fetching current user profile and active session.
where : Mounted under /api/v1/auth in app/main.py.
how   : Thin route layer: pure URL mapping delegating to auth_controller.
"""

from fastapi import APIRouter, status

from app.controllers import auth_controller
from app.schemas.auth import UserProfile, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/me",
    response_model=UserProfile,
    status_code=status.HTTP_200_OK,
    summary="Get current operator profile",
)
async def get_me() -> UserProfile:
    """Retrieve the profile of the authenticated operator."""
    return await auth_controller.get_current_user_profile()


@router.get(
    "/session",
    response_model=UserSession,
    status_code=status.HTTP_200_OK,
    summary="Get current operator session",
)
async def get_session() -> UserSession:
    """Retrieve active operator session information."""
    return await auth_controller.get_current_session()
