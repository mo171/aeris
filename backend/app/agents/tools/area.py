from typing import Any

from app.schemas.orchestration import TaskSpec

async def execute_area(task: TaskSpec) -> dict[str, Any]:
    """Mock execution for area calculation."""
    return {
        "type": "area",
        "target": task.target or "objects",
        "value": "Area calculated.",
    }
