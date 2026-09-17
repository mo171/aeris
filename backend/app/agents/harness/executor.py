from typing import Any
import numpy as np

from app.schemas.orchestration import TaskSpec
from app.constants.model_ids import ModelId
from app.models.manager import ModelManager
from app.services.detection.detector import detect_objects
from app.services.vlm.reading import answer_question, read_pair
from app.services.prompts.vlm import SAR_IMAGE_NOTE

from app.services.query.ontology import canonicalize_target

async def execute_task_locally(task: TaskSpec, tool_id: str, pictures: list[np.ndarray], sar: list[bool], manager: ModelManager) -> dict[str, Any]:
    """Execute a task immediately (bypassing MinIO graphs) to get real observations for Synthesis."""
    if tool_id == ModelId.DOTA_DETECTOR:
        result = await detect_objects(pictures[0], manager=manager)
        
        # Format the result as a claim
        target = canonicalize_target(task.target)
        count = result.count(target) if target else len(result.boxes)
        
        return {
            "type": "count",
            "target": target or "objects",
            "value": count,
            "latency_ms": result.latency_ms
        }
        
    elif tool_id == "vlm":
        if len(pictures) == 2:
            notes = tuple(SAR_IMAGE_NOTE if flag else None for flag in sar)
            reading = await read_pair(pictures[0], pictures[1], task.question or "Compare these.", manager=manager, notes=notes) # type: ignore
        else:
            reading = await answer_question(pictures[0], task.question or "What is in this image?", manager=manager, is_sar=sar[0])
            
        return {
            "type": "qualitative_presence",
            "target": task.target or "scene",
            "value": reading.text,
            "latency_ms": reading.latency_ms
        }
        
    else:
        return {
            "type": "unsupported_local_execution",
            "tool": tool_id,
            "value": "This tool requires a full scene graph (MinIO) and cannot be run directly on raw pictures yet."
        }
