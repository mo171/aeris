"""Compound requests: filler stripped, clauses split, pronouns bound to the clause before, same asks merged - with no model loaded."""

from app.agents.router import SceneFacts, route_plan
from app.constants.intents import Intent
from app.constants.model_ids import ModelId
from app.services.query.decomposer import split_clauses, strip_filler


def test_filler_is_stripped_and_the_ask_is_kept() -> None:
    assert strip_filler("Hey Aeris, can you please take a look at this satellite image and tell me how many ships there are, please") == "tell me how many ships there are"
    assert strip_filler("So basically what I need is the NDVI map for me") == "the ndvi map"
    assert strip_filler("count the planes") == "count the planes"


def test_clauses_split_at_connectives_and_sentence_ends_but_not_inside_a_phrase() -> None:
    texts = [clause.text for clause in split_clauses("Map the water bodies, then count the boats and ships near the shoreline. Is the port busy?")]
    assert texts == ["map the water bodies", "count the boats and ships near the shoreline", "is the port busy"]
    texts = [clause.text for clause in split_clauses("Is there an airport? If yes, how many aircraft are there and where is the runway")]
    assert texts == ["is there an airport", "how many aircraft are there", "where is the runway"]
    texts = [clause.text for clause in split_clauses("give me the ndvi and the nbr for this scene, and after that outline the coastline")]
    assert texts == ["give me the ndvi", "the nbr for this scene", "outline the coastline"]
    [single] = split_clauses("Where are the water bodies?")
    assert single.text == "where are the water bodies" and not single.pronominal
    [_, pronominal] = split_clauses("Find the planes and count them")
    assert pronominal.text == "count them" and pronominal.pronominal


async def test_a_pronoun_clause_inherits_the_objects_and_the_same_ask_merges_into_one_step() -> None:
    plan = await route_plan("Find all the planes on the apron, mark where they are, and tell me how many of them there are", encoder=None, bank=None)
    assert plan.intents == (Intent.DETECT,)
    [step] = plan.steps
    assert step.entities.objects == ("plane",) and step.entities.wants_count and step.entities.wants_location
    assert step.tool == ModelId.DOTA_DETECTOR and len(plan.clauses) == 3


async def test_each_question_in_a_request_becomes_its_own_step_in_order() -> None:
    plan = await route_plan(
        "Okay so first map the water bodies in this scene using NDWI and then count the boats you can see near the shoreline", encoder=None, bank=None
    )
    assert plan.intents == (Intent.INDEX_QUERY, Intent.DETECT)
    assert plan.steps[0].entities.index_named == "ndwi" and plan.steps[1].entities.objects == ("ship",)
    plan = await route_plan("Has the lake shrunk between the two dates, and if so, where exactly did the water recede?", encoder=None, bank=None, facts=SceneFacts(image_count=2))
    assert plan.intents == (Intent.CHANGE_VQA, Intent.CHANGE_DETECT) and not plan.refused


async def test_a_change_context_carries_to_a_later_clause_that_has_no_cue_of_its_own() -> None:
    plan = await route_plan("compare these two images and highlight where the forest was cleared, and tell me how much forest area was lost", encoder=None, bank=None, facts=SceneFacts(image_count=2))
    assert plan.intents == (Intent.CHANGE_DETECT, Intent.CHANGE_VQA)


async def test_a_refused_step_does_not_stop_the_others_from_being_planned() -> None:
    plan = await route_plan("show me the water bodies and then count the cars on the roads", encoder=None, bank=None, facts=SceneFacts(ground_sample_distance=10.0))
    assert plan.intents == (Intent.INDEX_QUERY, Intent.DETECT)
    assert plan.steps[0].refusal is None and plan.steps[1].refusal is not None and plan.refused


async def test_a_merged_index_step_is_validated_on_its_target_not_on_the_pronoun_clause() -> None:
    plan = await route_plan("map the unhealthy vegetation and give me its area", encoder=None, bank=None)
    [step] = plan.steps
    assert step.intent == Intent.INDEX_QUERY and step.refusal is None and step.entities.wants_area
