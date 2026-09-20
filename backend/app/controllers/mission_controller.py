"""Controller for missions listing and retrieval.

Implements cursor pagination and mappings for Mission models.
"""

from datetime import UTC, datetime
from typing import Any

from geoalchemy2.functions import ST_Intersects
from geoalchemy2.shape import to_shape
from sqlalchemy import and_, func, or_, select

from app.constants.statuses import MissionStatus, RunStatus
from app.db.models.investigation import Investigation as DbInvestigation
from app.db.models.mission import Mission as DbMission
from app.db.models.project import Project
from app.db.models.run import Run as DbRun
from app.db.models.scene import Scene
from app.lib import database
from app.lib.exceptions import InvalidRequestError, ResourceNotFoundError
from app.lib.responses import CursorPage
from app.schemas.geo import GeoPoint
from app.schemas.missions import Mission, MissionCreateRequest
from shapely.geometry import Point, Polygon
from geoalchemy2.shape import from_shape

def _db_mission_to_wire(
    db_m: DbMission, scene_count: int = 0, confidence: float | None = None
) -> Mission:
    """Map DB Mission model to Mission schema with real scene count and confidence."""
    centroid_geom = to_shape(db_m.centroid)
    name_lower = db_m.name.lower()
    if "vegetation" in name_lower:
        analysis_kind = "vegetation-health"
    elif "urban" in name_lower:
        analysis_kind = "urban-growth"
    elif "flood" in name_lower or "water" in name_lower:
        analysis_kind = "flood-mapping"
    elif "cross" in name_lower:
        analysis_kind = "cross-modal"
    else:
        analysis_kind = "change-detection"

    status_str = db_m.status.value if hasattr(db_m.status, "value") else str(db_m.status)
    is_alert = status_str == "alert"

    return Mission(
        id=db_m.id,
        project_id=db_m.project_id or "prj_default",
        template_version_id=None,
        name=db_m.name,
        status=status_str,
        analysis_kind=analysis_kind,
        area_of_interest_name=db_m.name,
        centroid=GeoPoint(latitude=centroid_geom.y, longitude=centroid_geom.x),
        created_at=db_m.created_at,
        last_run_at=db_m.last_run_at,
        next_run_at=None,
        scene_count=scene_count,
        confidence=confidence,
        open_alert_count=1 if is_alert else 0,
        summary=f"Standing surface surveillance mission: {db_m.name}.",
        cadence="daily" if is_alert else "weekly",
        alert_rule=None,
    )


async def list_missions(
    cursor: str | None = None, limit: int = 20, project_id: str | None = None
) -> CursorPage[Mission]:
    """Retrieve cursor-paginated missions from database, optionally filtered by project."""
    try:
        async with database.get_session() as session:
            query = select(DbMission)
            if project_id:
                query = query.where(DbMission.project_id == project_id)
            query = query.order_by(DbMission.status_rank.asc(), DbMission.updated_at.desc(), DbMission.id.desc()).limit(limit + 1)
            if cursor:
                cursor_mission = await session.get(DbMission, cursor)
                if cursor_mission is not None:
                    query = query.where(
                        or_(
                            DbMission.status_rank > cursor_mission.status_rank,
                            and_(
                                DbMission.status_rank == cursor_mission.status_rank,
                                DbMission.updated_at < cursor_mission.updated_at,
                            ),
                            and_(
                                DbMission.status_rank == cursor_mission.status_rank,
                                DbMission.updated_at == cursor_mission.updated_at,
                                DbMission.id < cursor_mission.id,
                            ),
                        )
                    )
            result = await session.execute(query)
            rows = list(result.scalars().all())

            next_cursor = None
            if len(rows) > limit:
                next_cursor = rows[limit - 1].id
                rows = rows[:limit]

            items: list[Mission] = []
            for r in rows:
                scene_cnt_stmt = select(func.count(Scene.id)).where(
                    ST_Intersects(Scene.footprint, r.area_of_interest)
                )
                cnt_res = await session.execute(scene_cnt_stmt)
                scene_count = cnt_res.scalar() or 0

                conf: float | None = None
                if r.investigation_id:
                    conf_stmt = select(func.avg(DbRun.confidence)).where(
                        DbRun.investigation_id == r.investigation_id,
                        DbRun.status == RunStatus.COMPLETE,
                        DbRun.confidence.is_not(None),
                    )
                    conf_res = await session.execute(conf_stmt)
                    conf_val = conf_res.scalar()
                    if conf_val is not None:
                        conf = round(float(conf_val), 2)

                items.append(_db_mission_to_wire(r, scene_count=scene_count, confidence=conf))

            return CursorPage(items=items, next_cursor=next_cursor, total_count=len(items))
    except Exception:
        return CursorPage(items=[], next_cursor=None, total_count=0)


