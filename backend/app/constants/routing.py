"""What the router knows before it sees a question: the intent -> graph table, the object vocabulary, and the cues that decide a family.

what  : `INTENT_GRAPHS`, `OBJECT_SYNONYMS`, `OBJECT_LENGTH_METRES`, `MIN_OBJECT_PIXELS`, the region /
        modality / temporal vocabularies, the classifier's encoder record and its kNN settings.
where : `services/query/` (classification and extraction) and `agents/router.py` (the table). Tests pin
        every table here so a routing change is a visible diff, not a behaviour drift.
how   : **Routing is a table** (PDF p.24): the classifier chooses an *intent* and the table chooses the
        *graph*. `None` is an intent whose graph is not built yet, with the phase that builds it, so the
        router refuses by name rather than falling through to a graph that would answer the wrong question.

        **Counting is never asked of the VLM.** Measured in 1.7: RSVQA-LR count accuracy 0.22 -> 0.23 after
        fine-tuning. `DETECT` with a count goes to `dota-detector`, whose count is the number of boxes it
        kept, each with a score. The detector knows fifteen classes; `OBJECT_SYNONYMS` maps the words an
        operator uses to them, and an object outside the vocabulary is a stated refusal, not a guess.

        **A detector cannot see what a pixel cannot hold.** `OBJECT_LENGTH_METRES` is a typical length per
        class; an object needs roughly `MIN_OBJECT_PIXELS` along it to be found by a detector trained at
        DOTA's 0.1-1 m. Required GSD = length / pixels: a 4.5 m car needs <= 0.56 m pixels, so a 10 m
        Sentinel-2 scene is refused for cars *before* the detector runs and reports zero.
"""

import re
from enum import StrEnum
from typing import Final

from app.constants.fleet import WeightsSource
from app.constants.intents import Intent
from app.constants.licences import Licence
from app.constants.pipeline import GraphName


class Modality(StrEnum):
    OPTICAL = "optical"
    SAR = "sar"
    BOTH = "both"
    UNSPECIFIED = "unspecified"


class SpatialRegion(StrEnum):
    """Where in the picture the operator pointed, as a compass sector. Absent when they did not."""

    NORTH = "north"
    NORTH_EAST = "north-east"
    EAST = "east"
    SOUTH_EAST = "south-east"
    SOUTH = "south"
    SOUTH_WEST = "south-west"
    WEST = "west"
    NORTH_WEST = "north-west"
    CENTRE = "centre"


class TemporalScope(StrEnum):
    SINGLE = "single"
    # Two acquisitions compared: "between these two images", "before and after", "since 2020".
    PAIR = "pair"
    # Evidence from earlier in the same investigation, not from imagery.
    PRIOR = "prior"


# Intent -> the graph that answers it, or `None` and the phase that builds it. Every intent is listed so
# an unrouted one is a visible `None`, never a missing key.
INTENT_GRAPHS: Final[dict[Intent, GraphName | None]] = {
    Intent.INDEX_QUERY: GraphName.SINGLE_IMAGE,
    Intent.SCENE_VQA: GraphName.SINGLE_IMAGE,
    Intent.GROUND: GraphName.SINGLE_IMAGE,
    Intent.DETECT: GraphName.SINGLE_IMAGE,
    Intent.SEGMENT: GraphName.SINGLE_IMAGE,
    Intent.CHANGE_DETECT: GraphName.TEMPORAL,
    Intent.CHANGE_VQA: GraphName.TEMPORAL,
    Intent.CROSS_MODAL: None,
    Intent.EVIDENCE_RECALL: None,
}
UNBUILT_GRAPH_PHASE: Final[dict[Intent, str]] = {
    Intent.CROSS_MODAL: "1.11 cross-modal graph (two per-sensor runs joined by late fusion)",
    Intent.EVIDENCE_RECALL: "no graph: the agent answers it from the conversation's earlier results (1.9)",
}

# Which intents need two acquisitions, and which need both sensors.
PAIR_INTENTS: Final[frozenset[Intent]] = frozenset({Intent.CHANGE_DETECT, Intent.CHANGE_VQA, Intent.CROSS_MODAL})

