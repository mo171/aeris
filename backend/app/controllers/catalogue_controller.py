"""Controller for temporal catalogue search.

Searches available acquisitions matching area of interest, date window, and cloud constraints.
Returns CatalogueSearchResponse adhering to features/investigation/schemas/catalogue.schema.ts.
"""

from datetime import UTC, datetime
from typing import Any

from geoalchemy2.functions import ST_Intersects
from geoalchemy2.shape import from_shape
from shapely.geometry import box
from sqlalchemy import or_, select

from app.constants.geo import STORAGE_SRID
from app.constants.scenes import SceneModality
from app.constants.statuses import SceneProcessingState
from app.db.models.scene import Scene as DbScene
from app.lib import database
from app.schemas.catalogue import (
    Acquisition,
    AcquisitionTiles,
    CatalogueSearchResponse,
    CoverageGap,
    PairRecommendation,
    TemporalQueryRequest,
)


def _recommend_pair(acquisitions: list[Acquisition]) -> PairRecommendation | None:
    """Recommend an optimal before/after or cross-modal pair from matching acquisitions."""
    if len(acquisitions) < 2:
        return None

    # Check for multimodal pair (one optical and one SAR)
    optical_acqs = [a for a in acquisitions if a.modality == SceneModality.OPTICAL]
    sar_acqs = [a for a in acquisitions if a.modality == SceneModality.SAR]

    if optical_acqs and sar_acqs:
        best_opt = optical_acqs[0]
        best_sar = sar_acqs[0]
        min_diff = abs((best_opt.captured_at - best_sar.captured_at).total_seconds())
        for opt in optical_acqs:
            for sar in sar_acqs:
                diff = abs((opt.captured_at - sar.captured_at).total_seconds())
                if diff < min_diff:
                    min_diff = diff
                    best_opt = opt
                    best_sar = sar
        sep_days = round(min_diff / 86400)
        t0, t1 = (best_opt, best_sar) if best_opt.captured_at <= best_sar.captured_at else (best_sar, best_opt)
        return PairRecommendation(
            t0_scene_id=t0.scene_id,
            t1_scene_id=t1.scene_id,
            separation_days=sep_days,
            reason=f"Coincident optical ({best_opt.sensor_platform}) and SAR ({best_sar.sensor_platform}) acquisitions ({sep_days} days apart) for late fusion.",
        )

    # Otherwise sort chronologically for temporal change detection
    sorted_acqs = sorted(acquisitions, key=lambda a: a.captured_at)
    t0 = sorted_acqs[0]
    t1 = sorted_acqs[-1]
    sep_days = max(1, (t1.captured_at - t0.captured_at).days)
    return PairRecommendation(
        t0_scene_id=t0.scene_id,
        t1_scene_id=t1.scene_id,
        separation_days=sep_days,
        reason=f"Temporal baseline ({t0.sensor_platform} on {t0.captured_at.strftime('%Y-%m-%d')}) and comparison ({t1.sensor_platform} on {t1.captured_at.strftime('%Y-%m-%d')}) with {sep_days} days separation.",
    )


