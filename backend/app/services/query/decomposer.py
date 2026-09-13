"""Splits one spoken request into the clauses it contains, each a question the router can answer on its own.

what  : `strip_filler()`, `split_clauses()`, `Clause`.
where : `agents/router.py`'s `route_plan()` runs it before classifying each clause; the CLI prints the
        clauses beside the steps so a wrong split is seen, not inferred.
how   : A voice request is long and compound: "hey, look at this and tell me how many ships there are,
        and also whether the port looks busy". Measured before this existed: the single-intent router got
        4 of 4 single asks and 0 of 11 compound ones right - it answered the loudest clause. So:

        1. **Filler off the front and back** - "hey aeris", "can you please", "so basically what i need
           is", "for me" - by a table, never by a model. Filler is not content and must not reach a cue.
        2. **Clauses at sentence ends and at connectives** (", and then", " then ", " and also ", " as
           well as ", "; ") and at " and " only when what follows opens a clause - a verb, a wh-word, an
           auxiliary - so "ships and boats" stays one phrase and "count the ships and tell me" is two.
        3. **Conditional leads dropped** ("if yes,", "if so,"): the clause is asked regardless, and the
           answer to the earlier one is what makes it moot, which is the agent's call (1.9), not the
           router's.

        A clause that is only a pronoun and a verb ("count them") is kept: the router inherits the objects
        from the clause before. Nothing here decides an intent.
"""

import re
from dataclasses import dataclass

from app.constants.spectral import INDEX_NAMES
from app.services.query.entities import normalise_query

# Leading and trailing filler, as regular expressions anchored to the ends. Applied repeatedly.
_LEADING_FILLER = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|alright|right|so|um|uh|well|basically|now|please|aeris),?\s+)+"
    r"|^(?:can|could|would|will)\s+you\s+(?:please\s+)?"
    r"|^(?:i\s+(?:want|need|would like|'d like)\s+(?:you\s+to\s+)?)"
    r"|^(?:what\s+i\s+(?:need|want)\s+is\s+)"
    r"|^(?:please\s+)"
    r"|^(?:(?:take|have)\s+a\s+look\s+at\s+(?:this|the)\s+(?:satellite\s+)?(?:image|picture|scene|tile)\s+and\s+)"
    r"|^(?:look\s+at\s+(?:this|the|these)\s+(?:two\s+)?(?:satellite\s+)?(?:images?|pictures?|scenes?|tiles?)(?:\s+from\s+\d{4}\s+and\s+\d{4})?\s+and\s+)"
    r"|^(?:first(?:ly)?,?\s+)"
    r"|^(?:(?:so\s+)?i\s+have\s+(?:this|an?|these)\s+(?:two\s+)?(?:satellite\s+)?(?:images?|pictures?|scenes?|tiles?)(?:\s+of\s+an?\s+\w+)?\s*,?\s*(?:and\s+)?)"
)
_TRAILING_FILLER = re.compile(r"(?:\s*,?\s*(?:please|for me|right now|now|thanks|thank you|if you can|if possible|nothing fancy|just what you see))+[\s.?!]*$")
_CONDITIONAL_LEAD = re.compile(r"^(?:if\s+(?:yes|so|not|it\s+is|they\s+are|there\s+are|there\s+is)\s*,?(?:\s+|$))")
# A clause that only directs attention ("take a look at this image") asks nothing; dropped whole.
_FILLER_CLAUSE = re.compile(r"^(?:(?:take|have)\s+a\s+)?look\s+at\s+(?:this|the|these)\s+(?:two\s+)?(?:satellite\s+)?(?:images?|pictures?|scenes?|tiles?)(?:\s+from\s+\d{4}\s+and\s+\d{4})?$")

