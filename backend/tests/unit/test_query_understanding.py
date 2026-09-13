"""Query understanding without a model: the kNN arithmetic, the extractor, the cues, and the cascade with a fake encoder."""

import numpy as np
import pytest

from app.constants.intents import Intent
from app.constants.routing import Modality, SpatialRegion, TemporalScope
from app.services.query.bank import EmbeddedBank, LabelledQuery
from app.services.query.classifier import DEFAULT_METHOD, KNN_METHOD, RULE_METHOD, classify_intent, rule_family
from app.services.query.entities import extract_entities, normalise_query, required_ground_sample_distance
from app.services.query.math.nearest import nearest_vote, normalise_rows

# --- math ---------------------------------------------------------------------------------------------


def test_neighbours_vote_by_similarity_and_the_margin_says_how_clear_it_was() -> None:
    bank = normalise_rows(np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9], [0.7, 0.7]]))
    labels = ["A", "A", "B", "B", "B"]
    vote = nearest_vote(np.array([1.0, 0.0]), bank, labels, k=3)
    assert vote.label == "A" and vote.confidence > 0.7 and vote.margin > 0.4
    assert [index for index, _ in vote.neighbours] == [0, 1, 4]
    # Restricting the candidates changes who may vote, not the arithmetic.
    assert nearest_vote(np.array([1.0, 0.0]), bank, labels, k=3, candidates=frozenset({"B"})).label == "B"
    with pytest.raises(ValueError):
        nearest_vote(np.array([1.0, 0.0]), bank[:0], labels[:0], k=3)
    with pytest.raises(ValueError):
        nearest_vote(np.array([1.0, 0.0]), bank, labels, k=3, candidates=frozenset({"C"}))


def test_an_even_split_has_no_margin() -> None:
    bank = normalise_rows(np.array([[1.0, 0.0], [1.0, 0.0]]))
    vote = nearest_vote(np.array([1.0, 0.0]), bank, ["A", "B"], k=2)
    assert vote.margin == pytest.approx(0.0) and vote.confidence == pytest.approx(0.5)


# --- entities -----------------------------------------------------------------------------------------


def test_objects_resolve_to_detector_classes_and_a_place_is_not_a_target() -> None:
    entities = extract_entities("How many ships are in the harbour?")
    assert entities.objects == ("ship",) and entities.context_objects == ("harbor",)
    assert entities.wants_count and not entities.wants_area
    assert extract_entities("Count the cars and trucks").objects == ("small vehicle", "large vehicle")
    assert extract_entities("Are there planes here?").objects == ("plane",)
    # Whole words: "planetary" is not a plane; "buildings" is a thing no detector knows.
    assert extract_entities("planetary boundary").objects == ()
    assert extract_entities("How many buildings are there?").unknown_objects == ("buildings",)
    assert extract_entities("Pinpoint the water tower.").unknown_objects == ("water tower",)


def test_region_temporal_modality_dates_and_the_wants() -> None:
    entities = extract_entities("Show urban expansion in the north-east between 2020 and 2024 using Sentinel-2")
    assert entities.region == SpatialRegion.NORTH_EAST and entities.temporal == TemporalScope.PAIR
    assert entities.dates == ("2020", "2024") and entities.image_count == 2 and entities.modality == Modality.OPTICAL
    assert entities.spectral_phrase == "urban" and entities.wants_map
    assert extract_entities("top left corner").region == SpatialRegion.NORTH_WEST
    assert extract_entities("Compare the SAR and optical views").modality == Modality.BOTH
    assert extract_entities("radar backscatter").modality == Modality.SAR
    assert extract_entities("Show me what you found earlier").temporal == TemporalScope.PRIOR
    assert extract_entities("How much of the scene is water?").wants_area
    assert extract_entities("Show me the NDWI map").index_named == "ndwi"


def test_text_speak_is_folded_before_any_cue_sees_it() -> None:
    assert normalise_query("how many ships  R there?") == "how many ships are there?"
    assert normalise_query("why did u say its flooded") == "why did you say its flooded"
    assert extract_entities("how many ships r there").wants_count


def test_the_resolution_a_class_needs_follows_from_its_length() -> None:
    assert required_ground_sample_distance("small vehicle") == pytest.approx(4.5 / 8)
    assert required_ground_sample_distance("harbor") == pytest.approx(300 / 8)


