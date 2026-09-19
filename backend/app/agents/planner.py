import logging
from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from app.schemas.orchestration import TaskSpec
from app.constants.intents import Intent
from app.prompts.harness import (
    HARNESS_PLANNER_FEEDBACK_TEMPLATE,
    HARNESS_PLANNER_USER_TEMPLATE,
    PLANNER_SYSTEM,
)

logger = logging.getLogger(__name__)

class PlanResponse(BaseModel):
    tasks: list[TaskSpec] = Field(..., description="The planned execution tasks.")

async def plan_request(request: str, model: BaseChatModel, available_inputs: list[str], feedback: str = "") -> list[TaskSpec]:
    """Decompose a request into an inspectable array of TaskSpecs."""
    
    user_prompt = HARNESS_PLANNER_USER_TEMPLATE
    if feedback:
        user_prompt += HARNESS_PLANNER_FEEDBACK_TEMPLATE
        
    prompt = ChatPromptTemplate.from_messages([
        ("system", PLANNER_SYSTEM),
        ("human", user_prompt)
    ])
    
    try:
        # Enforce budget/limits on output length via LLM configuration or max tasks validation
        chain = prompt | model.with_structured_output(PlanResponse)
        response = await chain.ainvoke({"request": request, "inputs": ", ".join(available_inputs), "feedback": feedback})
        
        # Hard execution budget check
        if len(response.tasks) > 10:
            logger.warning("Planner generated too many tasks, truncating to 10.")
            return response.tasks[:10]
            
        return response.tasks
    except Exception as error:
        logger.error(f"LLM planning failed: {error}")
        raise