# Operator's word -> DOTA class name (constants/detection.py). Plural and singular both listed because the
# extractor matches whole words, not stems - "planes" must not match "planetary".
OBJECT_SYNONYMS: Final[dict[str, str]] = {
    "plane": "plane", "planes": "plane", "aircraft": "plane", "airplane": "plane", "airplanes": "plane",
    "aeroplane": "plane", "aeroplanes": "plane", "jet": "plane", "jets": "plane",
    "ship": "ship", "ships": "ship", "boat": "ship", "boats": "ship", "vessel": "ship", "vessels": "ship",
    "container ship": "ship", "container ships": "ship",
    "storage tank": "storage tank", "storage tanks": "storage tank", "oil tank": "storage tank",
    "oil tanks": "storage tank", "fuel tank": "storage tank", "fuel tanks": "storage tank", "tank": "storage tank",
    "tanks": "storage tank", "silo": "storage tank", "silos": "storage tank",
    "baseball diamond": "baseball diamond", "baseball diamonds": "baseball diamond", "baseball field": "baseball diamond",
    "baseball fields": "baseball diamond",
    "tennis court": "tennis court", "tennis courts": "tennis court",
    "basketball court": "basketball court", "basketball courts": "basketball court",
    "ground track field": "ground track field", "ground track fields": "ground track field",
    "running track": "ground track field", "running tracks": "ground track field", "athletics track": "ground track field",
    "harbor": "harbor", "harbors": "harbor", "harbour": "harbor", "harbours": "harbor",
    "bridge": "bridge", "bridges": "bridge",
    "large vehicle": "large vehicle", "large vehicles": "large vehicle", "truck": "large vehicle", "trucks": "large vehicle",
    "lorry": "large vehicle", "lorries": "large vehicle", "bus": "large vehicle", "buses": "large vehicle",
    "small vehicle": "small vehicle", "small vehicles": "small vehicle", "car": "small vehicle", "cars": "small vehicle",
    "vehicle": "small vehicle", "vehicles": "small vehicle",
    "helicopter": "helicopter", "helicopters": "helicopter",
    "roundabout": "roundabout", "roundabouts": "roundabout",
    "soccer ball field": "soccer ball field", "soccer ball fields": "soccer ball field", "soccer field": "soccer ball field",
    "soccer fields": "soccer ball field", "football pitch": "soccer ball field", "football pitches": "soccer ball field",
    "football field": "soccer ball field", "football fields": "soccer ball field",
    "swimming pool": "swimming pool", "swimming pools": "swimming pool", "pool": "swimming pool", "pools": "swimming pool",
}

# Words that name a thing to find but that no detector in the fleet knows. Extracted so the refusal can
# say "buildings" rather than "the object", and so GROUND queries carry their phrase.
UNDETECTABLE_OBJECTS: Final[tuple[str, ...]] = (
    "building", "buildings", "house", "houses", "road", "roads", "runway", "runways", "airport", "airports",
    "stadium", "stadiums", "dam", "dams", "river", "rivers", "lake", "lakes", "field", "fields", "tree", "trees",
    "parking lot", "parking lots", "railway", "solar farm", "wind farm", "power plant", "refinery", "quarry", "mine",
    "port", "ports", "school", "hospital", "water tower", "tower", "towers", "structure", "structures", "settlement", "settlements",
)

# Typical length of one instance, metres. Engineering figures, not measurements: a car is 4-5 m, a truck
# 8-16, an airliner 30-70, a harbour hundreds. Used only for the resolution gate.
OBJECT_LENGTH_METRES: Final[dict[str, float]] = {
    "plane": 30.0, "ship": 40.0, "storage tank": 20.0, "baseball diamond": 80.0, "tennis court": 24.0,
    "basketball court": 28.0, "ground track field": 150.0, "harbor": 300.0, "bridge": 100.0,
    "large vehicle": 12.0, "small vehicle": 4.5, "helicopter": 15.0, "roundabout": 40.0,
    "soccer ball field": 100.0, "swimming pool": 15.0,
}
# Pixels an object must span along its length for a DOTA-trained detector to have a chance at it.
MIN_OBJECT_PIXELS: Final[int] = 8

