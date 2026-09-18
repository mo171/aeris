from typing import Any
import numpy as np

from app.models.manager import ModelManager
from app.schemas.orchestration import TaskSpec
from app.services.query.ontology import canonicalize_target
from app.services.segmentation.segmenter import segment_image


async def execute_segment(
    task: TaskSpec,
    pictures: list[np.ndarray] | None = None,
    manager: ModelManager | None = None,
) -> dict[str, Any]:
    """Execute land-cover semantic segmentation on an acquisition."""
    if not pictures or len(pictures) == 0:
        raise ValueError("Segmentation requires at least one acquisition image.")
    if manager is None:
        raise ValueError("ModelManager is required to lease SegFormer.")

    result = await segment_image(pictures[0], manager=manager)
    target = canonicalize_target(task.target)

    # If target is specific class, compute coverage for that class
    judged = np.isfinite(result.confidence)
    total_judged = int(judged.sum())
    if target and target in result.class_names:
        class_idx = result.class_names.index(target)
        matched = int((result.class_map == class_idx).sum())
        coverage = (matched / total_judged) if total_judged > 0 else 0.0
        display_val = f"{target} segmented across {coverage * 100.0:.1f}% of observed area."
    else:
        target = target or "land_cover"
        coverage = 1.0 if total_judged > 0 else 0.0
        display_val = f"Land cover segmented into {len(result.class_names)} classes."

    return {
        "type": "segmentation",
        "target": target,
        "value": display_val,
        "coverage_fraction": coverage,
        "classes": list(result.class_names),
        "confidence": result.stated_confidence,
        "model_id": result.model_id.value if hasattr(result.model_id, "value") else str(result.model_id),
        "model_version": result.model_version,
        "latency_ms": result.latency_ms,
    }
