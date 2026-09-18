from datetime import UTC, datetime
from typing import Any
import numpy as np

from app.models.manager import ModelManager
from app.schemas.orchestration import TaskSpec
from app.services.optical_sar.math.fusion_rules import assess_pair


async def execute_cross_modal(
    task: TaskSpec,
    pictures: list[np.ndarray] | None = None,
    sar: list[bool] | None = None,
    manager: ModelManager | None = None,
    optical_captured_at: datetime | None = None,
    radar_captured_at: datetime | None = None,
    residual_pixels: float | None = 0.35,
) -> dict[str, Any]:
    """Execute cross-modal optical-SAR feasibility assessment and late-fusion rules."""
    now = datetime.now(UTC)
    opt_time = optical_captured_at or now
    rad_time = radar_captured_at or now

    assessment = assess_pair(opt_time, rad_time, residual_pixels)

    return {
        "type": "cross_modal_analysis",
        "target": task.target or "optical_sar_pair",
        "value": f"Cross-modal pair assessment: {assessment.verdict} ({', '.join(assessment.notes)})",
        "verdict": assessment.verdict,
        "offset_days": assessment.offset_days,
        "co_registration_pixels": assessment.co_registration_pixels,
        "notes": list(assessment.notes),
        "refusal": assessment.refusal,
    }
