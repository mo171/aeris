from typing import Any
import numpy as np

from app.schemas.orchestration import TaskSpec
from app.constants.model_ids import ModelId
from app.models.manager import ModelManager
from app.services.detection.detector import detect_objects
from app.services.query.ontology import canonicalize_target

async def execute_detect(task: TaskSpec, pictures: list[np.ndarray], manager: ModelManager) -> dict[str, Any]:
    """Execute object detection and format the result as a claim."""
    result = await detect_objects(pictures[0], manager=manager)
    
    target = canonicalize_target(task.target)
    count = result.count(target) if target else len(result.boxes)
    
    return {
        "type": "count",
        "target": target or "objects",
        "value": count,
        "latency_ms": result.latency_ms
    }
