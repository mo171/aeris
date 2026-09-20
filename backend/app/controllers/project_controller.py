"""Controller for projects listing and retrieval.

Implements cursor pagination and mappings for Project models.
"""

from datetime import datetime

from geoalchemy2.shape import to_shape, from_shape
from shapely.geometry import box
from sqlalchemy import and_, or_, select

from app.db.models.project import Project as DbProject
from app.lib import database
from app.lib.exceptions import ResourceNotFoundError
from app.lib.responses import CursorPage
from app.schemas.geo import GeoPoint, GeoBoundingBox
from app.schemas.projects import ProjectResponse, ProjectCreateRequest
from app.constants.geo import STORAGE_SRID

def _db_project_to_wire(db_p: DbProject) -> ProjectResponse:
    """Map DB Project model to Project schema."""
    centroid_point = None
    if db_p.centroid:
        centroid_geom = to_shape(db_p.centroid)
        centroid_point = GeoPoint(latitude=centroid_geom.y, longitude=centroid_geom.x)
        
    aoi_box = None
    if db_p.area_of_interest:
        aoi_geom = to_shape(db_p.area_of_interest)
        bounds = aoi_geom.bounds
        if bounds:
            aoi_box = GeoBoundingBox(
                west=bounds[0],
                south=bounds[1],
                east=bounds[2],
                north=bounds[3]
            )

    return ProjectResponse(
        id=db_p.id,
        name=db_p.name,
        area_of_interest_name=db_p.area_of_interest_name or "Global AOI",
        area_of_interest=aoi_box,
        centroid=centroid_point,
        created_at=db_p.created_at,
        updated_at=db_p.updated_at,
        last_activity_at=db_p.last_activity_at or db_p.updated_at,
    )


async def list_projects(cursor: str | None = None, limit: int = 20) -> CursorPage[ProjectResponse]:
    """Retrieve cursor-paginated projects from database."""
    try:
        async with database.get_session() as session:
            query = select(DbProject).order_by(DbProject.updated_at.desc(), DbProject.id.desc()).limit(limit + 1)
            if cursor:
                cursor_project = await session.get(DbProject, cursor)
                if cursor_project is not None:
                    query = query.where(
                        or_(
                            DbProject.updated_at < cursor_project.updated_at,
                            and_(
                                DbProject.updated_at == cursor_project.updated_at,
                                DbProject.id < cursor_project.id,
                            ),
                        )
                    )
            result = await session.execute(query)
            rows = list(result.scalars().all())

            next_cursor = None
            if len(rows) > limit:
                next_cursor = rows[limit - 1].id
                rows = rows[:limit]

            items: list[ProjectResponse] = [_db_project_to_wire(r) for r in rows]

            return CursorPage(items=items, next_cursor=next_cursor, total_count=len(items))
    except Exception:
        return CursorPage(items=[], next_cursor=None, total_count=0)


async def get_project_by_id(project_id: str) -> ProjectResponse:
    """Retrieve a single project by ID from database."""
    async with database.get_session() as session:
        query = select(DbProject).where(DbProject.id == project_id)
        result = await session.execute(query)
        db_p = result.scalar_one_or_none()
        if db_p is not None:
            return _db_project_to_wire(db_p)

    raise ResourceNotFoundError(f"Project '{project_id}' does not exist.", details={"projectId": project_id})


async def create_project(request: ProjectCreateRequest) -> ProjectResponse:
    """Create a new project."""
    async with database.get_session() as session:
        # Create PostGIS geometry from bounding box
        shapely_box = box(
            request.area_of_interest.west,
            request.area_of_interest.south,
            request.area_of_interest.east,
            request.area_of_interest.north
        )
        shapely_centroid = shapely_box.centroid
        
        db_p = DbProject(
            name=request.name,
            area_of_interest_name=request.area_of_interest_name,
            area_of_interest=from_shape(shapely_box, srid=STORAGE_SRID),
            centroid=from_shape(shapely_centroid, srid=STORAGE_SRID)
        )
        session.add(db_p)
        await session.commit()
        await session.refresh(db_p)
        
        return _db_project_to_wire(db_p)
