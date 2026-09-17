"""Catalogue routes declaration.

Adheres to bcontext/folder-archtecture.md:
- Pure route declarations. No database queries, no models.
"""

from fastapi import APIRouter

from app.controllers import catalogue_controller
from app.schemas.catalogue import CatalogueSearchResponse, TemporalQueryRequest

router = APIRouter(prefix="/catalogue", tags=["catalogue"])


@router.post("/search", response_model=CatalogueSearchResponse)
async def search_catalogue(query: TemporalQueryRequest) -> CatalogueSearchResponse:
    """Search catalogue acquisitions for a given spatial area and temporal window."""
    return await catalogue_controller.search_catalogue(query)
