import logging
from typing import Any
from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from app.schemas.orchestration import Refusal
from app.prompts.harness import HARNESS_SYNTHESIS_USER_TEMPLATE, SYNTHESIS_SYSTEM

logger = logging.getLogger(__name__)

async def synthesize_response(claims: list[dict[str, Any]], refusals: list[Refusal], model: BaseChatModel) -> str:
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYNTHESIS_SYSTEM),
        ("human", HARNESS_SYNTHESIS_USER_TEMPLATE)
    ])
    
    refusal_dicts = [r.model_dump() for r in refusals]
    try:
        chain = prompt | model
        response = await chain.ainvoke({"claims": claims, "refusals": refusal_dicts})
        return response.content
    except Exception as error:
        logger.error(f"Synthesis failed: {error}")
        return "The analysis completed, but I encountered an error formatting the results."
