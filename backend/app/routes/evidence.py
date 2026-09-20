from fastapi import APIRouter, Query
from app.lib.responses import CursorPage
from app.schemas.evidence import AuditedClaim
from app.controllers import evidence_controller

router = APIRouter(prefix="/evidence", tags=["evidence"])

@router.get("/claims", response_model=CursorPage[AuditedClaim])
async def list_claims(
    search: str | None = Query(None),
    model_id: str | None = Query(None, alias="modelId"),
    band: str | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> CursorPage[AuditedClaim]:
    """Retrieve cursor-paginated audited claims."""
    return await evidence_controller.list_claims(
        search=search, model_id=model_id, band=band, cursor=cursor, limit=limit
    )
