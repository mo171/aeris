"""Declaration of figure artifact routes.

Follows bcontext/folder-archtecture.md:
Declaration only. No business logic, no database queries, no model definitions.
All requests are routed directly to controllers/figures_controller.py.
"""

from fastapi import APIRouter, Response

from app.controllers import figures_controller

router = APIRouter(prefix="/figures", tags=["figures"])


@router.get("/{figure_id}")
async def get_figure_image(figure_id: str) -> Response:
    """Retrieve raw image bytes for a figure artifact from object storage."""
    return await figures_controller.get_figure_image_response(figure_id)
