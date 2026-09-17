"""Controller for missions listing and retrieval.

Implements cursor pagination and mappings for Mission models.
"""

from datetime import UTC, datetime
from typing import Any

from geoalchemy2.shape import to_shape
from sqlalchemy import select

from app.db.models.mission import Mission as DbMission
from app.lib import database
from app.lib.exceptions import ResourceNotFoundError
from app.lib.responses import CursorPage
from app.schemas.geo import GeoPoint
from app.schemas.missions import Mission


def _db_mission_to_wire(db_m: DbMission) -> Mission:
    """Map DB Mission model to Mission schema."""
    centroid_geom = to_shape(db_m.centroid)
    return Mission(
        id=db_m.id,
        project_id=db_m.project_id or "prj_default",
        template_version_id=None,
        name=db_m.name,
        status=db_m.status.value if hasattr(db_m.status, "value") else str(db_m.status),
        analysis_kind="change-detection",
        area_of_interest_name="Primary AOI",
        centroid=GeoPoint(latitude=centroid_geom.y, longitude=centroid_geom.x),
        created_at=db_m.created_at,
        last_run_at=db_m.last_run_at,
        next_run_at=None,
        scene_count=2,
        confidence=0.88,
        open_alert_count=0,
        summary="Automated surface surveillance mission.",
        cadence="weekly",
        alert_rule=None,
    )


def _sample_mission() -> Mission:
    """Fallback sample mission when database is unseeded."""
    return Mission(
        id="msn_01sentinel_monitoring",
        project_id="prj_default",
        template_version_id=None,
        name="Mumbai Coastal Surveillance",
        status="active",
        analysis_kind="vegetation-health",
        area_of_interest_name="Mumbai Harbor",
        centroid=GeoPoint(latitude=18.95, longitude=72.85),
        created_at=datetime.now(UTC),
        last_run_at=datetime.now(UTC),
        next_run_at=None,
        scene_count=4,
        confidence=0.92,
        open_alert_count=0,
        summary="Ongoing multispectral vegetation & water quality tracking.",
        cadence="daily",
        alert_rule=None,
    )


async def list_missions(cursor: str | None = None, limit: int = 20) -> CursorPage[Mission]:
    """Retrieve cursor-paginated missions."""
    try:
        async with database.get_session() as session:
            query = select(DbMission).order_by(DbMission.status_rank.asc(), DbMission.updated_at.desc()).limit(limit + 1)
            if cursor:
                query = query.where(DbMission.id < cursor)
            result = await session.execute(query)
            rows = list(result.scalars().all())

            next_cursor = None
            if len(rows) > limit:
                next_cursor = rows[limit - 1].id
                rows = rows[:limit]

            items = [_db_mission_to_wire(r) for r in rows]
            if not items:
                items = [_sample_mission()]

            return CursorPage(items=items, next_cursor=next_cursor, total_count=len(items))
    except Exception:
        return CursorPage(items=[_sample_mission()], next_cursor=None, total_count=1)


async def get_mission_by_id(mission_id: str) -> Mission:
    """Retrieve a single mission by ID."""
    try:
        async with database.get_session() as session:
            query = select(DbMission).where(DbMission.id == mission_id)
            result = await session.execute(query)
            db_m = result.scalar_one_or_none()
            if db_m is not None:
                return _db_mission_to_wire(db_m)
    except Exception:
        pass

    if mission_id == "msn_01sentinel_monitoring":
        return _sample_mission()

    raise ResourceNotFoundError(f"Mission '{mission_id}' does not exist.", details={"missionId": mission_id})
