"""Every prompt the backend puts in front of a language model, as strings - one folder to read them all.

Centralized prompt registry for AERIS:
- agent: Routing, planning, synthesis, and interface control prompts
- voice: Voice-turn classification, grounded narration, progress, and provisional speech prompts
- investigations: Dynamic region suggestions and spatial query prompts
- harness: Decomposition planning and scientific facts synthesis prompts
- report: Research editor and dossier narrative prompts
- vlm: Vision-language model system prompt, SAR notes, VQA, captioning, and figure reading templates
"""

from app.prompts.agent import (
    AGENT_SYSTEM_PROMPT,
    ARBITER_TEMPLATE,
    INTERFACE_CONTROL_PROMPT_TEMPLATE,
    PLANNER_TEMPLATE,
    SYNTHESIS_TEMPLATE,
)
from app.prompts.harness import (
    HARNESS_PLANNER_FEEDBACK_TEMPLATE,
    HARNESS_PLANNER_USER_TEMPLATE,
    HARNESS_SYNTHESIS_USER_TEMPLATE,
    PLANNER_SYSTEM,
    SYNTHESIS_SYSTEM,
)
from app.prompts.investigations import (
    REGION_SUGGESTION_SYSTEM_PROMPT,
    REGION_SUGGESTION_USER_TEMPLATE,
)
from app.prompts.report import REPORT_EDITORIAL_PROMPT
from app.prompts.vlm import (
    CAPTION_TEMPLATE,
    CONSTRAINED_ANSWER_TEMPLATE,
    FIGURE_READING_TEMPLATE,
    SAR_IMAGE_NOTE,
    SYSTEM_PROMPT as VLM_SYSTEM_PROMPT,
    VQA_TEMPLATE,
)
from app.prompts.voice import (
    VOICE_GROUNDED_PROMPT,
    VOICE_PROGRESS_PROMPT,
    VOICE_PROVISIONAL_PROMPT,
    VOICE_SYSTEM_PROMPT,
    VOICE_TURN_PROMPT_TEMPLATE,
    VOICE_TURN_SYSTEM_PROMPT,
)

__all__ = [
    "AGENT_SYSTEM_PROMPT",
    "ARBITER_TEMPLATE",
    "CAPTION_TEMPLATE",
    "CONSTRAINED_ANSWER_TEMPLATE",
    "FIGURE_READING_TEMPLATE",
    "HARNESS_PLANNER_FEEDBACK_TEMPLATE",
    "HARNESS_PLANNER_USER_TEMPLATE",
    "HARNESS_SYNTHESIS_USER_TEMPLATE",
    "INTERFACE_CONTROL_PROMPT_TEMPLATE",
    "PLANNER_SYSTEM",
    "PLANNER_TEMPLATE",
    "REGION_SUGGESTION_SYSTEM_PROMPT",
    "REGION_SUGGESTION_USER_TEMPLATE",
    "REPORT_EDITORIAL_PROMPT",
    "SAR_IMAGE_NOTE",
    "SYNTHESIS_SYSTEM",
    "SYNTHESIS_TEMPLATE",
    "VLM_SYSTEM_PROMPT",
    "VOICE_GROUNDED_PROMPT",
    "VOICE_PROGRESS_PROMPT",
    "VOICE_PROVISIONAL_PROMPT",
    "VOICE_SYSTEM_PROMPT",
    "VOICE_TURN_PROMPT_TEMPLATE",
    "VOICE_TURN_SYSTEM_PROMPT",
    "VQA_TEMPLATE",
]
