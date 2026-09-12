"""Decides which of the nine intents a question is: cues narrow the family, neighbours in a labelled bank choose within it.

what  : `IntentDecision`, `classify_intent()`, `rule_family()`.
where : `agents/router.py`. The evaluation harness (`services/evaluation/intent.py`) scores it on the
        held-out half of the bank and on each half of the cascade alone.
how   : A cascade, in order of precedence, each step a table in `constants/routing.py`:

        1. **Cues that settle a family.** "your answer" is EVIDENCE_RECALL whatever else the sentence says;
           both sensors named is CROSS_MODAL; a change cue is the CHANGE family; a segmentation word is
           SEGMENT; "how many <object>" or "detect" is DETECT; an index name, or a spectral target asked
           for as an area, map or location, is INDEX_QUERY; a locating verb is GROUND. These are the
           high-precision patterns, and each names itself in the decision so a wrong one is a visible rule.
        2. **Within the CHANGE family**, a question opener ("has", "did", "how much") asks for a fact
           (CHANGE_VQA); a map, mask or "where" asks for a map (CHANGE_DETECT).
        3. **Otherwise the kNN**: the question embedded by the sentence encoder, the five most similar
           labelled questions vote, restricted to the family when a cue found one. With no encoder (no
           weights, no network) the rules alone answer and say so; a question no rule touches is then
           SCENE_VQA, the intent that asks nothing of a specialist.

        Why not a model for all of it: the rules are where a mistake must be impossible (a count must
        never reach the VLM), the kNN is where wording varies. Why not rules for all of it: measured in
        the harness - rules alone leave a fifth of the held-out questions to the default.
"""

import asyncio
import logging
from dataclasses import dataclass

from app.constants.intents import Intent
from app.constants.routing import (
    ASKING_LEAD,
    CHANGE_FAMILY,
    CHANGE_QUESTION_OPENERS,
    CROSS_MODAL_CUE,
    DETECT_CUE,
    EVIDENCE_CUE,
    GROUND_CUE,
    INTENT_NEIGHBOURS,
    INTENT_UNCERTAIN_MARGIN,
    PERCEPTION_OPENER,
    SEGMENT_NOUN_CUE,
    SEGMENT_VERB_CUE,
    Modality,
    TemporalScope,
)
from app.models.encoder import SentenceEncoder
from app.services.query.bank import EmbeddedBank
from app.services.query.entities import QueryEntities, extract_entities, normalise_query
from app.services.query.math.nearest import nearest_vote, normalise_rows

logger = logging.getLogger(__name__)

RULE_METHOD = "rule"
KNN_METHOD = "knn"
DEFAULT_METHOD = "default"


@dataclass(frozen=True, slots=True)
class IntentDecision:
    intent: Intent
    # `rule`: a cue settled it; `knn`: the bank voted; `default`: no cue and no encoder.
    method: str
    # The cue that narrowed the family, named, or `None`.
    rule: str | None
    # Winner's vote share and lead over the runner-up when the kNN chose; 1.0 for a rule.
    confidence: float
    margin: float
    # `(bank question, its intent, similarity)`, most similar first; empty for a rule.
    neighbours: tuple[tuple[str, Intent, float], ...] = ()

    @property
    def uncertain(self) -> bool:
        return self.method == KNN_METHOD and self.margin < INTENT_UNCERTAIN_MARGIN


def rule_family(text: str, entities: QueryEntities) -> tuple[frozenset[Intent] | None, str | None]:
    """The family a cue narrows the question to, and the cue's name. `(None, None)` when no cue fires."""
    lowered = ASKING_LEAD.sub("", normalise_query(text))
    if entities.temporal == TemporalScope.PRIOR or EVIDENCE_CUE.search(lowered):
        return frozenset({Intent.EVIDENCE_RECALL}), "asks about earlier evidence"
    if entities.modality == Modality.BOTH or CROSS_MODAL_CUE.search(lowered):
        return frozenset({Intent.CROSS_MODAL}), "names both sensors"
    if entities.modality == Modality.SAR and entities.spectral_phrase:
        # A spectral target is an optical quantity; asking for it "with radar" is asking for both.
        return frozenset({Intent.CROSS_MODAL}), "names SAR with an optical target"
    if entities.temporal == TemporalScope.PAIR:
        if CHANGE_QUESTION_OPENERS.search(lowered):
            return frozenset({Intent.CHANGE_VQA}), "change cue, asked as a question"
        if entities.wants_map or entities.wants_location or DETECT_CUE.search(lowered):
            return frozenset({Intent.CHANGE_DETECT}), "change cue, asked as a map"
        return CHANGE_FAMILY, "change cue"
    if entities.index_named:
        return frozenset({Intent.INDEX_QUERY}), f"names the index {entities.index_named}"
    if SEGMENT_VERB_CUE.search(lowered) or (SEGMENT_NOUN_CUE.search(lowered) and (entities.wants_map or entities.wants_area)):
        return frozenset({Intent.SEGMENT}), "segmentation word"
    if entities.wants_count and (entities.objects or entities.unknown_objects):
        return frozenset({Intent.DETECT}), "counts an object"
    if DETECT_CUE.search(lowered):
        return frozenset({Intent.DETECT}), "detection word"
    if PERCEPTION_OPENER.search(lowered):
        return frozenset({Intent.SCENE_VQA}), "asks what the picture shows"
    if entities.spectral_phrase and not entities.objects and not entities.unknown_objects and (entities.wants_area or entities.wants_map or entities.wants_location):
        return frozenset({Intent.INDEX_QUERY}), f"spectral target '{entities.spectral_phrase}' asked as area, map or location"
    if GROUND_CUE.search(lowered) and not entities.spectral_phrase:
        return frozenset({Intent.GROUND}), "locating verb"
    return None, None


async def classify_intent(
    query: str, *, encoder: SentenceEncoder | None, bank: EmbeddedBank | None, entities: QueryEntities | None = None,
    use_rules: bool = True,
) -> IntentDecision:
    """The cascade. `encoder` and `bank` may be `None` - rules alone, stated in `method`. `use_rules=False`
    is the kNN alone, for the harness's ablation; it is not a production setting."""
    entities = entities if entities is not None else extract_entities(query)
    family, rule = rule_family(query, entities) if use_rules else (None, None)
    if family is not None and len(family) == 1:
        return IntentDecision(next(iter(family)), RULE_METHOD, rule, 1.0, 1.0)
    if encoder is None or bank is None:
        fallback = next(iter(sorted(family, key=str))) if family else Intent.SCENE_VQA
        return IntentDecision(fallback, DEFAULT_METHOD, rule, 0.0, 0.0)

    vector = await asyncio.to_thread(encoder.encode, [normalise_query(query)])
    vector = normalise_rows(vector)[0]
    candidates = frozenset(intent.value for intent in family) if family else None
    vote = nearest_vote(vector, bank.vectors, bank.labels, INTENT_NEIGHBOURS, candidates)
    neighbours = tuple((bank.rows[index].query, bank.rows[index].intent, round(similarity, 3)) for index, similarity in vote.neighbours)
    return IntentDecision(Intent(vote.label), KNN_METHOD, rule, round(vote.confidence, 3), round(vote.margin, 3), neighbours)