# --- cues ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("How many ships are in the harbour?", {Intent.DETECT}),
        ("How many buildings are there?", {Intent.DETECT}),
        ("Detect all vehicles.", {Intent.DETECT}),
        ("How many hectares of open water are there?", {Intent.INDEX_QUERY}),
        ("Show me the NDWI map.", {Intent.INDEX_QUERY}),
        ("Where are the water bodies?", {Intent.INDEX_QUERY}),
        ("Segment the buildings.", {Intent.SEGMENT}),
        ("Has the built-up area increased between these two images?", {Intent.CHANGE_VQA}),
        ("Compare these two images and show where new buildings appeared.", {Intent.CHANGE_DETECT}),
        ("Find the differences between the two images.", {Intent.CHANGE_DETECT, Intent.CHANGE_VQA}),
        ("What changed between the optical and SAR images?", {Intent.CROSS_MODAL}),
        ("Confirm the urban extent with radar backscatter.", {Intent.CROSS_MODAL}),
        ("Show the region responsible for your answer.", {Intent.EVIDENCE_RECALL}),
        ("Which detections did you use for the count?", {Intent.EVIDENCE_RECALL}),
        ("Is there an airport in this image?", {Intent.SCENE_VQA}),
        ("Where is the airport?", {Intent.GROUND}),
        ("Tell me about this image.", {Intent.SCENE_VQA}),
        ("Highlight the oil refinery.", None),
    ],
)
def test_each_cue_narrows_to_its_family(query: str, expected: set[Intent] | None) -> None:
    family, rule = rule_family(query, extract_entities(query))
    assert family == (frozenset(expected) if expected else None)
    assert (rule is not None) == (expected is not None)


def test_a_count_never_reaches_the_vlm_by_any_wording() -> None:
    """The rule the whole phase rests on: every counting phrasing is DETECT, decided by a rule, before any model votes."""
    for query in (
        "how many ships r there", "Count the planes.", "Number of cars in the car park?", "total number of storage tanks",
        "Enumerate the helicopters in the north.", "How many buildings can you see?", "count all the pools please",
    ):
        family, _ = rule_family(query, extract_entities(query))
        assert family == frozenset({Intent.DETECT}), query


# --- cascade ------------------------------------------------------------------------------------------


class FakeEncoder:
    """Two dimensions: how 'change-like' and how 'perception-like' a sentence is, by keyword."""

    version = "fake-encoder"

    def encode(self, texts: list[str]) -> np.ndarray:
        rows = [[float("chang" in t or "differ" in t), float("what" in t or "describe" in t), float("where" in t)] for t in texts]
        return normalise_rows(np.array(rows, dtype=np.float32) + 1e-3)


def fake_bank() -> EmbeddedBank:
    rows = [
        LabelledQuery("What changed here?", Intent.CHANGE_VQA),
        LabelledQuery("Describe what is different", Intent.CHANGE_VQA),
        LabelledQuery("Where did it change", Intent.CHANGE_DETECT),
        LabelledQuery("Where are the changes", Intent.CHANGE_DETECT),
        LabelledQuery("Describe the scene", Intent.SCENE_VQA),
        LabelledQuery("What is this", Intent.SCENE_VQA),
        LabelledQuery("Where is the bridge", Intent.GROUND),
    ]
    encoder = FakeEncoder()
    return EmbeddedBank(rows, encoder.encode([row.query for row in rows]), encoder.version)


async def test_the_knn_chooses_within_the_family_a_cue_narrowed() -> None:
    decision = await classify_intent("Find the differences between the two images.", encoder=FakeEncoder(), bank=fake_bank())
    assert decision.method == KNN_METHOD and decision.rule == "change cue"
    assert decision.intent in {Intent.CHANGE_DETECT, Intent.CHANGE_VQA}
    assert all(intent in {Intent.CHANGE_DETECT, Intent.CHANGE_VQA} for _, intent, _ in decision.neighbours)


async def test_a_rule_decides_without_the_encoder_and_says_so() -> None:
    ruled = await classify_intent("How many ships are there?", encoder=None, bank=None)
    assert ruled.intent == Intent.DETECT and ruled.method == RULE_METHOD and ruled.confidence == 1.0
    defaulted = await classify_intent("Highlight the oil refinery.", encoder=None, bank=None)
    assert defaulted.intent == Intent.SCENE_VQA and defaulted.method == DEFAULT_METHOD and defaulted.confidence == 0.0
    narrowed = await classify_intent("Find the differences between the two images.", encoder=None, bank=None)
    assert narrowed.method == DEFAULT_METHOD and narrowed.intent in {Intent.CHANGE_DETECT, Intent.CHANGE_VQA}
