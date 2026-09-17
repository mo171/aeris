from typing import Any
import numpy as np

from app.schemas.orchestration import TaskSpec
from app.constants.model_ids import ModelId
from app.models.manager import ModelManager
from app.services.detection.detector import detect_objects
from app.services.vlm.reading import answer_question, read_pair
from app.services.prompts.vlm import SAR_IMAGE_NOTE

from app.services.query.ontology import canonicalize_target

from app.agents.tools.detect import execute_detect
from app.agents.tools.vqa import execute_vqa
from app.agents.tools.change import execute_change
from app.agents.tools.segment import execute_segment
from app.agents.tools.cross_modal import execute_cross_modal
from app.agents.tools.area import execute_area

async def execute_task_locally(task: TaskSpec, tool_id: str, pictures: list[np.ndarray], sar: list[bool], manager: ModelManager) -> dict[str, Any]:
    """Execute a task using the Layer 3 tools API."""
    if tool_id == ModelId.DOTA_DETECTOR:
        return await execute_detect(task, pictures, manager)
        
    elif tool_id == "vlm":
        return await execute_vqa(task, pictures, sar, manager)
        
    elif tool_id == "changeformer":
        return await execute_change(task)
        
    elif tool_id == "segformer":
        return await execute_segment(task)
        
    elif tool_id == "optical-sar-fusion":
        return await execute_cross_modal(task)
        
    elif tool_id == "evidence_recall":
        return await execute_area(task)
        
    else:
        return {
            "type": "unsupported_local_execution",
            "tool": tool_id,
            "value": "This tool requires a full scene graph (MinIO) and cannot be run directly on raw pictures yet."
        }
