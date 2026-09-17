from typing import Any
from pydantic import BaseModel, Field

from app.schemas.orchestration import TaskSpec, Refusal
from app.agents.router import SceneFacts

class AgentObservation(BaseModel):
    task_id: str
    status: str
    claim: dict[str, Any] | None = None
    refusal: Refusal | None = None

class AgentState(BaseModel):
    user_request: str
    scene_facts: SceneFacts
    
    tasks: list[TaskSpec] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)
    observations: list[AgentObservation] = Field(default_factory=list)
    
    budget_tasks: int = 10
    max_tool_calls: int = 10
    max_execution_time: int = 300
    status: str = "running"
    final_answer: str | None = None
