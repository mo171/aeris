from typing import Any
import numpy as np

from app.models.manager import ModelManager
from app.schemas.orchestration import TaskSpec
from app.services.change_detection.detector import detect_change


async def execute_change(
    task: TaskSpec,
    pictures: list[np.ndarray] | None = None,
    manager: ModelManager | None = None,
) -> dict[str, Any]:
    """Execute change detection between two temporal images."""
    if not pictures or len(pictures) < 2:
        raise ValueError("Change detection requires two temporal acquisitions (T0 and T1).")
    if manager is None:
        raise ValueError("ModelManager is required to lease ChangeFormer.")

    result = await detect_change(pictures[0], pictures[1], manager=manager)
    target = task.target or "surface_change"
    pct = result.changed_fraction * 100.0

    return {
        "type": "change_detection",
        "target": target,
        "value": f"Surface change detected across {pct:.1f}% of observed area.",
        "changed_fraction": result.changed_fraction,
        "confidence": result.confidence,
        "model_id": result.model_id.value if hasattr(result.model_id, "value") else str(result.model_id),
        "model_version": result.model_version,
        "latency_ms": result.latency_ms,
    }
