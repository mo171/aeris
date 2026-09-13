"""Resolves the words in a question to the land-cover classes the segmenter can draw, or says which words it could not.

what  : `resolve_landcover_classes(query) -> tuple[str, ...]` and `unresolved_landcover_words(query)`.
where : The runner and the agent's segmentation step, before the single-image graph starts; S15 reads the
        resolved names from the state.
how   : Whole-phrase matching against `LANDCOVER_SYNONYMS`, longest phrase first, the same discipline as
        the detector's `OBJECT_SYNONYMS` and the spectral `QUERY_TARGETS`: "water bodies" is matched
        before "water", and "field" does not match "fields of view". An empty result is not a refusal -
        "segment the land cover" names no class and gets every class - which is why the unresolved words
        are reported separately: "segment the runways" names something the model cannot draw, and the
        run should say so rather than answer with everything.
"""

import re

from app.constants.routing import UNDETECTABLE_OBJECTS
from app.constants.segmentation import LANDCOVER_SYNONYMS, LOVEDA_CLASS_NAMES
from app.services.query.entities import normalise_query

_PHRASES = sorted(LANDCOVER_SYNONYMS, key=len, reverse=True)
_PATTERNS = [(phrase, re.compile(rf"\b{re.escape(phrase)}\b")) for phrase in _PHRASES]
# Words that name a thing to segment but that the segmenter has no class for.
_UNDRAWABLE = tuple(word for word in UNDETECTABLE_OBJECTS if word not in LANDCOVER_SYNONYMS)


def resolve_landcover_classes(query: str) -> tuple[str, ...]:
    """The classes the question names, in order of mention, no repeats. Empty means every class."""
    text = normalise_query(query)
    found: list[tuple[int, str]] = []
    consumed = [False] * len(text)
    for phrase, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            if any(consumed[match.start() : match.end()]):
                continue
            for index in range(match.start(), match.end()):
                consumed[index] = True
            found.append((match.start(), LANDCOVER_SYNONYMS[phrase]))
    ordered: list[str] = []
    for _, name in sorted(found):
        if name not in ordered:
            ordered.append(name)
    return tuple(ordered)


def unresolved_landcover_words(query: str) -> tuple[str, ...]:
    """Things asked for that no land-cover class covers, as the operator wrote them."""
    text = normalise_query(query)
    for _, pattern in _PATTERNS:
        text = pattern.sub(" ", text)
    return tuple(word for word in _UNDRAWABLE if re.search(rf"\b{re.escape(word)}\b", text))


def class_id_of(name: str) -> int:
    return LOVEDA_CLASS_NAMES.index(name)
