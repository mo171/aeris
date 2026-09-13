"""The deterministic router: a question in, the intent, the entities, the specialist and the graph out - or a refusal that says why.

what  : `SceneFacts`, `RoutingDecision`, `route()` for one question; `RoutingPlan`, `route_plan()` for a
        spoken request that may hold several.
where : `cli/analyse.py` and `cli/ask.py` call it before anything runs; 1.9's agent calls the same
        function from its planner node. Computes nothing (folder-archtecture.md: `agents/` plans, routes,
        dispatches) - the classifier and the extractor are services, the tables are constants.
how   : PDF p.24, kept literally: *a model chooses the intent, a table chooses the pipeline.* Then the
        data validation the PDF puts between them - "fail fast with an explanation, never silently
        degrade" - as four checks that need only what the caller already knows about its inputs:

        - **Counting goes to the detector, never the VLM.** `DETECT` names `dota-detector` as the tool;
          an object the detector has no class for is refused with the fifteen it has, and the VLM is
          offered for *presence* only, labelled. Measured basis: 1.7's count accuracy of 0.23.
        - **A pixel must be able to hold the object.** With the scene's ground sample distance known, a
          class whose typical length spans fewer than `MIN_OBJECT_PIXELS` is refused with both numbers.
        - **Two-image intents need two images; cross-modal needs both sensors.**
        - **An index question needs an index the engine has** - `resolve_index_target`'s own refusal.

        `graph` is the table's answer; `None` with `graph_note` names the phase that builds it, so a
        caller can say "this is CHANGE_DETECT and its graph is 1.10" rather than running the wrong one.

        **A request is a plan of steps** (`route_plan`): the decomposer splits it into clauses, each is
        routed on its own, a clause that names its subject by pronoun ("count them") inherits the objects
        of the clause before, and consecutive steps that are the same ask of the same tool ("find the
        planes, mark where they are, count them") merge into one step with the union of what was wanted.
        Measured before this existed: 0 of 11 compound requests routed to more than their loudest clause.
"""

import logging
from dataclasses import dataclass, replace

from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.pipeline import GraphName
from app.constants.routing import (
    INTENT_GRAPHS,
    MIN_OBJECT_PIXELS,
    PAIR_INTENTS,
    UNBUILT_GRAPH_PHASE,
    Modality,
    TemporalScope,
)
from app.lib.exceptions import InvalidRequestError, UpstreamUnavailableError
from app.models.encoder import SentenceEncoder, load_encoder
from app.services.query.bank import EmbeddedBank, embed_bank
from app.services.query.classifier import Arbiter, IntentDecision, classify_intent
from app.services.query.decomposer import Clause, split_clauses
from app.services.query.entities import QueryEntities, extract_entities, required_ground_sample_distance
from app.services.spectral.indices import resolve_index_target

logger = logging.getLogger(__name__)

# Intent -> the fleet member that does the work. `None` for evidence recall, which runs no model.
INTENT_TOOLS: dict[Intent, ModelId | None] = {
    Intent.SCENE_VQA: ModelId.REMOTE_SENSING_VLM,
    Intent.GROUND: ModelId.REMOTE_SENSING_VLM,
    Intent.INDEX_QUERY: ModelId.INDEX_ENGINE,
    Intent.DETECT: ModelId.DOTA_DETECTOR,
    Intent.SEGMENT: ModelId.SEGFORMER_LANDCOVER,
    Intent.CHANGE_DETECT: ModelId.CHANGEFORMER,
    Intent.CHANGE_VQA: ModelId.REMOTE_SENSING_VLM,
    Intent.CROSS_MODAL: ModelId.OPTICAL_SAR_FUSION,
    Intent.EVIDENCE_RECALL: None,
}


