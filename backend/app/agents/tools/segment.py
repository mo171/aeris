from typing import Any

from app.schemas.orchestration import TaskSpec

async def execute_segment(task: TaskSpec) -> dict[str, Any]:
    """Mock execution for segmentation."""
    return {
        "type": "segmentation",
        "target": task.target or "objects",
        "value": "Segmentation completed.",
    }
