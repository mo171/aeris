"""The deterministic router: every intent is in every table, counting goes to the detector, and the four validations refuse with reasons."""

import pytest

from app.agents.router import INTENT_TOOLS, SceneFacts, route
from app.constants.detection import DOTA_CLASS_NAMES
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.constants.pipeline import GraphName
from app.constants.routing import INTENT_GRAPHS, OBJECT_LENGTH_METRES, OBJECT_SYNONYMS, UNBUILT_GRAPH_PHASE, Modality


def test_every_intent_is_in_every_table_and_every_synonym_is_a_detector_class() -> None:
    assert set(INTENT_GRAPHS) == set(Intent) == set(INTENT_TOOLS)
    assert set(UNBUILT_GRAPH_PHASE) == {intent for intent, graph in INTENT_GRAPHS.items() if graph is None}
    assert INTENT_GRAPHS[Intent.INDEX_QUERY] is GraphName.SINGLE_IMAGE
    assert INTENT_GRAPHS[Intent.CHANGE_DETECT] is INTENT_GRAPHS[Intent.CHANGE_VQA] is GraphName.TEMPORAL
    assert INTENT_GRAPHS[Intent.CROSS_MODAL] is GraphName.CROSS_MODAL
    assert Intent.CROSS_MODAL not in UNBUILT_GRAPH_PHASE
    assert set(OBJECT_SYNONYMS.values()) == set(DOTA_CLASS_NAMES) == set(OBJECT_LENGTH_METRES)


@pytest.mark.parametrize(
    "query",
    ["How many ships are in the harbour?", "count the planes", "Number of storage tanks?", "how many cars r there", "Detect every vehicle."],
)
async def test_a_count_is_the_detectors_and_never_the_vlms(query: str) -> None:
    decision = await route(query, encoder=None, bank=None)
    assert decision.intent == Intent.DETECT and decision.tool == ModelId.DOTA_DETECTOR and decision.refusal is None


async def test_an_object_no_detector_knows_is_refused_by_name_with_what_can_be_counted() -> None:
    decision = await route("How many buildings are there?", encoder=None, bank=None)
    assert decision.intent == Intent.DETECT and decision.refusal is not None
    assert "buildings" in decision.refusal and "small vehicle" in decision.refusal and "not measurements" in decision.refusal


async def test_the_resolution_gate_refuses_what_a_pixel_cannot_hold() -> None:
    cars_on_sentinel = await route("How many cars are there?", encoder=None, bank=None, facts=SceneFacts(ground_sample_distance=10.0))
    assert cars_on_sentinel.refusal is not None and "10 m per pixel" in cars_on_sentinel.refusal and "0.56 m" in cars_on_sentinel.refusal
    planes_on_sentinel = await route("Count the planes.", encoder=None, bank=None, facts=SceneFacts(ground_sample_distance=10.0))
    assert planes_on_sentinel.refusal is not None  # 30 m / 8 px = 3.75 m needed
    ships_on_aerial = await route("Count the ships.", encoder=None, bank=None, facts=SceneFacts(ground_sample_distance=0.5))
    assert ships_on_aerial.refusal is None
    unknown_resolution = await route("How many cars are there?", encoder=None, bank=None, facts=SceneFacts(ground_sample_distance=None))
    assert unknown_resolution.refusal is None


async def test_two_image_intents_need_two_images_and_cross_modal_needs_both_sensors() -> None:
    one = await route("Has the built-up area increased between these two images?", encoder=None, bank=None, facts=SceneFacts(image_count=1))
    assert one.intent == Intent.CHANGE_VQA and one.refusal is not None and "1 was given" in one.refusal
    two = await route("Has the built-up area increased between these two images?", encoder=None, bank=None, facts=SceneFacts(image_count=2))
    assert two.refusal is None
    optical_pair = await route(
        "Compare the SAR and optical views.", encoder=None, bank=None, facts=SceneFacts(image_count=2, modalities=(Modality.OPTICAL, Modality.OPTICAL))
    )
    assert optical_pair.intent == Intent.CROSS_MODAL and optical_pair.refusal is not None and "optical, optical" in optical_pair.refusal


async def test_an_index_question_the_engine_cannot_answer_is_refused_with_the_phrases_it_knows() -> None:
    known = await route("Where are the water bodies?", encoder=None, bank=None)
    assert known.intent == Intent.INDEX_QUERY and known.graph is GraphName.SINGLE_IMAGE and known.refusal is None
    unknown = await route("Show me the NDVI of the moon rocks and the snow cover map", encoder=None, bank=None)
    assert unknown.intent == Intent.INDEX_QUERY and unknown.refusal is None  # names ndvi: the engine draws it
    bare = await route("Map the bare soil", encoder=None, bank=None)
    assert bare.intent in {Intent.INDEX_QUERY, Intent.SCENE_VQA}
    if bare.intent == Intent.INDEX_QUERY:
        assert bare.refusal is not None and "No spectral index answers" in bare.refusal


async def test_grounding_a_detector_class_uses_the_detector_and_a_phrase_uses_the_vlm() -> None:
    tanks = await route("Locate the storage tanks near the coast.", encoder=None, bank=None)
    assert tanks.intent == Intent.GROUND and tanks.tool == ModelId.DOTA_DETECTOR
    stadium = await route("Where is the stadium?", encoder=None, bank=None)
    assert stadium.intent == Intent.GROUND and stadium.tool == ModelId.REMOTE_SENSING_VLM
    # Both go through the single-image graph; its GROUND edge sends the phrase to the VLM (1.10).
    assert stadium.graph is GraphName.SINGLE_IMAGE and tanks.graph is GraphName.SINGLE_IMAGE
