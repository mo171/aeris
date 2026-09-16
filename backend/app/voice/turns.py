"""Structured LLM output for classifying one operator voice turn.

The classifier asks a separately scoped model call what the operator wants. Every decision is the model's;
no keyword, regex, or vocabulary shortcut can reach ``RunHandle.abandon()`` or bypass the structured output.
The session coordinator dispatches on the returned ``VoiceTurnAction`` enum, which is exhaustive.
"""

import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

VOICE_TURN_SYSTEM_PROMPT = (
    "You are the AERIS voice-turn classifier. The operator spoke one sentence during an Earth-observation "
    "analysis session. Classify the operator's intent into exactly one action. Respond with structured JSON.\n\n"
    "Actions:\n"
    "- approve_all: The operator wants to run every planned step as-is.\n"
    "- approve_plan: The operator approves the plan (same as approve_all unless they specify steps).\n"
    "- modify_plan: The operator wants to keep only specific steps. List the step ids they mention.\n"
    "- question: The operator is asking a question or making a comment unrelated to plan approval or session control.\n"
    "- abandon: The operator explicitly wants to stop/cancel/abort the current scientific run.\n"
    "- standby: The operator wants to mute/silence/pause speech output while the run continues.\n"
    "- resume: The operator wants to unmute/restore speech output.\n\n"
    "Rules:\n"
    "- If the operator says anything like 'yes', 'go ahead', 'run it', 'looks good', 'proceed', classify as approve_all.\n"
    "- Only classify as abandon when the operator EXPLICITLY asks to stop the analysis.\n"
    "- A question about the analysis is 'question', not 'abandon'.\n"
    "- Prefer approve_all over approve_plan unless the operator restricts to specific steps."
)


class VoiceTurnAction(StrEnum):
    """Every action the voice coordinator can take after one operator turn."""

    APPROVE_ALL = "approve_all"
    APPROVE_PLAN = "approve_plan"
    MODIFY_PLAN = "modify_plan"
    QUESTION = "question"
    ABANDON = "abandon"
    STANDBY = "standby"
    RESUME = "resume"


class VoiceTurnDecision(BaseModel):
    """Structured output from the language model classifying one operator turn."""

    action: VoiceTurnAction = Field(
        description="The classified operator intent."
    )
    enabled_step_ids: list[str] = Field(
        default_factory=list,
        description="Step ids to keep when action is modify_plan. Empty for all other actions.",
    )
    response: str = Field(
        default="",
        description="Natural-language response text when action is question. Empty for other actions.",
    )


def _turn_prompt(transcript: str, session_context: str) -> str:
    return (
        f"Session state: {session_context}\n"
        f"Operator said: {transcript!r}\n\n"
        "Classify the operator's intent."
    )


async def classify_voice_turn(
    transcript: str,
    *,
    session_context: str = "",
    model: Any = None,
) -> VoiceTurnDecision:
    """Ask the LLM to classify one operator turn into a structured action.

    Falls back to ``question`` only when the model itself is unavailable — never from a keyword match.
    """
    if model is None:
        try:
            from app.lib.llm.chat_model import require_chat_model

            model = await require_chat_model()
        except Exception as error:  # noqa: BLE001 — model unavailability is a typed voice error
            from app.lib.exceptions import SpeechGenerationError

            raise SpeechGenerationError(
                "The language model is unavailable for voice-turn classification.",
                details={"upstream": "llm", "reason": str(error)},
            ) from error

    prompt = _turn_prompt(transcript, session_context)

    # Use with_structured_output when available (LangChain models), otherwise parse manually
    structured_model = getattr(model, "with_structured_output", None)
    if structured_model is not None:
        try:
            structured = structured_model(VoiceTurnDecision)
            result = await structured.ainvoke([
                ("system", VOICE_TURN_SYSTEM_PROMPT),
                ("human", prompt),
            ])
            if isinstance(result, VoiceTurnDecision):
                return result
            # Some providers return a dict
            return VoiceTurnDecision.model_validate(result)
        except Exception:  # noqa: BLE001 — structured output may not be supported; fall through to manual
            logger.debug("with_structured_output failed; falling back to manual parse", exc_info=True)

    # Manual parse path for models that don't support structured output
    try:
        import json

        reply = await model.ainvoke([
            ("system", VOICE_TURN_SYSTEM_PROMPT + "\n\nRespond ONLY with valid JSON matching this schema: "
             '{"action": "<action>", "enabled_step_ids": [], "response": ""}'),
            ("human", prompt),
        ])
        content = getattr(reply, "content", str(reply)).strip()
        # Extract JSON from possible markdown fences
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        data = json.loads(content)
        return VoiceTurnDecision.model_validate(data)
    except Exception as error:  # noqa: BLE001 — classification failure is typed
        from app.lib.exceptions import SpeechGenerationError

        raise SpeechGenerationError(
            "Voice-turn classification failed.",
            details={"upstream": "llm", "reason": str(error)},
        ) from error
