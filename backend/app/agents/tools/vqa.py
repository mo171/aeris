from typing import Any
import numpy as np

from app.schemas.orchestration import TaskSpec
from app.models.manager import ModelManager
from app.services.vlm.reading import answer_question, read_pair
from app.services.prompts.vlm import SAR_IMAGE_NOTE

async def execute_vqa(task: TaskSpec, pictures: list[np.ndarray], sar: list[bool], manager: ModelManager) -> dict[str, Any]:
    """Execute Vision-Language Question Answering and format as a claim."""
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
