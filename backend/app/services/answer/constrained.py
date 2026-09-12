"""Turns claim objects into an answer in plain English whose every number is a claim's number - the VLM phrases, it never measures.

what  : `phrase_claims()` - claims and a question in, `ConstrainedAnswer` out - and the pure pieces under
        it: `facts_from_claims()`, `verify_phrasing()`, `fill_placeholders()`.
where : S16 (`pipeline/nodes/answer_generation.py`) when `settings.answer_generator` is `vlm`; the
        template composition stays as the fallback and as the answer on a machine with no model.
how   : Each claim's metric values are replaced in its own sentence by placeholders `{m1}`, `{m2}`...;
        the model is shown the facts *with the holes* and asked to write the answer copying the holes.
        Its text is then checked: every placeholder it used must exist, and no numeral may appear that is
        neither a placeholder nor already written in a fact (an index range, a scene id) - a `4` it typed
        on its own is a number nobody computed, and the whole phrasing is rejected for the template rather
        than edited, because an edited hallucination is still one. Only after the check are the holes
        filled with the values formatted exactly as the claim formatted them. (Measured: the first real
        run was rejected for copying "NDVI 0.20-0.40" from the fact - the rule had to learn the difference
        between repeating a specialist's number and inventing one.)

        Every placeholder must be spoken: the first adapted model answered the phrasing prompt with "{m1}"
        alone - one number, nothing else - and a guard that only forbids *invented* numbers let it through.
        Phrasing runs on the base weights (`use_adapter=False`); the adapter's job is the picture.

        The check is the design (PDF §20, `product-truth.md` §1.3): "the VLM cannot emit a figure that no
        specialist produced" is not a prompt instruction, it is a regular expression that runs on the
        output. The gate test seeds a claim with a known number and asserts the answer carries exactly it.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from app.constants.model_ids import ModelId
from app.constants.vlm import NUMERAL_PATTERN, PLACEHOLDER_PATTERN, VLM_MAX_NEW_TOKENS
from app.lib.exceptions import AerisError
from app.models.manager import ModelManager
from app.services.prompts.vlm import CONSTRAINED_ANSWER_TEMPLATE

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Fact:
    """One claim as the model sees it: its sentence with holes, and what goes in them."""

    statement: str
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class ConstrainedAnswer:
    text: str
    # `vlm` when the model's phrasing passed the check; `template` when it did not, or was not tried.
    source: str
    model_version: str | None
    rejected_phrasing: str | None = None


class Phraser(Protocol):
    """What the generator needs from a model: text in, text out. The VLM adapter satisfies it text-only."""

    version: str

    def generate(self, images: list[Any], prompt: str, *, max_new_tokens: int = ...) -> Any: ...


def format_metric(value: float, precision: int, unit: str) -> str:
    """The claim builder's own formatting, so the fill is byte-identical to the claim's text."""
    number = f"{value:,.{precision}f}"
    return f"{number}{unit}" if unit == "%" else (f"{number} {unit}" if unit else number)


def facts_from_claims(claims: list[dict[str, Any]]) -> list[Fact]:
    """Claims (wire form) to facts with placeholders, numbered across the whole answer."""
    facts: list[Fact] = []
    counter = 0
    for claim in sorted(claims, key=lambda c: not c.get("isPrimary", False)):
        statement = claim["text"]
        values: dict[str, str] = {}
        for metric in claim.get("metrics", []):
            counter += 1
            name = f"m{counter}"
            formatted = format_metric(metric["value"], metric["precision"], metric["unit"])
            bare = f"{metric['value']:,.{metric['precision']}f}"
            # The hole is filled with exactly what it replaced: the bare number where the sentence already
            # carries its own unit word ("covers 2,471.0 hectares"), the number with its unit otherwise.
            if formatted in statement:
                statement = statement.replace(formatted, f"{{{name}}}", 1)
                values[name] = formatted
            elif bare in statement:
                statement = statement.replace(bare, f"{{{name}}}", 1)
                values[name] = bare
            else:
                statement += f" ({metric['label']}: {{{name}}})"
                values[name] = formatted
        facts.append(Fact(statement, values))
    return facts


def verify_phrasing(text: str, facts: list[Fact]) -> str | None:
    """`None` when the text is admissible; otherwise the reason it is not."""
    known = {name for fact in facts for name in fact.values}
    used = {f"m{index}" for index in PLACEHOLDER_PATTERN.findall(text)}
    if unknown := used - known:
        return f"placeholders that no fact defines: {sorted(unknown)}"
    # Numerals the facts themselves carry outside their metrics - an index range like "0.20-0.40", a scene
    # id's digits - are the specialists' too, and the model may repeat them. Anything else is invented.
    permitted = {numeral for fact in facts for numeral in NUMERAL_PATTERN.findall(PLACEHOLDER_PATTERN.sub("", fact.statement))}
    stripped = PLACEHOLDER_PATTERN.sub("", text)
    if invented := [numeral for numeral in NUMERAL_PATTERN.findall(stripped) if numeral not in permitted]:
        return f"numerals the model wrote itself: {invented}"
    if missing := known - used:
        return f"placeholders left unspoken: {sorted(missing)} - every number the specialists computed is said, or the template says it"
    return None


def admissible_reading(reading: str, claims: list[dict[str, Any]]) -> bool:
    """A free-form reading may be spoken only if every numeral in it already appears in a claim's text.
    "Three fields" is fine; "3 fields" is a count nobody computed and keeps the reading out of the answer
    (it stays in the provenance record)."""
    permitted = {numeral for claim in claims for numeral in NUMERAL_PATTERN.findall(claim["text"])}
    return all(numeral in permitted for numeral in NUMERAL_PATTERN.findall(reading))


def fill_placeholders(text: str, facts: list[Fact]) -> str:
    values = {name: value for fact in facts for name, value in fact.values.items()}
    return PLACEHOLDER_PATTERN.sub(lambda match: values[f"m{match.group(1)}"], text)


def template_answer(claims: list[dict[str, Any]]) -> str:
    """The claims' own sentences, primary first. What S16 said before 1.7 and still says without a model."""
    primary = [claim["text"] for claim in claims if claim.get("isPrimary")]
    supporting = [claim["text"] for claim in claims if not claim.get("isPrimary")]
    return " ".join(primary + supporting)


async def phrase_claims(
    question: str, claims: list[dict[str, Any]], *, manager: ModelManager | None
) -> ConstrainedAnswer:
    """Ask the VLM to phrase the claims; keep its words only if they carry no number of their own."""
    fallback = ConstrainedAnswer(template_answer(claims), "template", None)
    if manager is None or not claims:
        return fallback
    facts = facts_from_claims(claims)
    prompt = CONSTRAINED_ANSWER_TEMPLATE.format(
        facts="\n".join(f"{index}. {fact.statement}" for index, fact in enumerate(facts, start=1)), question=question
    )
    try:
        async with manager.lease(ModelId.REMOTE_SENSING_VLM) as model:
            generation = await asyncio.to_thread(model.generate, [], prompt, max_new_tokens=VLM_MAX_NEW_TOKENS, use_adapter=False)
    except AerisError as error:
        logger.info("vlm unavailable for phrasing; template answer used", extra={"reason": str(error)})
        return fallback
    version = getattr(model, "version", None)
    reason = verify_phrasing(generation.text, facts)
    if reason is not None:
        logger.warning("vlm phrasing rejected", extra={"reason": reason, "text": generation.text})
        return ConstrainedAnswer(fallback.text, "template", version, rejected_phrasing=generation.text)
    return ConstrainedAnswer(fill_placeholders(generation.text, facts), "vlm", version)
