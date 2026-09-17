from typing import Any

from app.schemas.orchestration import TaskSpec

async def execute_change(task: TaskSpec) -> dict[str, Any]:
    """Mock execution for change detection."""
    return {
        "type": "change_detection",
        "target": task.target or "changes",
        "value": "Change detected.",
    }