# What opens a clause after " and ": a verb of asking, a wh-word, an auxiliary, or "whether/if".
_CLAUSE_OPENER = (
    r"(?:tell|show|give|count|map|find|locate|detect|segment|compare|mark|check|explain|describe|highlight|"
    r"identify|list|outline|measure|calculate|compute|draw|point|estimate|say|let|see|where|what|which|how|"
    r"whether|if|is|are|was|were|has|have|did|does|do|also|then)\b"
)
_INDEX_NAME = "|".join(re.escape(name) for name in INDEX_NAMES)
_SPLIT = re.compile(
    rf"(?:[.?!;]\s+)|(?:\s*,?\s+(?:and\s+)?(?:then|after\s+that|afterwards|next(?!\s+to\b)|finally|lastly|first\s+of\s+all)\s+)|(?:\s*,?\s+and\s+also\s+)|(?:\s*,?\s+as\s+well\s+as\s+)|"
    rf"(?:\s+and\s+(?=(?:the\s+)?(?:{_INDEX_NAME})\b))|"
    rf"(?:\s*,?\s+and\s+(?={_CLAUSE_OPENER}))|(?:\s*,\s+(?={_CLAUSE_OPENER}))|(?:\s+also\s+(?={_CLAUSE_OPENER}))|"
    r"(?:\s*,\s+(?:and\s+)?(?=(?:a|an|the)\s))"
)
_MIN_CLAUSE_WORDS = 2
# A verb of asking left alone by a split ("tell me" before "first of all"): nothing to route.
_BARE_ASK = re.compile(r"^(?:tell me|show me|give me|let me know|say)$")
_PRONOUN = re.compile(r"\b(them|those|they|their|theirs|of them|each of|its|it|one|ones|there are|are there)\b")
_OBJECT_PRONOUN = re.compile(r"\b(them|those|they|their|theirs|of them|each of|one|ones|there are|are there)\b")
# Words that point at an earlier request rather than at the clause before: "what did you find earlier",
# "the number you gave". Without one of these, a clause that asks about evidence or a property is about
# the step it follows in this same request, and enriches it instead of recalling.
_PAST_REFERENCE = re.compile(
    r"\b(earlier|previous(ly)?|last time|before|the last (answer|run|analysis|query|step|result)|your (last|previous|earlier) \w+|"
    r"you (found|said|reported|detected|measured|gave|counted|flagged|used|told|showed|mentioned)|the number you|"
    r"(that|the) (earlier|previous) (number|answer|result|figure))\b"
)


@dataclass(frozen=True, slots=True)
class Clause:
    text: str
    # `True` when the clause refers back by pronoun ("count them", "how many of them are there").
    pronominal: bool
    # `True` when that pronoun is a plural or object one ("them", "those", "one") rather than "it": "count
    # them" is about the things just found; "does it look like a school" is about the picture.
    object_pronoun: bool = False
    # `True` when the clause points at an earlier request ("what did you find earlier"). Without it, an
    # evidence question or a property ask is about the step before it in this request.
    past_reference: bool = False


def strip_filler(query: str) -> str:
    text = normalise_query(query)
    previous = None
    while previous != text:
        previous = text
        text = _LEADING_FILLER.sub("", text).strip()
        text = _TRAILING_FILLER.sub("", text).strip()
    return text


def split_clauses(query: str) -> list[Clause]:
    """The request as clauses, in order, filler removed. One clause when nothing splits."""
    text = strip_filler(query)
    clauses: list[Clause] = []
    for piece in _SPLIT.split(text):
        piece = _CONDITIONAL_LEAD.sub("", strip_filler(piece)).strip(" ,.?!;")
        if len(piece.split()) < _MIN_CLAUSE_WORDS or _FILLER_CLAUSE.match(piece) or _BARE_ASK.match(piece):
            continue
        pronominal = _PRONOUN.search(piece) is not None
        clauses.append(Clause(piece, pronominal, _OBJECT_PRONOUN.search(piece) is not None, _PAST_REFERENCE.search(piece) is not None))
    return clauses or [Clause(text or normalise_query(query), False)]