async def get_mission_by_id(mission_id: str) -> Mission:
    """Retrieve a single mission by ID from database."""
    async with database.get_session() as session:
        query = select(DbMission).where(DbMission.id == mission_id)
        result = await session.execute(query)
        db_m = result.scalar_one_or_none()
        if db_m is not None:
            scene_cnt_stmt = select(func.count(Scene.id)).where(
                ST_Intersects(Scene.footprint, db_m.area_of_interest)
            )
            cnt_res = await session.execute(scene_cnt_stmt)
            scene_count = cnt_res.scalar() or 0

            conf: float | None = None
            if db_m.investigation_id:
                conf_stmt = select(func.avg(DbRun.confidence)).where(
                    DbRun.investigation_id == db_m.investigation_id,
                    DbRun.status == RunStatus.COMPLETE,
                    DbRun.confidence.is_not(None),
                )
                conf_res = await session.execute(conf_stmt)
                conf_val = conf_res.scalar()
                if conf_val is not None:
                    conf = round(float(conf_val), 2)

            return _db_mission_to_wire(db_m, scene_count=scene_count, confidence=conf)

    raise ResourceNotFoundError(f"Mission '{mission_id}' does not exist.", details={"missionId": mission_id})

async def create_mission(request: MissionCreateRequest) -> Mission:
    """Create a new mission, either standalone or promoted from an investigation."""
    async with database.get_session() as session:
        poly = None
        centroid_geom = None
        proj_id = request.project_id

        if request.investigation_id:
            inv_stmt = select(DbInvestigation).where(DbInvestigation.id == request.investigation_id)
            inv_res = await session.execute(inv_stmt)
            db_inv = inv_res.scalar_one_or_none()
            if db_inv is None:
                raise ResourceNotFoundError(
                    f"Source investigation '{request.investigation_id}' does not exist.",
                    details={"investigationId": request.investigation_id},
                )
            poly = db_inv.area_of_interest
            centroid_geom = db_inv.centroid
            if not proj_id:
                proj_id = db_inv.project_id

        if poly is None:
            if request.centroid is None:
                raise InvalidRequestError("Either investigation_id or centroid must be provided to create a mission.")
            pt = Point(request.centroid.longitude, request.centroid.latitude)
            delta = 0.1
            minx, miny, maxx, maxy = pt.x - delta, pt.y - delta, pt.x + delta, pt.y + delta
            poly = from_shape(Polygon([(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy), (minx, miny)]), srid=4326)
            centroid_geom = from_shape(pt, srid=4326)

        final_proj_id = proj_id or "prj_default"

        # Ensure project exists
        proj = await session.get(Project, final_proj_id)
        if proj is None:
            session.add(
                Project(
                    id=final_proj_id,
                    name="Default Project" if final_proj_id == "prj_default" else f"Project {final_proj_id}",
                    description="Auto-initialized project workspace",
                    last_activity_at=datetime.now(UTC),
                )
            )
        else:
            proj.last_activity_at = datetime.now(UTC)

        db_m = DbMission(
            name=request.name,
            status=MissionStatus.ACTIVE,
            centroid=centroid_geom,
            area_of_interest=poly,
            project_id=final_proj_id,
            investigation_id=request.investigation_id,
        )
        session.add(db_m)
        await session.commit()
        await session.refresh(db_m)

        return _db_mission_to_wire(db_m, scene_count=0, confidence=None)

