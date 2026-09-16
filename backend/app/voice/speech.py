"""AI-authored, evidence-bound speech text.

Speech is a projection of claims and trace facts, never a re-reading of report Markdown.  The model may
choose wording, while the existing placeholder/numeral guard decides whether that wording can cross the
speech boundary.  An invalid second draft is an explicit failure; fixed prose is not a production fallback.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.constants.events import AnalysisEventType
from app.constants.vlm import NUMERAL_PATTERN, PLACEHOLDER_PATTERN
from app.lib.exceptions import SpeechGenerationError
from app.schemas.events.voice import SpeechEvent, SpeechKind
from app.services.answer.constrained import Fact, facts_from_claims, fill_placeholders, verify_phrasing
from app.services.prompts.voice import (
    VOICE_GROUNDED_PROMPT,
    VOICE_PROGRESS_PROMPT,
    VOICE_PROVISIONAL_PROMPT,
    VOICE_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)
_INTERNAL_IDENTIFIER = re.compile(r"\b(?:run|clm|stp|lyr|ev|fig|utt)_[A-Za-z0-9_-]+\b|\bS\d+[A-Za-z0-9_-]*\b", re.IGNORECASE)
# Number words are a lexical representation of the same scientific invariant as NUMERAL_PATTERN.  Keeping
# this small, closed parsing vocabulary here prevents a model from smuggling an unvalidated count as prose.
_CARDINAL_WORDS = frozenset(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand million billion".split()
)
_ORDINAL_WORDS = frozenset(
    "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth "
    "fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth thirtieth fortieth fiftieth "
    "sixtieth seventieth eightieth ninetieth hundredth thousandth millionth billionth".split()
)
_CARDINAL_VALUES = {
    word: value
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_CARDINAL_VALUES.update(dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10), strict=True)))
_CARDINAL_VALUES.update({"hundred": 100, "thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000})
_ORDINAL_VALUES = {
    word: value
    for value, word in enumerate(
        "zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth".split()
    )
}
_ORDINAL_VALUES.update(dict(zip("twentieth thirtieth fortieth fiftieth sixtieth seventieth eightieth ninetieth".split(), (20, 30, 40, 50, 60, 70, 80, 90), strict=True)))
_ORDINAL_VALUES.update({"hundredth": 100, "thousandth": 1_000, "millionth": 1_000_000, "billionth": 1_000_000_000})


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    """The operator context needed to author one grounded utterance."""

    question: str = ""
    run_id: str | None = None
    refusal: str | None = None
    supersedes_utterance_id: str | None = None
    context: str | None = None


@dataclass(frozen=True, slots=True)
class AuthoredSpeech:
    """Validated model prose plus the truth metadata needed by ``SpeechEvent``."""

    text: str
    claim_ids: tuple[str, ...] = ()
    kind: SpeechKind | str = SpeechKind.GROUNDED
    interruptible: bool = True
    provisional: bool = False
    supersedes_utterance_id: str | None = None
    model_version: str | None = None
    utterance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(self, "kind", SpeechKind(self.kind))
        object.__setattr__(self, "claim_ids", tuple(self.claim_ids))
        if not self.text:
            raise ValueError("speech text cannot be empty")
        if self.kind is SpeechKind.PROVISIONAL and self.claim_ids:
            raise ValueError("provisional speech cannot carry claim ids")
        if self.kind is SpeechKind.GROUNDED and not self.claim_ids:
            raise ValueError("grounded speech requires claim ids")
        if self.kind is SpeechKind.REFUSAL and self.interruptible:
            object.__setattr__(self, "interruptible", False)
        expected_provisional = self.kind is SpeechKind.PROVISIONAL
        if self.provisional != expected_provisional:
            raise ValueError("provisional must match the speech kind")

    def to_event(self, *, run_id: str, utterance_id: str, audio_url: str | None = None) -> SpeechEvent:
        """Build the wire event only after an utterance identity has been assigned."""
        return SpeechEvent(
            type=AnalysisEventType.SPEECH,
            run_id=run_id,
            utterance_id=utterance_id,
            kind=self.kind,
            text=self.text,
            audio_url=audio_url,
            claim_ids=list(self.claim_ids),
            interruptible=self.interruptible,
            provisional=self.provisional,
            supersedes_utterance_id=self.supersedes_utterance_id,
        )


def _request(value: SpeechRequest | str | dict[str, Any]) -> SpeechRequest:
    if isinstance(value, SpeechRequest):
        return value
    if isinstance(value, str):
        return SpeechRequest(question=value)
    if isinstance(value, dict):
        return SpeechRequest(
            question=str(value.get("question", "")),
            run_id=value.get("run_id", value.get("runId")),
            refusal=value.get("refusal"),
            supersedes_utterance_id=value.get("supersedes_utterance_id", value.get("supersedesUtteranceId")),
            context=value.get("context", value.get("trace", value.get("active_trace"))),
        )
    raise TypeError("speech request must be SpeechRequest, text, or mapping")


def _content(reply: Any) -> str:
    content = getattr(reply, "content", reply)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(item.get("text", "") for item in content if isinstance(item, dict)).strip()
    return str(content).strip()


async def _model_or_raise(model: Any) -> Any:
    if model is not None:
        return model
    try:
        from app.lib.llm.chat_model import require_chat_model

        return await require_chat_model()
    except Exception as error:  # noqa: BLE001 - dependency errors become one typed speech error
        raise SpeechGenerationError(
            "The language model is unavailable for speech generation.",
            details={"upstream": "llm", "reason": str(error)},
        ) from error


async def _invoke(model: Any, prompt: str) -> tuple[str, str | None]:
    try:
        reply = await model.ainvoke([("system", VOICE_SYSTEM_PROMPT), ("human", prompt)])
    except Exception as error:  # noqa: BLE001 - provider failures must be typed at this boundary
        raise SpeechGenerationError(
            "The language-model provider failed while authoring speech.",
            details={"upstream": "llm", "reason": str(error)},
        ) from error
    text = _content(reply)
    if not text:
        raise SpeechGenerationError("The language model returned empty speech.", details={"upstream": "llm"})
    return text, getattr(model, "version", None)


def _grounding_reason(text: str, facts: list[Fact], refusal: str | None) -> str | None:
    # A typed refusal is itself validated evidence. Include it in the guard's permitted numeral vocabulary
    # without making it a claim or allowing the model to invent a second refusal.
    guard_facts = facts + ([Fact(refusal, {})] if refusal else [])
    placeholders = PLACEHOLDER_PATTERN.findall(text)
    if len(placeholders) != len(set(placeholders)):
        return "duplicate placeholders in spoken prose"
    reason = verify_phrasing(text, guard_facts)
    if reason is not None:
        return reason
    if refusal is not None and refusal not in text:
        return "typed refusal was not preserved verbatim"
    if _INTERNAL_IDENTIFIER.search(text):
        return "internal identifier leaked into spoken prose"
    if _unsupported_spelled_number(text, guard_facts):
        return "unsupported spelled-out number in spoken prose"
    return None


def _retry_prompt(prompt: str, reason: str) -> str:
    return f"{prompt}\n\nThe previous draft failed the evidence guard ({reason}). Rewrite the complete answer and satisfy every rule."


def _number_words(text: str) -> set[str]:
    """Return normalized number-word tokens; hyphenated words are treated as separate number words."""
    return {token.lower() for token in re.findall(r"[A-Za-z]+", text) if token.lower() in _CARDINAL_WORDS | _ORDINAL_WORDS}


def _numeric_tokens(text: str) -> set[str]:
    tokens = {number.replace(",", "") for number in NUMERAL_PATTERN.findall(text)}
    tokens.update(f"cardinal:{_CARDINAL_VALUES[word]}" for word in _number_words(text) if word in _CARDINAL_VALUES)
    tokens.update(f"ordinal:{_ORDINAL_VALUES[word]}" for word in _number_words(text) if word in _ORDINAL_VALUES)
    return tokens


def _unsupported_spelled_number(text: str, facts: list[Fact]) -> bool:
    source = " ".join(fact.statement for fact in facts)
    permitted = _numeric_tokens(source)
    spoken_words = _number_words(text)
    spoken = {
        f"cardinal:{_CARDINAL_VALUES[word]}" if word in _CARDINAL_VALUES else f"ordinal:{_ORDINAL_VALUES[word]}"
        for word in spoken_words
    }
    return bool(spoken - permitted)


def _draft_reason(text: str, *, allow_numbers_from: list[Fact] | None = None, progress: bool = False) -> str | None:
    if PLACEHOLDER_PATTERN.search(text):
        return "unresolved placeholder in spoken prose"
    if NUMERAL_PATTERN.search(text):
        return "progress narration introduced a numeral" if progress else "unsupported numeral in spoken prose"
    if _INTERNAL_IDENTIFIER.search(text):
        return "internal identifier leaked into spoken prose"
    if _unsupported_spelled_number(text, allow_numbers_from or []):
        return "unsupported spelled-out number in spoken prose"
    return None


async def author_grounded_speech(
    request: SpeechRequest | str | dict[str, Any], claims: list[dict[str, Any]], model: Any = None
) -> AuthoredSpeech:
    """Ask the LLM for a claim-grounded result, retry once, then raise on invalid prose."""
    context = _request(request)
    valid_claims = [claim for claim in claims if claim.get("id")]
    claim_ids = tuple(str(claim["id"]) for claim in valid_claims)
    refusal = context.refusal or next((str(claim["text"]) for claim in claims if claim.get("kind") == "refusal"), None)
    if not claim_ids and refusal is None:
        raise SpeechGenerationError(
            "Grounded speech requires validated claim ids or a typed refusal.",
            details={"upstream": "evidence", "reason": "missing claim binding"},
        )
    facts = facts_from_claims(valid_claims)
    facts_text = "\n".join(f"{index}. {fact.statement}" for index, fact in enumerate(facts, 1)) or "(typed refusal only)"
    refusal_rule = f"Preserve this refusal exactly in the spoken answer: {refusal}" if refusal else ""
    prompt = VOICE_GROUNDED_PROMPT.format(question=context.question, facts=facts_text, refusal_rule=refusal_rule)
    model = await _model_or_raise(model)
    draft, version = await _invoke(model, prompt)
    reason = _grounding_reason(draft, facts, refusal)
    if reason is not None:
        draft, version = await _invoke(model, _retry_prompt(prompt, reason))
        reason = _grounding_reason(draft, facts, refusal)
    if reason is not None:
        raise SpeechGenerationError(
            f"The language model produced speech that failed the evidence guard: {reason}.",
            details={"upstream": "llm", "reason": reason},
        )
    kind = SpeechKind.REFUSAL if refusal else SpeechKind.GROUNDED
    return AuthoredSpeech(
        text=fill_placeholders(draft, facts),
        claim_ids=claim_ids,
        kind=kind,
        interruptible=kind is not SpeechKind.REFUSAL,
        supersedes_utterance_id=context.supersedes_utterance_id,
        model_version=version,
    )


def _trace_fact(trace_step: Any) -> str:
    if hasattr(trace_step, "model_dump"):
        value = trace_step.model_dump(by_alias=True, mode="json")
    elif isinstance(trace_step, dict):
        value = trace_step
    else:
        value = {name: getattr(trace_step, name) for name in ("id", "stage_code", "detail", "state") if hasattr(trace_step, name)}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


async def author_progress_speech(trace_step: Any, model: Any = None) -> AuthoredSpeech | None:
    """Author a progress update from one trace fact; an empty trace has nothing honest to say."""
    trace_text = _trace_fact(trace_step)
    if trace_text in {"{}", "null"}:
        return None
    prompt = VOICE_PROGRESS_PROMPT.format(trace_fact=trace_text)
    model = await _model_or_raise(model)
    draft, version = await _invoke(model, prompt)
    reason = _draft_reason(draft, progress=True)
    if reason is not None:
        draft, version = await _invoke(model, _retry_prompt(prompt, reason))
        reason = _draft_reason(draft, progress=True)
    if reason is not None:
        raise SpeechGenerationError(
            f"The language model produced progress speech that failed the evidence guard: {reason}.",
            details={"upstream": "llm", "reason": reason},
        )
    return AuthoredSpeech(text=draft, claim_ids=(), kind=SpeechKind.PROGRESS, model_version=version)


async def author_provisional_speech(
    request: SpeechRequest | str | dict[str, Any], model: Any = None
) -> AuthoredSpeech:
    """Author a clearly labelled in-flight response with no claim binding or invented numerals."""
    context = _request(request)
    operator_context = " ".join(part for part in (context.question, context.context or "") if part).strip()
    if not operator_context:
        raise SpeechGenerationError(
            "Provisional speech requires operator context.",
            details={"upstream": "voice", "reason": "missing context"},
        )
    prompt = VOICE_PROVISIONAL_PROMPT.format(context=operator_context)
    model = await _model_or_raise(model)
    draft, version = await _invoke(model, prompt)

    def reason_for(value: str) -> str | None:
        return _draft_reason(value)

    reason = reason_for(draft)
    if reason is not None:
        draft, version = await _invoke(model, _retry_prompt(prompt, reason))
        reason = reason_for(draft)
    if reason is not None:
        raise SpeechGenerationError(
            f"The language model produced provisional speech that failed the evidence guard: {reason}.",
            details={"upstream": "llm", "reason": reason},
        )
    return AuthoredSpeech(
        text=draft,
        claim_ids=(),
        kind=SpeechKind.PROVISIONAL,
        provisional=True,
        supersedes_utterance_id=context.supersedes_utterance_id,
        model_version=version,
    )
