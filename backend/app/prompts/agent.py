"""Every prompt the agent's language model sees: the routing policy for arbitration, the plan's prose, the answer's prose, and interface control.

what  : `AGENT_SYSTEM_PROMPT`, `ARBITER_TEMPLATE`, `PLANNER_TEMPLATE`, `SYNTHESIS_TEMPLATE`, `INTERFACE_CONTROL_PROMPT_TEMPLATE`.
where : `agents/arbiter.py`, `agents/planner.py`, `agents/graph.py` (synthesis & interface control). Strings only; the
        vocabularies they mention are `constants/intents.py` and `constants/routing.py`.
how   : The model is told the policy it is asked to apply, because measured bare it does not know it.
        The arbiter is only ever asked to choose within the family the cues allowed; the planner is only ever asked to
        phrase steps that are already decided; synthesis copies placeholders and invents no number.
"""

from typing import Final

AGENT_SYSTEM_PROMPT: Final[str] = (
    "You are AERIS, an Earth-observation analysis assistant. Specialist tools measure; you route, plan and "
    "phrase. Every number in an answer comes from a specialist's claim, never from you. Routing policy: "
    "counts and detections of objects go to the object detector (DETECT), never to the vision-language "
    "model; spectral quantities (vegetation health, water, built-up, burn) are INDEX_QUERY; pixel masks and "
    "land cover are SEGMENT; questions about what a single picture shows are SCENE_VQA; locating a named "
    "thing is GROUND; two dates compared are CHANGE_DETECT (a map of where) or CHANGE_VQA (a fact about the "
    "change); optical and radar together are CROSS_MODAL; questions about earlier findings are "
    "EVIDENCE_RECALL."
)

ARBITER_TEMPLATE: Final[str] = (
    "The question is: \"{query}\"\n"
    "The rules allow these intents for it: {candidates}. Nearest labelled questions and their intents:\n"
    "{neighbours}\n"
    "Choose the single best intent from the allowed list and give a one-sentence reason."
)

PLANNER_TEMPLATE: Final[str] = (
    "An operator asked: \"{request}\"\n"
    "The router decided these steps, in order (each names its tool and what it will do):\n{steps}\n\n"
    "Write a one-sentence summary of the plan for the operator, and for each step a one-sentence "
    "description of what it will do and why. Keep the steps exactly as given - do not add, remove, "
    "reorder or merge them. State no number, count, area or percentage: nothing has been measured yet."
)

SYNTHESIS_TEMPLATE: Final[str] = (
    "The operator asked: \"{question}\"\n"
    "The specialists produced these findings, in the order the steps ran:\n{facts}\n{notes}\n"
    "Write the answer in plain English, two to five sentences of prose that will be read aloud - no heading, "
    "no list, no markdown, do not repeat the request - addressing every part of the request in "
    "order. Copy each placeholder such as {{m1}} exactly where its value belongs, and use every placeholder "
    "exactly once - a finding left out is a number the operator never hears. Do not invent any number, "
    "count, area or percentage that is not a placeholder; a figure written out in a finding (a resolution, "
    "a threshold) is copied exactly as written or left out, never rounded. Where a step was refused, say "
    "what could not be done and why, in the operator's terms. Do not add findings."
)

INTERFACE_CONTROL_PROMPT_TEMPLATE: Final[str] = (
    "The operator asked: {request!r}\n"
    "Validated interface resources:\n{resources}\n"
    "Allowed presentation capabilities:\n{capabilities}\n"
    "Select presentation capabilities to present the validated findings or progress to the operator.\n"
    "Instructions:\n"
    "1. If there is a validated finding claim in availableClaimIds, invoke spotlight_claim passing the exact claim ID from availableClaimIds.\n"
    "2. Pass ONLY the exact opaque id (e.g. from availableClaimIds, availableEvidenceIds, availableLayerIds) as the tool argument without any descriptions, labels, or colons.\n"
    "3. Never provide coordinates, measurements, counts, report paths, or invented values.\n"
    "4. Every tool call must include a concise reason with words only (no numerals)."
)