@dataclass(frozen=True, slots=True)
class SceneFacts:
    """What the caller knows about its inputs. Everything optional: unknown is not the same as absent."""

    # Metres per pixel of the finest band, when the input is georeferenced.
    ground_sample_distance: float | None = None
    image_count: int = 1
    modalities: tuple[Modality, ...] = ()


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    query: str
    decision: IntentDecision
    entities: QueryEntities
    tool: ModelId | None
    graph: GraphName | None
    graph_note: str | None
    # Why the question cannot be answered with these inputs, or `None`. A refusal is a decision too: the
    # intent stands and is reported, so the operator sees what was understood and what was missing.
    refusal: str | None

    @property
    def intent(self) -> Intent:
        return self.decision.intent


async def routing_resources() -> tuple[SentenceEncoder | None, EmbeddedBank | None]:
    """The encoder and the embedded bank, or `(None, None)` when the weights cannot be had - the rules
    alone then route, and every decision says `default` where the kNN would have spoken."""
    try:
        encoder = await load_encoder()
    except UpstreamUnavailableError as error:
        logger.warning("intent encoder unavailable; routing by rules alone", extra={"reason": str(error)})
        return None, None
    return encoder, await embed_bank(encoder)


def routing_arbiter() -> Arbiter | None:
    """The language model's vote on uncertain margins, when one is configured; `None` otherwise."""
    from app.agents.arbiter import build_arbiter

    return build_arbiter()


@dataclass(frozen=True, slots=True)
class RoutingPlan:
    """The request as ordered steps, one decision each, beside the clauses they came from."""

    query: str
    clauses: tuple[Clause, ...]
    steps: tuple[RoutingDecision, ...]

    @property
    def intents(self) -> tuple[Intent, ...]:
        return tuple(step.intent for step in self.steps)

    @property
    def refused(self) -> bool:
        return any(step.refusal for step in self.steps)


async def route_plan(
    query: str, *, encoder: SentenceEncoder | None, bank: EmbeddedBank | None, facts: SceneFacts | None = None,
    arbiter: Arbiter | None = None,
) -> RoutingPlan:
    clauses = split_clauses(query)
    steps: list[RoutingDecision] = []
    # A pair named anywhere earlier in the request ("compare these two images and ...") is the context of
    # every later clause that has no stronger cue of its own.
    pair_context = False
    both_sensors_context = False
    for clause in clauses:
        inherit = steps[-1].entities if steps and clause.pronominal else None
        inherit_intent = steps[-1].intent if inherit is not None else None
        decision = await route(clause.text, encoder=encoder, bank=bank, facts=facts, inherit=inherit, inherit_intent=inherit_intent, arbiter=arbiter)
        if both_sensors_context and decision.entities.modality == Modality.UNSPECIFIED and _weakly_decided(decision):
            # "compare the SAR and the optical ... and tell me if the flood extent matches": the pair of
            # sensors is what "matches" is about.
            decision = await route(clause.text, encoder=encoder, bank=bank, facts=facts, inherit=inherit, inherit_intent=inherit_intent, as_both=True, arbiter=arbiter)
        elif pair_context and decision.entities.temporal == TemporalScope.SINGLE and (_weakly_decided(decision) or _bare_locating(decision)):
            decision = await route(clause.text, encoder=encoder, bank=bank, facts=facts, inherit=inherit, inherit_intent=inherit_intent, as_pair=True, arbiter=arbiter)
        pair_context |= decision.entities.temporal == TemporalScope.PAIR
        both_sensors_context |= decision.entities.modality == Modality.BOTH
        if steps and not clause.past_reference and steps[-1].intent != Intent.EVIDENCE_RECALL and _dependent_follow_up(decision):
            # "give me their area", "and the area in hectares as well", "show me the evidence behind that
            # number", in the same breath as the measurement: a property or the evidence of the step just
            # planned, not a recall of an earlier request and not a step of its own. The step is enriched
            # with what was wanted; nothing is recalled and nothing repeats. (Review, 2026-09-13: this was
            # an EVIDENCE_RECALL step that echoed the same claims.)
            steps[-1] = _merge(steps[-1], decision, adopt=True)
        elif steps and clause.pronominal and _weakly_decided(decision) and (clause.object_pronoun or steps[-1].intent not in _OBJECT_INTENTS):
            # "tell me if they agree" after a cross-modal clause: the pronoun binds it to the ask before,
            # and nothing in the clause itself chose otherwise. The earlier step absorbs what it wants.
            # "does it look like a school" after a count is about the picture, not the courts: kept apart.
            steps[-1] = _merge(steps[-1], decision, adopt=True)
        elif steps and _same_ask(steps[-1], decision):
            steps[-1] = _merge(steps[-1], decision)
        else:
            steps.append(decision)
    return RoutingPlan(query, tuple(clauses), tuple(steps))