def _compute_coverage_gaps(
    request: TemporalQueryRequest, acquisitions: list[Acquisition]
) -> list[CoverageGap]:
    """Calculate stretches of the requested search window with no satellite passes."""
    gaps: list[CoverageGap] = []
    gap_threshold_days = 14

    if not acquisitions:
        window_days = max(1, (request.to - request.from_).days)
        gaps.append(
            CoverageGap(
                from_=request.from_,
                to=request.to,
                days=window_days,
                reason="No satellite passes catalogued within this area and temporal window.",
            )
        )
        return gaps

    sorted_acqs = sorted(acquisitions, key=lambda a: a.captured_at)

    # Gap before first acquisition
    first_gap = (sorted_acqs[0].captured_at - request.from_).days
    if first_gap >= gap_threshold_days:
        gaps.append(
            CoverageGap(
                from_=request.from_,
                to=sorted_acqs[0].captured_at,
                days=first_gap,
                reason="No catalogued acquisitions between search start and first recorded pass.",
            )
        )

    # Gaps between consecutive acquisitions
    for i in range(len(sorted_acqs) - 1):
        delta_days = (sorted_acqs[i + 1].captured_at - sorted_acqs[i].captured_at).days
        if delta_days >= gap_threshold_days:
            gaps.append(
                CoverageGap(
                    from_=sorted_acqs[i].captured_at,
                    to=sorted_acqs[i + 1].captured_at,
                    days=delta_days,
                    reason=f"Orbital revisit gap of {delta_days} days between passes.",
                )
            )

    # Gap after last acquisition
    last_gap = (request.to - sorted_acqs[-1].captured_at).days
    if last_gap >= gap_threshold_days:
        gaps.append(
            CoverageGap(
                from_=sorted_acqs[-1].captured_at,
                to=request.to,
                days=last_gap,
                reason="No catalogued acquisitions between latest pass and search window end.",
            )
        )

    return gaps


async def search_catalogue(request: TemporalQueryRequest) -> CatalogueSearchResponse:
    """Execute temporal archive query over the specified window and AOI."""
    aoi = request.area_of_interest
    aoi_box = box(aoi.west, aoi.south, aoi.east, aoi.north)
    aoi_geom = from_shape(aoi_box, srid=STORAGE_SRID)

    acquisitions: list[Acquisition] = []

    try:
        async with database.get_session() as session:
            stmt = select(DbScene).where(
                DbScene.footprint.is_not(None),
                ST_Intersects(DbScene.footprint, aoi_geom),
                DbScene.captured_at >= request.from_,
                DbScene.captured_at <= request.to,
                DbScene.processing_state == SceneProcessingState.READY,
            )

            if request.modalities:
                stmt = stmt.where(DbScene.modality.in_(request.modalities))

            if request.maximum_cloud_percentage is not None:
                stmt = stmt.where(
                    or_(
                        DbScene.cloud_cover_percentage.is_(None),
                        DbScene.cloud_cover_percentage <= request.maximum_cloud_percentage,
                    )
                )

            stmt = stmt.order_by(DbScene.captured_at.asc())
            result = await session.execute(stmt)
            scenes = list(result.scalars().all())

            for scene in scenes:
                acq_id = f"acq_{scene.id.replace('scn_', '')}"
                acquisitions.append(
                    Acquisition(
                        id=acq_id,
                        scene_id=scene.id,
                        captured_at=scene.captured_at,
                        modality=scene.modality,
                        sensor_platform=scene.sensor_platform,
                        ground_sample_distance_meters=scene.ground_sample_distance_meters,
                        cloud_cover_percentage=scene.cloud_cover_percentage,
                        quicklook_url=scene.thumbnail_url or f"/api/v1/tiles/{scene.id}/preview",
                        tiles=AcquisitionTiles(
                            url_template=f"/api/v1/tiles/{scene.id}/{{z}}/{{x}}/{{y}}.png",
                            attribution=f"Copernicus {scene.sensor_platform}",
                            minimum_zoom=8,
                            maximum_zoom=14,
                        ),
                        is_available=True,
                    )
                )
    except Exception:
        acquisitions = []

    coverage_gaps = _compute_coverage_gaps(request, acquisitions)
    recommended_pair = _recommend_pair(acquisitions)

    advisory: str | None = None
    if not acquisitions:
        advisory = "No acquisitions match the spatial, temporal, and cloud constraints."
    elif all(a.modality == SceneModality.SAR for a in acquisitions):
        advisory = "Only SAR acquisitions found; optical spectral indices (NDVI/EVI) unavailable."

    return CatalogueSearchResponse(
        query=request,
        acquisitions=acquisitions,
        coverage_gaps=coverage_gaps,
        recommended_pair=recommended_pair,
        advisory=advisory,
    )
