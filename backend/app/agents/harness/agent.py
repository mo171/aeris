import logging
from typing import Any
import numpy as np
from langchain_core.language_models import BaseChatModel

from app.agents.harness.state import AgentState, AgentObservation
from app.agents.planner import plan_request
from app.agents.registry import CapabilityRegistry
from app.agents.synthesis import synthesize_response
from app.models.manager import ModelManager

logger = logging.getLogger(__name__)

async def run_harness(
    request: str, 
    facts: Any, 
    model: BaseChatModel,
    pictures: list[np.ndarray] | None = None,
    sar: list[bool] | None = None,
    manager: ModelManager | None = None
) -> str:
    """
    Layer 1: Agent Harness (Cognitive Loop)
    """
    state = AgentState(user_request=request, scene_facts=facts)
    registry = CapabilityRegistry()
    
    # Understand & Plan
    inputs = ["image_T0"]
    if facts.image_count >= 2:
        inputs.append("image_T1")
        
    state.tasks = await plan_request(request, model, inputs)
    logger.info("Agent planned %d tasks.", len(state.tasks))
    
    import time
    start_time = time.time()
    tool_calls = 0
    
    # Loop over planned tasks
    for task in state.tasks:
        if len(state.completed_tasks) >= state.budget_tasks:
            logger.warning("Agent hit task budget limit.")
            break
        if tool_calls >= state.max_tool_calls:
            logger.warning("Agent hit max tool calls limit.")
            break
        if (time.time() - start_time) > state.max_execution_time:
            logger.warning("Agent hit execution time limit.")
            break
            
        tool_calls += 1
            
        # Feasibility check (Layer 2)
        capability, refusal = registry.check_feasibility(task, facts)
        
        if refusal:
            # Observation: scientific refusal
            obs = AgentObservation(task_id=task.task_id, status="REJECTED", refusal=refusal)
            state.observations.append(obs)
            logger.info("Agent observes failure on task %s: %s", task.task_id, refusal.code)
            # Future enhancement: Here the agent can decide to re-plan by calling the LLM planner again
            # with the observation history.
        else:
            # Execute (Layer 3 via tools)
            if pictures and sar and manager and capability:
                from app.agents.harness.executor import execute_task_locally
                claim = await execute_task_locally(task, capability.id, pictures, sar, manager)
            else:
                claim = {
                    "claim_id": f"c_{task.task_id}",
                    "type": "execution",
                    "value": "completed",
                    "source": capability.id if capability else "unknown"
                }
                
            obs = AgentObservation(task_id=task.task_id, status="VALID", claim=claim)
            state.observations.append(obs)
            state.completed_tasks.append(task.task_id)
            
    # Final Synthesis
    claims = [obs.claim for obs in state.observations if obs.claim]
    refusals = [obs.refusal for obs in state.observations if obs.refusal]
    
    state.final_answer = await synthesize_response(claims, refusals, model)
    return state.final_answer
