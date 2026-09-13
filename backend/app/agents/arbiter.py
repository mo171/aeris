"""The language model's one vote in routing: when the neighbours cannot agree, it chooses within the family the rules allowed.

what  : `LlmArbiter`, an `Arbiter` for `services/query/classifier.py`; `build_arbiter()`.
where : `agents/router.py::routing_resources` builds one when a model is configured; `aeris route
        --evaluate` scores the cascade with and without it.
how   : Invoked only for a kNN decision whose margin is under `INTENT_UNCERTAIN_MARGIN` - one question
        in 235 on the held-out file. It is shown the question, the allowed intents (the family a cue
        narrowed to, or all nine) and the neighbours that voted, and answers with structured output: an
        intent from the allowed list and a reason. An intent outside the list is a rejected answer and the
        kNN's choice stands, so the model can refine a routing decision but never overrule a rule. A
        provider error is the same: the decision stands, the reason is logged.
"""

import logging

from pydantic import BaseModel, Field

from app.constants.intents import Intent
from app.lib.llm.chat_model import build_chat_model, chat_model_record
from app.services.prompts.agent import AGENT_SYSTEM_PROMPT, ARBITER_TEMPLATE

logger = logging.getLogger(__name__)


class Arbitration(BaseModel):
    intent: str = Field(description="One of the allowed intents, exactly as written.")
    reason: str = Field(description="One sentence.")


class LlmArbiter:
    def __init__(self, model) -> None:  # noqa: ANN001 - a LangChain chat model
        self._model = model.with_structured_output(Arbitration)
        self.version = chat_model_record().version if chat_model_record() else "llm"
        self.calls = 0

    async def __call__(
        self, query: str, candidates: frozenset[Intent], neighbours: tuple[tuple[str, Intent, float], ...]
    ) -> tuple[Intent, str] | None:
        """The model's choice within `candidates`, or `None` when it fails or steps outside them."""
        self.calls += 1
        prompt = ARBITER_TEMPLATE.format(
            query=query, candidates=", ".join(sorted(intent.value for intent in candidates)),
            neighbours="\n".join(f"- {similarity:.2f}  {intent.value}: {text}" for text, intent, similarity in neighbours) or "- none",
        )
        try:
            verdict = await self._model.ainvoke([("system", AGENT_SYSTEM_PROMPT), ("human", prompt)])
        except Exception as error:  # noqa: BLE001 - the kNN's decision stands; the provider's failure is logged
            logger.warning("intent arbitration failed; the neighbours' decision stands", extra={"reason": str(error)})
            return None
        try:
            chosen = Intent(verdict.intent.strip())
        except ValueError:
            logger.warning("arbiter named an unknown intent", extra={"intent": verdict.intent})
            return None
        if chosen not in candidates:
            logger.warning("arbiter stepped outside the allowed family; ignored", extra={"intent": chosen.value})
            return None
        return chosen, verdict.reason


def build_arbiter() -> LlmArbiter | None:
    model = build_chat_model()
    return LlmArbiter(model) if model is not None else None
