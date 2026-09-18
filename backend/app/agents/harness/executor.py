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
    if tool_id in (ModelId.DOTA_DETECTOR, "dota-detector"):
        return await execute_detect(task, pictures, manager)
        
    elif tool_id in ("vlm", ModelId.REMOTE_SENSING_VLM):
        return await execute_vqa(task, pictures, sar, manager)
        
    elif tool_id in ("changeformer", ModelId.CHANGEFORMER):
        return await execute_change(task, pictures, manager)
        
    elif tool_id in ("segformer", ModelId.SEGFORMER_LANDCOVER):
        return await execute_segment(task, pictures, manager)
        
    elif tool_id in ("optical-sar-fusion", "fusion"):
        return await execute_cross_modal(task, pictures, sar, manager)
        
    elif tool_id in ("evidence_recall", "area", "geospatial-engine"):
        return await execute_area(task, pictures)
        
    else:
        return {
            "type": "unsupported_local_execution",
            "tool": tool_id,
            "value": "This tool requires a full scene graph (MinIO) and cannot be run directly on raw pictures yet."
        }