def _dependent_follow_up(decision: RoutingDecision) -> bool:
    """A clause that names nothing of its own and asks for a property (area, map, location, count) or the
    evidence: it is about the step before it. A clause with its own subject is its own step."""
    entities = decision.entities
    if entities.objects or entities.unknown_objects or entities.spectral_phrase or entities.index_named:
        return False
    if decision.intent == Intent.EVIDENCE_RECALL:
        return True
    asks_property = entities.wants_area or entities.wants_map or entities.wants_location or entities.wants_count
    # A question about what the picture shows ("is the area near the coast built up?") is its own step
    # even when it mentions an area; only an undecided clause is read as a property of the step before.
    return asks_property and decision.decision.method != "rule"


def _bare_locating(decision: RoutingDecision) -> bool:
    """"show me where" with nothing named: after a change question it asks where the change is."""
    return decision.intent == Intent.GROUND and not decision.entities.objects and not decision.entities.unknown_objects


def _weakly_decided(decision: RoutingDecision) -> bool:
    """A kNN or default decision, or the perception opener: the cues that yield to a pronoun's referent."""
    return decision.decision.method != "rule" or decision.decision.rule == "asks what the picture shows"


# Steps about things in the picture: a singular "it" after one of these means the picture, not the things.
_OBJECT_INTENTS = frozenset({Intent.DETECT, Intent.GROUND})

# Consecutive steps of these intents are one run of the tool whatever they name: two change questions are
# one comparison, two segmentation asks one pass, two counts one detector run over the union of classes,
# two perception questions one conversation with the VLM.
_MERGEABLE = frozenset({Intent.EVIDENCE_RECALL, Intent.CROSS_MODAL, Intent.CHANGE_DETECT, Intent.CHANGE_VQA, Intent.SEGMENT, Intent.DETECT, Intent.SCENE_VQA})


def _same_ask(first: RoutingDecision, second: RoutingDecision) -> bool:
    """Two consecutive steps that would run the same tool on the same things: one step, both wants."""
    if first.tool != second.tool:
        return False
    a, b = first.entities, second.entities
    if first.intent == second.intent and first.intent in _MERGEABLE:
        return True
    if {first.intent, second.intent} == {Intent.DETECT, Intent.GROUND}:
        # "detect the planes ... show me where the biggest one is": the detector's boxes answer both.
        return not b.objects or a.objects == b.objects
    if first.intent != second.intent:
        return False
    if first.intent == Intent.INDEX_QUERY:
        return b.spectral_phrase is None or a.spectral_phrase == b.spectral_phrase
    return a.objects == b.objects and a.unknown_objects == b.unknown_objects


def _merge(first: RoutingDecision, second: RoutingDecision, *, adopt: bool = False) -> RoutingDecision:
    """One step from two: the first's intent and tool; the wants of both; the first's refusal when the
    second was adopted (its own was judged under the wrong intent)."""
    a, b = first.entities, second.entities
    entities = replace(
        a, objects=tuple(dict.fromkeys(a.objects + b.objects)), unknown_objects=tuple(dict.fromkeys(a.unknown_objects + b.unknown_objects)),
        wants_count=a.wants_count or b.wants_count, wants_area=a.wants_area or b.wants_area,
        wants_location=a.wants_location or b.wants_location, wants_map=a.wants_map or b.wants_map,
        region=a.region or b.region, dates=a.dates or b.dates, matched=tuple(dict.fromkeys(a.matched + b.matched)),
    )
    refusal = first.refusal if adopt else first.refusal or second.refusal
    return replace(first, query=f"{first.query}; {second.query}", entities=entities, refusal=refusal)