# Compass phrases, longest first so "north-east" is not read as "north". Screen words map to the same
# sectors: the figures are drawn north-up.
SPATIAL_REGION_PHRASES: Final[dict[str, SpatialRegion]] = {
    "north-east": SpatialRegion.NORTH_EAST, "northeast": SpatialRegion.NORTH_EAST, "north east": SpatialRegion.NORTH_EAST,
    "top right": SpatialRegion.NORTH_EAST, "upper right": SpatialRegion.NORTH_EAST, "top-right": SpatialRegion.NORTH_EAST,
    "north-west": SpatialRegion.NORTH_WEST, "northwest": SpatialRegion.NORTH_WEST, "north west": SpatialRegion.NORTH_WEST,
    "top left": SpatialRegion.NORTH_WEST, "upper left": SpatialRegion.NORTH_WEST, "top-left": SpatialRegion.NORTH_WEST,
    "south-east": SpatialRegion.SOUTH_EAST, "southeast": SpatialRegion.SOUTH_EAST, "south east": SpatialRegion.SOUTH_EAST,
    "bottom right": SpatialRegion.SOUTH_EAST, "lower right": SpatialRegion.SOUTH_EAST, "bottom-right": SpatialRegion.SOUTH_EAST,
    "south-west": SpatialRegion.SOUTH_WEST, "southwest": SpatialRegion.SOUTH_WEST, "south west": SpatialRegion.SOUTH_WEST,
    "bottom left": SpatialRegion.SOUTH_WEST, "lower left": SpatialRegion.SOUTH_WEST, "bottom-left": SpatialRegion.SOUTH_WEST,
    "north": SpatialRegion.NORTH, "top": SpatialRegion.NORTH, "south": SpatialRegion.SOUTH, "bottom": SpatialRegion.SOUTH,
    "east": SpatialRegion.EAST, "right": SpatialRegion.EAST, "west": SpatialRegion.WEST, "left": SpatialRegion.WEST,
    "centre": SpatialRegion.CENTRE, "center": SpatialRegion.CENTRE, "middle": SpatialRegion.CENTRE,
}

# Text-speak an operator types, folded to the words the cues know. Whole words only: "r" in "r&d" stays.
QUERY_SPELLINGS: Final[dict[str, str]] = {"u": "you", "r": "are", "ur": "your", "pls": "please", "plz": "please", "pic": "picture", "whats": "what is", "dint": "did not"}

SAR_WORDS: Final[tuple[str, ...]] = ("sar", "radar", "sentinel-1", "sentinel 1", "backscatter", "vv", "vh")
OPTICAL_WORDS: Final[tuple[str, ...]] = ("optical", "sentinel-2", "sentinel 2", "true-colour", "true colour", "true-color", "rgb", "ndvi", "ndwi")

