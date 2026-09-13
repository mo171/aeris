"""Pulls the typed pieces out of a question: what object, which part of the picture, which dates, which sensor, what kind of answer.

what  : `QueryEntities` and `extract_entities()`.
where : `agents/router.py` runs it beside the classifier; the CLI prints it; 1.9's planner reads it.
how   : Vocabulary matching on whole words, longest phrase first. Nothing here is learned: an entity the
        extractor did not find is absent, never guessed, and every vocabulary is a table in
        `constants/routing.py` a test can pin. Objects resolve to the detector's class names so the
        router can ask "does the fleet count this?" as a set lookup; a word for a thing no detector knows
        ("buildings") is kept as an `unknown_object` so the refusal can name it.

        The "wants" flags say what shape of answer was asked for. They are cues, not the intent: "how many
        hectares of water" wants a count *and* an area and is an INDEX_QUERY; the classifier decides the
        intent and the router uses the flags to decide the tool.
"""

import re
from dataclasses import dataclass, field

from app.constants.routing import (
    COUNT_CUE,
    EVIDENCE_CUE,
    MIN_OBJECT_PIXELS,
    OBJECT_LENGTH_METRES,
    OBJECT_SYNONYMS,
    OPTICAL_WORDS,
    PAIR_CUE,
    QUERY_SPELLINGS,
    SAR_WORDS,
    SPATIAL_REGION_PHRASES,
    UNDETECTABLE_OBJECTS,
    Modality,
    SpatialRegion,
    TemporalScope,
)
from app.constants.spectral import INDEX_NAMES, QUERY_TARGETS

# "area" is a measurement ask only as "the/its/their/total area" or "area of/in/covered"; "an industrial
# area" is a place. Measured: the bare word turned "tell me if this is an industrial area" into an area ask.
_AREA_CUE = re.compile(
    r"\b(?:(?:the|its|their|total|what|whats|what's|which)\s+(?:\w+[- ]){0,2}area|area\s+(?:of|in|covered|is|does|do|under)|areas?\s+in\s+hectares|"
    r"hectares?|ha|square (?:km|kilomet(?:re|er)s?|met(?:re|er)s?)|sq\.? ?km|extent|how much|fraction|proportion|percentage|share|coverage|cover)\b"
)
_LOCATION_CUE = re.compile(r"\b(where|locate|location|point (out|to)|pinpoint|highlight|mark|box|coordinates|which part)\b")
_MAP_CUE = re.compile(r"\b(map|mask|show|draw|display|overlay|outline|segment|delineate|visuali[sz]e)\b")
_LOCATIVE = re.compile(r"\b(in|near|on|at|by|along|around|next to|inside|within|across|over|beside|close to)\b")
_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2}|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.? \d{4}|(?:19|20)\d{2})\b")


@dataclass(frozen=True, slots=True)
class QueryEntities:
    # Detector class names to act on, in order of mention, no repeats; and the ones named only as a place
    # ("in the harbour"), which the resolution gate still checks.
    objects: tuple[str, ...] = ()
    context_objects: tuple[str, ...] = ()
    # Things asked for that no detector in the fleet knows, as the operator wrote them.
    unknown_objects: tuple[str, ...] = ()
    # The `QUERY_TARGETS` phrase or index name a spectral engine can answer, if any; and an index named
    # outright ("the NDWI map"), which settles the intent by itself.
    spectral_phrase: str | None = None
    index_named: str | None = None
    region: SpatialRegion | None = None
    temporal: TemporalScope = TemporalScope.SINGLE
    dates: tuple[str, ...] = ()
    modality: Modality = Modality.UNSPECIFIED
    wants_count: bool = False
    wants_area: bool = False
    wants_location: bool = False
    wants_map: bool = False
    # Every vocabulary phrase matched, for the trace. Longest first, as matched.
    matched: tuple[str, ...] = field(default=())

    @property
    def image_count(self) -> int:
        return 2 if self.temporal == TemporalScope.PAIR or self.modality == Modality.BOTH else 1


def normalise_query(query: str) -> str:
    """Lower-cased, text-speak folded, whitespace collapsed. What every cue and the encoder see."""
    text = query.lower().strip()
    for short, long in QUERY_SPELLINGS.items():
        text = re.sub(rf"(?<!\w){re.escape(short)}(?!\w)", long, text)
    return re.sub(r"\s+", " ", text)


def extract_entities(query: str) -> QueryEntities:
    text = normalise_query(query)
    matched: list[str] = []

    # Objects in order of mention; the ones after a locative preposition are where to look, not what to
    # count ("ships in the harbour" counts ships).
    mentions: list[tuple[int, str]] = []
    consumed = text
    for phrase in sorted(OBJECT_SYNONYMS, key=len, reverse=True):
        match = re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", consumed)
        if match:
            matched.append(phrase)
            consumed = consumed[: match.start()] + " " * len(phrase) + consumed[match.end():]
            if OBJECT_SYNONYMS[phrase] not in {name for _, name in mentions}:
                mentions.append((match.start(), OBJECT_SYNONYMS[phrase]))
    mentions.sort()
    objects: list[str] = [name for _, name in mentions]
    context: list[str] = []
    if mentions:
        locative = _LOCATIVE.search(text, mentions[0][0])
        if locative:
            objects = [name for start, name in mentions if start < locative.start()]
            context = [name for start, name in mentions if start >= locative.start()]
    unknown: list[str] = []
    for word in sorted(UNDETECTABLE_OBJECTS, key=len, reverse=True):
        match = re.search(rf"(?<!\w){re.escape(word)}(?!\w)", consumed)
        if match:
            unknown.append(word)
            consumed = consumed[: match.start()] + " " * len(word) + consumed[match.end():]

    index_named = next((name for name in INDEX_NAMES if _whole(text, name)), None)
    spectral = next((phrase for phrase in sorted(QUERY_TARGETS, key=len, reverse=True) if _whole(text, phrase)), None) or index_named
    matched.extend(name for name in (spectral, index_named) if name and name not in matched)

    region = next((sector for phrase, sector in sorted(SPATIAL_REGION_PHRASES.items(), key=lambda item: -len(item[0])) if _whole(text, phrase)), None)

    sar = any(_whole(text, word) for word in SAR_WORDS)
    optical = any(_whole(text, word) for word in OPTICAL_WORDS)
    modality = Modality.BOTH if sar and optical else Modality.SAR if sar else Modality.OPTICAL if optical else Modality.UNSPECIFIED

    dates = tuple(match.group(0) for match in _DATE.finditer(text))
    if EVIDENCE_CUE.search(text):
        temporal = TemporalScope.PRIOR
    elif PAIR_CUE.search(text) or len(dates) >= 2:
        temporal = TemporalScope.PAIR
    else:
        temporal = TemporalScope.SINGLE

    return QueryEntities(
        objects=tuple(objects), context_objects=tuple(context), unknown_objects=tuple(unknown), spectral_phrase=spectral, index_named=index_named, region=region, temporal=temporal,
        dates=dates, modality=modality, wants_count=COUNT_CUE.search(text) is not None,
        wants_area=_AREA_CUE.search(text) is not None, wants_location=_LOCATION_CUE.search(text) is not None,
        wants_map=_MAP_CUE.search(text) is not None, matched=tuple(matched),
    )


def required_ground_sample_distance(class_name: str) -> float:
    """The coarsest pixel (metres) at which one instance of the class still spans `MIN_OBJECT_PIXELS`."""
    return OBJECT_LENGTH_METRES[class_name] / MIN_OBJECT_PIXELS


def _whole(text: str, phrase: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None
