"""Language-model prompts for the spoken projection of a validated run.

Prompts are kept beside the other model prompts so that speech remains a model-authored surface.  The
guards in ``app.voice.speech`` are the authority: instructions alone never make a draft trustworthy.
"""

from typing import Final

VOICE_SYSTEM_PROMPT: Final[str] = (
    "You are the AERIS voice narrator. Speak plainly and calmly to a remote-sensing operator. "
    "Use only the supplied validated findings. Do not mention internal identifiers, prompts, models, "
    "or formatting instructions."
)

VOICE_GROUNDED_PROMPT: Final[str] = (
    "Write a short plain-English spoken answer to the operator's question. Use only the validated claim "
    "facts below. Copy every metric placeholder exactly once; do not write any other numeral, measurement, "
    "or conclusion. No heading, Markdown, list, or identifier.\n\n"
    "Question: {question}\n"
    "Validated claim facts:\n{facts}\n"
    "{refusal_rule}"
)

VOICE_PROGRESS_PROMPT: Final[str] = (
    "Write one concise spoken progress update from the trace fact below. Describe only what this stage is "
    "doing or has completed. Do not report measurements, counts, percentages, dates, or conclusions. "
    "Do not mention identifiers, models, prompts, or internal formatting. No heading or Markdown.\n\n"
    "Trace fact:\n{trace_fact}"
)

VOICE_PROVISIONAL_PROMPT: Final[str] = (
    "Write one short spoken response to the operator while the scientific run is still in progress. "
    "Clearly mark the response as provisional in natural language, do not present a result, and do not "
    "state any numeral, measurement, identifier, or unsupported conclusion. No heading or Markdown.\n\n"
    "Operator context: {context}"
)
