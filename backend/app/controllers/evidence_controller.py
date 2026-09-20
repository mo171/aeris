from typing import Any
from sqlalchemy import and_, desc, or_, select
from app.db.models.claim import Claim
from app.db.models.run import Run
from app.db.models.investigation import Investigation, InvestigationScene
from app.db.models.evidence import Evidence
from app.lib import database
from app.lib.responses import CursorPage
from app.schemas.evidence import AuditedClaim, AuditEvidenceItem, ClaimMetric

async def list_claims(
    search: str | None = None,
    model_id: str | None = None,
    band: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
) -> CursorPage[AuditedClaim]:
    async with database.get_session() as session:
        query = (
            select(Claim, Run, Investigation)
            .join(Run, Claim.run_id == Run.id)
            .join(Investigation, Run.investigation_id == Investigation.id)
            .order_by(desc(Claim.created_at), desc(Claim.id))
            .limit(limit + 1)
        )

        if search:
            query = query.where(Claim.text.ilike(f"%{search}%"))
        
        if model_id:
            query = query.where(Claim.model_id == model_id)
            
        if band:
            if band == "high":
                query = query.where(Claim.confidence >= 0.8)
            elif band == "medium":
                query = query.where((Claim.confidence >= 0.5) & (Claim.confidence < 0.8))
            elif band == "low":
                query = query.where(Claim.confidence < 0.5)
            elif band == "none":
                query = query.where(Claim.confidence.is_(None))
                
        if cursor:
            cursor_claim = await session.get(Claim, cursor)
            if cursor_claim is not None:
                query = query.where(
                    or_(
                        Claim.created_at < cursor_claim.created_at,
                        and_(
                            Claim.created_at == cursor_claim.created_at,
                            Claim.id < cursor_claim.id,
                        ),
                    )
                )

        result = await session.execute(query)
        rows = list(result.all())

        next_cursor = None
        if len(rows) > limit:
            next_cursor = rows[limit - 1][0].id
            rows = rows[:limit]

        items = []
        for claim, run, inv in rows:
            # Fetch evidence items
            ev_items = []
            if claim.evidence_ids:
                ev_query = select(Evidence).where(Evidence.id.in_(claim.evidence_ids))
                ev_res = await session.execute(ev_query)
                for ev in ev_res.scalars().all():
                    ev_items.append(
                        AuditEvidenceItem(
                            id=ev.id,
                            kind=str(ev.kind),
                            title=ev.title,
                            area_hectares=ev.area_hectares,
                            magnitude=ev.magnitude,
                            confidence=ev.confidence,
                        )
                    )
            
            # Fetch source scenes
            scene_query = select(InvestigationScene.scene_id).where(InvestigationScene.investigation_id == inv.id)
            scene_res = await session.execute(scene_query)
            source_scene_ids = list(scene_res.scalars().all())

            metrics = []
            for m in claim.metrics:
                metrics.append(ClaimMetric(
                    label=m.get("label", ""),
                    value=float(m.get("value", 0.0)),
                    unit=m.get("unit", ""),
                    direction=m.get("direction", ""),
                    precision=int(m.get("precision", 0)),
                ))

            items.append(
                AuditedClaim(
                    claim_id=claim.id,
                    run_id=run.id,
                    text=claim.text,
                    kind=str(claim.kind),
                    confidence=claim.confidence,
                    model_id=str(claim.model_id),
                    model_version=claim.model_version,
                    trace_step_id=claim.trace_step_id,
                    investigation_id=inv.id,
                    investigation_name=inv.name,
                    area_of_interest_name=inv.area_of_interest_name,
                    evidence_count=len(claim.evidence_ids),
                    evidence_items=ev_items,
                    metrics=metrics,
                    is_primary=claim.is_primary,
                    investigation_status=str(inv.status),
                    source_scene_ids=source_scene_ids,
                    produced_at=claim.created_at,
                )
            )

        return CursorPage(items=items, next_cursor=next_cursor, total_count=len(items))
