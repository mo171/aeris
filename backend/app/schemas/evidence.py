from datetime import datetime
from pydantic import Field
from typing import Any

from app.lib.responses import CamelCaseModel

class AuditEvidenceItem(CamelCaseModel):
    id: str
    kind: str
    title: str
    area_hectares: float | None = None
    magnitude: float
    confidence: float | None = None

class ClaimMetric(CamelCaseModel):
    label: str
    value: float
    unit: str
    direction: str
    precision: int

class AuditedClaim(CamelCaseModel):
    claim_id: str
    run_id: str
    text: str
    kind: str
    confidence: float | None
    
    model_id: str
    model_version: str
    trace_step_id: str
    
    investigation_id: str
    investigation_name: str
    area_of_interest_name: str
    
    evidence_count: int
    evidence_items: list[AuditEvidenceItem]
    metrics: list[ClaimMetric]
    is_primary: bool
    investigation_status: str
    
    source_scene_ids: list[str]
    produced_at: datetime