# Cues, as regular expressions over the lower-cased question. Each is a *family* the classifier restricts
# itself to; the kNN chooses within it. Order is precedence: an evidence question that mentions ships is
# still an evidence question.
COUNT_CUE: Final[re.Pattern[str]] = re.compile(r"\b(how many|count|number of|total number|enumerate)\b")
PAIR_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(two images|both images|two scenes|two dates|between the (two|images|dates)|between these|before and after|"
    r"before/after|(first|second|later|earlier) (image|date|scene)|since the|t0|t1|since \d{4}|between \d{4} and \d{4}|"
    r"chang(e|ed|es|ing)|differen(ce|ces|t)|appear(ed|s)?|disappear(ed|s)?|increas(e|ed|es)|decreas(e|ed|es)|"
    r"grow(th|n|s)?|grew|shrank|shrunk|shrink|expand(ed|s)?|retreat(ed|s)?|reced(e|ed)|recover(ed|s)?|erod(e|ed)|"
    r"declin(e|ed)|convert(ed)?|demolished|destroyed|encroach(ed|ment)?|moved|widen(ed)?|lost|gained|cleared|dried( up)?|"
    r"newly|than before|now than|bigger|smaller|wider|narrower|larger|greener|busier|higher|lower|fewer|taller|denser|"
    r"new (buildings|roads|construction|development|structures|settlements|farmland|industrial))\b"
)
EVIDENCE_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(your (answer|claim|last|previous|earlier|conclusion|findings?)|evidence|provenance|audit trail|trace of|"
    r"why did you|why (is|was) the confidence|why the confidence|where did that (number|figure|value) come from|where did you|"
    r"what did you (find|see|say|measure)|which (model|index|bands?|files?|detections?) (did|were|produced)|"
    r"(previous|earlier|last) (answer|result|run|analysis|query|step|findings?)|"
    r"you (found|detected|reported|flagged|counted|used|gave|said|saw|based|arrive)|made you say|responsible for|supports? your|"
    r"behind (your|that|the) (answer|claim|area|number)|from (your|the) (previous|last|earlier)|"
    r"show (the|me the|me your) (evidence|mask you|map behind|region you|regions from|source|claim's)|"
    r"(retrieve|recall|bring back|re-display|display .* again|go back to))\b"
)
CROSS_MODAL_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(both sensors|two sensors|sensors|modalities|multi-?modal|cross-?modal|multi-?sensor|fus(e|ion|ed))\b"
)
# Segmentation asked for as an action, and the nouns of it that only count when a map or a share is wanted.
SEGMENT_VERB_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(segment(ation|ed|s)?|outline|delineate|trace the|classify (the|each|land)|partition|semantic|mask (of|out|the)|"
    r"extract (the|building|footprint)|class-wise)\b"
)
SEGMENT_NOUN_CUE: Final[re.Pattern[str]] = re.compile(r"\b(land[- ]?cover|land[- ]?use|footprints?|classification|shoreline|boundar(y|ies))\b")
GROUND_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(where(?: is| ?'s| are| exactly| can i find)|locate|point (out|to)|pinpoint|draw a box|box the|coordinates of|"
    r"identify where|show (me )?where|show me the|which building|which part of the image|mark the (position|intersection)|"
    r"find the (largest|biggest|smallest|tallest|nearest|closest|main|\w+est))\b"
)
DETECT_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(detect|detection|find (all|every)|identify all|list all|all the objects|every (vehicle|boat|ship|plane|"
    r"storage|car|truck|pool|tank))\b"
)
# A question that opens like this asks what the picture shows - presence, kind, description - which is
# the VLM's question (SCENE_VQA), unless a stronger cue above has already claimed it.
PERCEPTION_OPENER: Final[re.Pattern[str]] = re.compile(
    r"^(is|are|does|do|any|can you|could you|would you|why|whether|if|what (kind|type|does|can|are)|describe|caption|"
    r"(check|say|see|find out) (whether|if)|tell me about|"
    r"summari[sz]e|explain|give me a caption)\b"
)

# The intent families a cue narrows to. A family of one is a decision; a family of two is a kNN choice.
CHANGE_FAMILY: Final[frozenset[Intent]] = frozenset({Intent.CHANGE_DETECT, Intent.CHANGE_VQA})

# "tell me whether ...", "say if ...": the verb of asking is transparent to the openers below.
ASKING_LEAD: Final[re.Pattern[str]] = re.compile(r"^(?:tell me|say|let me know|i want to know|find out|check)\s+(?=(?:whether|if|how|what|which|is|are|has|have|did|does|by)\b)")
# A question that opens like this asks for a *fact* about change (CHANGE_VQA) rather than a map of it.
CHANGE_QUESTION_OPENERS: Final[re.Pattern[str]] = re.compile(
    r"^(has|have|had|is|are|was|were|did|does|do|by how much|how much|how has|what is the percentage|which image)\b"
)

# The sentence encoder behind the kNN. BAAI/bge-small-en-v1.5: 33M parameters, 384-d, MIT, ~10 ms per
# query on a CPU. Not a fleet member: it holds no GPU memory and states no claim, so `ModelManager`'s
# budget and the frontend's fleet vocabulary do not apply to it. Pinned by commit like every other weight.
INTENT_ENCODER: Final[WeightsSource] = WeightsSource(
    repository="BAAI/bge-small-en-v1.5", filename=None, revision="5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
)
INTENT_ENCODER_LICENCE: Final[Licence] = Licence.MIT
INTENT_ENCODER_VERSION: Final[str] = "bge-small-en-v1.5"
INTENT_ENCODER_MAX_TOKENS: Final[int] = 64

# kNN over the labelled bank: five neighbours, votes weighted by cosine similarity. Below the margin
# between the top two intents the decision is reported as uncertain (1.9's agent may ask or arbitrate).
INTENT_NEIGHBOURS: Final[int] = 5
INTENT_UNCERTAIN_MARGIN: Final[float] = 0.15

# The labelled query bank is package data beside the classifier; the held-out half is scored, never
# learned from. The split is by hash of the text so it is the same on every machine.
INTENT_BANK_FILENAME: Final[str] = "intent_bank.jsonl"
INTENT_HOLDOUT_FILENAME: Final[str] = "intent_holdout.jsonl"
# Written after the cues were tuned against the held-out half, in an operator's register ("how many ships
# r there"); scored, never tuned against. The number that stands for what a judge would see.
INTENT_FRESH_FILENAME: Final[str] = "intent_fresh.jsonl"
# Compound, voice-register requests with the ordered intents a plan must contain. The first was developed
# against; the second written afterwards and scored once.
INTENT_COMPOUND_FILENAME: Final[str] = "intent_compound.jsonl"
INTENT_COMPOUND_FRESH_FILENAME: Final[str] = "intent_compound_fresh.jsonl"
