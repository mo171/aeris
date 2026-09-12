"""Carries the fleet's health to the operator's fleet strip: which models are up, how busy, how slow.

what  : `ModelStatus` and `ModelStatusCollection`, mirroring `modelStatusSchema` and
        `modelStatusCollectionSchema` in `model.schema.ts`.
where : Built by `app/models/manager.py`'s `status()`; printed by `aeris models status` in Phase 1 and
        served by `GET /models/status` in Phase 2.1.
how   : `health` is the four-state vocabulary the frontend renders (`constants/statuses.py`,
        `ModelHealth`); `queueDepth` is how many callers are waiting on the model right now, and
        `medianLatencyMs` is the median of its recent inferences. `version` is the fleet record's - what a
        claim carries as `modelVersion` - so the strip and the claims can be joined.
"""

from datetime import datetime

from pydantic import Field

from app.constants.model_ids import ModelId
from app.constants.statuses import ModelHealth
from app.lib.responses import CamelCaseModel


class ModelStatus(CamelCaseModel):
    id: ModelId
    version: str = Field(min_length=1)
    health: ModelHealth
    median_latency_ms: int = Field(ge=0)
    queue_depth: int = Field(ge=0)


class ModelStatusCollection(CamelCaseModel):
    models: list[ModelStatus]
    checked_at: datetime
