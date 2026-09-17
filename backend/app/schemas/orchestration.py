from typing import Any, Literal
from pydantic import BaseModel, Field
from app.constants.intents import Intent

class TaskSpec(BaseModel):
    """A single deterministic task defined by the LLM Planner."""
    task_id: str = Field(..., description="Unique ID for the task within the plan (e.g. 'T1')")
    intent: Intent = Field(..., description="The scientific intent to execute")
    target: str | None = Field(None, description="The object, class, or entity to operate on (e.g., 'ship', 'buildings')")
    question: str | None = Field(None, description="The natural language question to answer, if applicable")
    inputs: list[str] = Field(default_factory=list, description="List of input identifiers (e.g. 'image_T0')")
    dependencies: list[str] = Field(default_factory=list, description="List of task_ids this task depends on")
    requested_outputs: list[str] = Field(default_factory=list, description="Requested output capabilities (e.g., 'count', 'bounding_boxes', 'qualitative_presence')")

class Refusal(BaseModel):
    """A typed refusal returned by the Feasibility Engine when a task is not executable."""
    code: str
    target: str | None
    reason: str
    gsd: float | None = None
    required_max_gsd: float | None = None
