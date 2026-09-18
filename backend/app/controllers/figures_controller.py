"""Controller for figures: metadata listing and immutable artifact streaming.

Coordinates artifact retrieval through figures_service and sets appropriate CORS and Cache-Control headers.
"""

import logging

from fastapi import Response

from app.schemas.events.figure import FigureReadyEvent
from app.services.investigations import figures_service

logger = logging.getLogger(__name__)


async def list_investigation_figures(investigation_id: str) -> list[FigureReadyEvent]:
    """Retrieve figure metadata for an investigation."""
    return await figures_service.list_investigation_figures(investigation_id)


async def get_figure_image_response(figure_id: str) -> Response:
    """Retrieve raw figure bytes from storage and build HTTP response with CORS and immutable cache headers."""
    image_bytes, media_type = await figures_service.get_figure_bytes(figure_id)

    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }
    return Response(content=image_bytes, media_type=media_type, headers=headers)