async def route(
    query: str, *, encoder: SentenceEncoder | None, bank: EmbeddedBank | None, facts: SceneFacts | None = None,
    inherit: QueryEntities | None = None, inherit_intent: Intent | None = None, as_pair: bool = False, as_both: bool = False,
    arbiter: Arbiter | None = None,
) -> RoutingDecision:
    facts = facts or SceneFacts()
    entities = extract_entities(query)
    if inherit is not None and not entities.objects and not entities.unknown_objects and not entities.spectral_phrase:
        # "count them", "how much of it is there": the things are the previous clause's. Only what was
        # asked about is inherited - a region or a date named in one clause is not silently a constraint
        # on the next - and a spectral target only from an index step, so "those pixels" after an evidence
        # question does not become an index question.
        entities = replace(
            entities, objects=inherit.objects, context_objects=inherit.context_objects, unknown_objects=inherit.unknown_objects,
            spectral_phrase=inherit.spectral_phrase if inherit_intent == Intent.INDEX_QUERY or entities.wants_area else None,
        )
    if as_pair:
        entities = replace(entities, temporal=TemporalScope.PAIR)
    if as_both:
        entities = replace(entities, modality=Modality.BOTH)
    decision = await classify_intent(query, encoder=encoder, bank=bank, entities=entities, arbiter=arbiter)
    intent = decision.intent
    tool = INTENT_TOOLS[intent]
    if intent == Intent.GROUND and entities.objects:
        # A phrase that names a class the detector knows is grounded by the detector's boxes, which
        # scored 0.84 F1 where the VLM's boxes scored 0.36 IoU>=0.5.
        tool = ModelId.DOTA_DETECTOR
    refusal = await _validate(query, intent, entities, facts)
    graph = INTENT_GRAPHS[intent]
    logger.info(
        "query routed",
        extra={"intent": intent.value, "method": decision.method, "rule": decision.rule, "tool": tool.value if tool else None,
               "graph": graph.value if graph else None, "refused": refusal is not None},
    )
    return RoutingDecision(query, decision, entities, tool, graph, UNBUILT_GRAPH_PHASE.get(intent), refusal)


async def _validate(query: str, intent: Intent, entities: QueryEntities, facts: SceneFacts) -> str | None:
    if intent in PAIR_INTENTS and facts.image_count < 2:
        return f"{intent.value} compares two acquisitions and {facts.image_count} was given."
    if intent == Intent.CROSS_MODAL and facts.modalities and not {Modality.SAR, Modality.OPTICAL} <= set(facts.modalities):
        return f"CROSS_MODAL needs one optical and one SAR image; given {', '.join(m.value for m in facts.modalities)}."
    if intent == Intent.DETECT:
        if not entities.objects:
            from app.constants.detection import DOTA_CLASS_NAMES

            named = ", ".join(entities.unknown_objects) or "the object asked for"
            return (
                f"No detector in the fleet counts {named}. dota-detector counts: {', '.join(DOTA_CLASS_NAMES)}. "
                "The VLM can say whether it is present, but its counts are not measurements (0.23 accuracy, 1.7)."
            )
        if facts.ground_sample_distance is not None:
            for class_name in entities.objects:
                needed = required_ground_sample_distance(class_name)
                if facts.ground_sample_distance > needed:
                    return (
                        f"A {class_name} spans fewer than {MIN_OBJECT_PIXELS} pixels at {facts.ground_sample_distance:g} m per pixel; "
                        f"detecting one needs {needed:.2g} m or finer. The detector would run and report zero, which is not an answer."
                    )
    if intent == Intent.INDEX_QUERY:
        try:
            await resolve_index_target(entities.spectral_phrase or query)
        except InvalidRequestError as error:
            return str(error)
    return None
