import logging
from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.schemas.orchestration import TaskSpec
from app.constants.intents import Intent
from app.services.prompts.harness import PLANNER_SYSTEM

logger = logging.getLogger(__name__)

class PlanResponse(BaseModel):
    tasks: list[TaskSpec] = Field(..., description="The planned execution tasks.")

async def plan_request(request: str, model: BaseChatModel, available_inputs: list[str]) -> list[TaskSpec]:
    """Decompose a request into an inspectable array of TaskSpecs."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_SYSTEM),
        ("human", "Available inputs: {inputs}\n\nRequest: {request}")
    ])
    
    try:
        # Enforce budget/limits on output length via LLM configuration or max tasks validation
        chain = prompt | model.with_structured_output(PlanResponse)
        response = await chain.ainvoke({"request": request, "inputs": ", ".join(available_inputs)})
        
        # Hard execution budget check
        if len(response.tasks) > 10:
            logger.warning("Planner generated too many tasks, truncating to 10.")
            return response.tasks[:10]
            
        return response.tasks
    except Exception as error:
        logger.error(f"LLM planning failed: {error}")
        raise
