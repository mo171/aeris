"""The agent without a network: the plan is the router's, the prose is checked, the pause returns the operator's choice, ids are verified."""

from typing import Any

import pytest
from jsonschema import Draft202012Validator

from app.agents import graph as agent_graph
from app.agents.legacy_planner import PlanProse, apply_approval, build_plan, template_plan, verify_prose
from app.agents.run import converse
from app.agents.state import StepRecord
from app.agents.tools.interface_tools import default_ui_commands, validate_ui_commands
from app.config import settings
from app.constants.contracts import CONTRACT_SCHEMAS_FILE
from app.constants.intents import Intent
from app.lib.llm.chat_model import build_chat_model, chat_model_record
from app.schemas.agent import AgentTraceStep, AnalysisPlan
from app.services.query.classifier import LLM_METHOD, classify_intent


def steps() -> list[StepRecord]:
    return [
        StepRecord(id="step-1", query="count the ships", intent="DETECT", tool="dota-detector", graph=None, method="rule", rule="counts an object",
                   refusal=None, objects=["ship"], unknown_objects=[], spectral_phrase=None, wants_count=True, wants_location=False, wants_area=False),
        StepRecord(id="step-2", query="how many cars are there", intent="DETECT", tool="dota-detector", graph=None, method="rule", rule="counts an object",
                   refusal="A small vehicle spans fewer than 8 pixels at 10 m per pixel; detecting one needs 0.56 m or finer.", objects=["small vehicle"],
                   unknown_objects=[], spectral_phrase=None, wants_count=True, wants_location=False, wants_area=False),
        StepRecord(id="step-3", query="is this a port", intent="SCENE_VQA", tool="rs-vlm", graph=None, method="rule", rule="asks what the picture shows",
                   refusal=None, objects=[], unknown_objects=["port"], spectral_phrase=None, wants_count=False, wants_location=False, wants_area=False),
    ]


def validator(module: str, name: str) -> Draft202012Validator:
    import json

    schemas = json.loads(CONTRACT_SCHEMAS_FILE.read_text(encoding="utf-8"))
    return Draft202012Validator(schemas[module][name])


def test_no_provider_means_no_model_and_every_path_has_a_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "none")
    assert build_chat_model() is None and chat_model_record() is None


def test_the_template_plan_is_the_routers_steps_with_refused_ones_off_and_validates_against_the_frontend() -> None:
    plan = template_plan(steps())
    assert [step.id for step in plan.steps] == ["step-1", "step-2", "step-3"]
    assert [step.is_enabled for step in plan.steps] == [True, False, True]
    assert plan.steps[0].model["id"] == "dota-detector" and plan.steps[0].stage_code.value == "S13" and plan.steps[2].stage_code.value == "S14"
    validator("features/investigation/schemas/analysis.schema.ts", "analysisPlanSchema").validate(plan.to_wire())


def test_plan_prose_may_not_add_steps_or_numbers_but_may_repeat_the_templates_numbers() -> None:
    plan = template_plan(steps())
    assert verify_prose(PlanProse(summary="Count, then look.", step_descriptions=["a", "b"]), plan) is not None
    assert "numerals" in (verify_prose(PlanProse(summary="Find the 12 ships.", step_descriptions=["a", "b", "c"]), plan) or "")
    assert verify_prose(PlanProse(summary="Count ships, then ask about the port.", step_descriptions=["Count ships.", "Cars need 0.56 m pixels; this scene has 10 m.", "Ask the model."]), plan) is None


async def test_without_a_model_the_plan_is_the_template_and_approval_only_strikes_out() -> None:
    plan, source = await build_plan("count the ships", steps(), model=None)
    assert source == "template"
    approved = apply_approval(plan, ["step-3"])
    assert [step.is_enabled for step in approved.steps] == [False, False, True]
    assert apply_approval(plan, None) == plan
    assert apply_approval(plan, ["step-2"]).steps[1].is_enabled is False  # a refused step cannot be enabled


def test_interface_commands_are_checked_against_the_run() -> None:
    calls = [
        {"name": "spotlight_claim", "args": {"claim_id": "clm_1"}},
        {"name": "spotlight_claim", "args": {"claim_id": "clm_made_up"}},
        {"name": "focus_evidence", "args": {"evidence_id": "ev_1"}},
        {"name": "fly_to", "args": {"where": "mumbai"}},
    ]
    commands = validate_ui_commands(calls, claim_ids={"clm_1"}, evidence_ids={"ev_1"}, layer_ids=set())
    assert commands == [
        {"commandId": "investigation.spotlightClaim", "params": {"claimId": "clm_1"}},
        {"commandId": "investigation.focusEvidence", "params": {"evidenceId": "ev_1"}},
    ]
    claims = [{"id": "clm_1", "isPrimary": True, "evidenceIds": ["ev_9"]}, {"id": "clm_2", "isPrimary": False}]
    assert default_ui_commands(claims, []) == [
        {"commandId": "investigation.spotlightClaim", "params": {"claimId": "clm_1"}},
        {"commandId": "investigation.focusEvidence", "params": {"evidenceId": "ev_9"}},
    ]
    assert default_ui_commands([{"text": "no id"}], []) == []


class FakeArbiter:
    def __init__(self, answer: Intent) -> None:
        self.answer = answer
        self.calls: list[tuple[str, frozenset[Intent]]] = []

    async def __call__(self, query: str, candidates: frozenset[Intent], neighbours: Any) -> tuple[Intent, str] | None:
        self.calls.append((query, candidates))
        return (self.answer, "because") if self.answer in candidates else None


async def test_the_arbiter_is_asked_only_on_an_uncertain_margin_and_only_within_the_family() -> None:
    from tests.unit.test_query_understanding import FakeEncoder, fake_bank

    arbiter = FakeArbiter(Intent.CHANGE_VQA)
    # A rule decides: the arbiter is never consulted.
    ruled = await classify_intent("How many ships are there?", encoder=FakeEncoder(), bank=fake_bank(), arbiter=arbiter)
    assert ruled.method == "rule" and arbiter.calls == []
    # The fake bank splits evenly on a change question: uncertain, so the arbiter chooses within the family.
    decided = await classify_intent("Find the differences between the two images.", encoder=FakeEncoder(), bank=fake_bank(), arbiter=arbiter)
    assert decided.method == LLM_METHOD and decided.intent == Intent.CHANGE_VQA and decided.rule == "because"
    assert arbiter.calls and arbiter.calls[0][1] == frozenset({Intent.CHANGE_DETECT, Intent.CHANGE_VQA})
    # An answer outside the family is ignored and the neighbours' decision stands.
    outside = FakeArbiter(Intent.SCENE_VQA)
    stood = await classify_intent("Find the differences between the two images.", encoder=FakeEncoder(), bank=fake_bank(), arbiter=outside)
    assert stood.method == "knn" and outside.calls


async def test_the_graph_pauses_on_the_plan_and_resumes_with_the_operators_choice(monkeypatch: pytest.MonkeyPatch, isolated_pipeline_paths: Any) -> None:
    """No model, no encoder, no image: the request is understood by rules, the plan is proposed, the pause
    returns what the approver said, the steps that need an image are skipped and the answer says so."""
    monkeypatch.setattr(settings, "llm_provider", "none")
    monkeypatch.setattr(settings, "synthesis_generator", "template")  # the VLM fallback has its own integration tests

    async def no_resources() -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(agent_graph, "routing_resources", no_resources)
    monkeypatch.setattr(agent_graph, "routing_arbiter", lambda: None)
    seen: list[dict[str, Any]] = []

    async def approver(plan: dict[str, Any], source: str) -> list[str] | None:
        seen.append(plan)
        assert source == "template"
        return [plan["steps"][0]["id"]]

    outcome = await converse("count the ships, then tell me if this is a port", approver=approver)
    assert seen and [step["id"] for step in seen[0]["steps"]] == ["step-1", "step-2"]
    assert outcome.state["approved_step_ids"] == ["step-1"]
    [first, second] = outcome.results
    assert first["intent"] == "DETECT" and first["state"] == "skipped" and "--image" in first["detail"]
    assert second["intent"] == "SCENE_VQA" and second["detail"] == "struck out by the operator"
    assert outcome.state["answer_source"] == "template" and "was not done" in outcome.answer
    labels = [step["label"] for step in outcome.trace]
    assert labels[:3] == ["Understanding the request", "Planning", "Plan approved"] and labels[-1] == "Answering"
    schema = validator("features/missionCommand/schemas/assistant.schema.ts", "executionTraceStepSchema")
    for step in outcome.trace:
        schema.validate(step)
        AgentTraceStep.model_validate(step)
    AnalysisPlan.model_validate(outcome.plan)


async def test_a_second_request_on_the_thread_recalls_the_first(monkeypatch: pytest.MonkeyPatch, isolated_pipeline_paths: Any) -> None:
    monkeypatch.setattr(settings, "llm_provider", "none")
    monkeypatch.setattr(settings, "synthesis_generator", "template")  # the VLM fallback has its own integration tests

    async def no_resources() -> tuple[None, None]:
        return None, None

    monkeypatch.setattr(agent_graph, "routing_resources", no_resources)
    monkeypatch.setattr(agent_graph, "routing_arbiter", lambda: None)

    async def keep_all(plan: dict[str, Any], source: str) -> None:
        return None

    first = await converse("count the ships", approver=keep_all)
    second = await converse("what did you find earlier", approver=keep_all, agent_id=first.agent_id)
    assert second.agent_id == first.agent_id and second.request_id != first.request_id
    [recall] = second.results
    assert recall["intent"] == "EVIDENCE_RECALL" and recall["state"] == "skipped"  # the first found nothing (no image)
    assert len(second.state["results"]) == 2  # both requests' results live on the thread


def test_the_ui_command_ids_mirror_the_frontends_registry() -> None:
    import re
    from pathlib import Path

    from app.constants.ui_commands import AGENT_UI_COMMANDS, UiCommand

    source = Path(__file__).resolve().parents[3] / "frontend" / "lib" / "constants" / "commands.ts"
    if not source.exists():
        pytest.skip(f"{source} is not on disk")
    frontend = set(re.findall(r'"([a-z]+\.[A-Za-z]+)"', source.read_text(encoding="utf-8")))
    assert {command.value for command in UiCommand} == frontend
    assert set(AGENT_UI_COMMANDS) <= set(UiCommand)


# --- The 2026-09-13 review: dependent clauses enrich, recall is provenance, synthesis input is unique. ------


async def test_a_follow_up_about_the_previous_step_enriches_it_instead_of_recalling() -> None:
    from app.agents.router import route_plan

    for request in (
        "map the water bodies and give me their area",
        "map the water bodies and give me the area in hectares as well",
        "map the water bodies and show me the evidence behind that number",
    ):
        plan = await route_plan(request, encoder=None, bank=None)
        assert plan.intents == (Intent.INDEX_QUERY,), request
        assert plan.steps[0].entities.spectral_phrase == "water bodies"
    assert (await route_plan("map the water bodies and give me their area", encoder=None, bank=None)).steps[0].entities.wants_area
    # A past-reference word keeps a genuine recall separate.
    recall = await route_plan("map the water bodies, then show me what you found earlier about the vegetation", encoder=None, bank=None)
    assert recall.intents == (Intent.INDEX_QUERY, Intent.EVIDENCE_RECALL)
    alone = await route_plan("what did you find about the water earlier", encoder=None, bank=None)
    assert alone.intents == (Intent.EVIDENCE_RECALL,)


async def test_recall_returns_the_claims_and_keeps_where_they_came_from_as_provenance() -> None:
    from app.agents.state import StepResult
    from app.agents.tools.analysis_tools import recall_evidence_step

    earlier = [StepResult(
        request_id="req-1", step_id="step-1", intent="INDEX_QUERY", tool="index-engine", state="completed", run_id="run_a",
        claims=[{"id": "clm_1", "text": "Water covers 2,667.3 hectares.", "isPrimary": True, "metrics": []}], evidence_ids=["ev_1", "ev_2"],
    )]
    result = await recall_evidence_step(StepRecord(id="step-1", query="what did you find earlier", intent="EVIDENCE_RECALL"), earlier=earlier)
    assert [claim["id"] for claim in result["claims"]] == ["clm_1"]
    assert all("Recalled" not in claim["text"] for claim in result["claims"])
    assert result["provenance"] == {"recalledFromRequest": "req-1", "recalledFromRun": "run_a", "recalledFromStep": "step-1", "claimCount": 1, "evidenceCount": 2}
    assert result["run_id"] == "run_a" and result["evidence_ids"] == ["ev_1", "ev_2"]


def test_synthesis_facts_are_unique_by_claim_id_and_refusals_speak_the_operators_words() -> None:
    from app.agents.graph import synthesis_facts
    from app.agents.state import StepResult
    from app.services.answer.constrained import template_answer

    water = {"id": "clm_1", "text": "Water covers 2,667.3 hectares.", "isPrimary": True, "metrics": [{"label": "Area", "value": 2667.3, "unit": "ha", "precision": 1}]}
    largest = {"id": "clm_2", "text": "The largest region covers 2,547.4 hectares.", "isPrimary": False, "metrics": []}
    steps = [
        StepRecord(id="step-1", query="map the water bodies", intent="INDEX_QUERY"),
        StepRecord(id="step-2", query="tell me what you found earlier", intent="EVIDENCE_RECALL"),
        StepRecord(id="step-3", query="count the cars on the roads", intent="DETECT"),
        StepRecord(id="step-4", query="describe the scene", intent="SCENE_VQA"),
    ]
    results = [
        StepResult(request_id="r", step_id="step-1", intent="INDEX_QUERY", state="completed", claims=[water, largest]),
        StepResult(request_id="r", step_id="step-2", intent="EVIDENCE_RECALL", state="completed", claims=[dict(water), dict(largest)]),
        StepResult(request_id="r", step_id="step-3", intent="DETECT", state="skipped", detail="A small vehicle spans fewer than 8 pixels at 10 m per pixel.", claims=[]),
        StepResult(request_id="r", step_id="step-4", intent="SCENE_VQA", state="skipped", detail="struck out by the operator", claims=[]),
    ]
    facts, notes = synthesis_facts(results, steps)
    assert [fact.get("id") for fact in facts if fact.get("id")] == ["clm_1", "clm_2"]
    texts = [fact["text"] for fact in facts]
    assert notes == ["These findings were recalled from earlier in this conversation; no new measurement was made."]
    assert not any("recalled" in text for text in texts)  # a note for the wording, never a fact
    assert "The request to count the cars on the roads was not done: A small vehicle spans fewer than 8 pixels at 10 m per pixel." in texts
    assert "The request to describe the scene was not done: it was struck out of the plan" in texts
    assert not any("Step 3" in text or "(DETECT)" in text for text in texts)
    answer = template_answer(facts)
    assert answer.count("2,667.3") == 1 and answer.count("2,547.4") == 1
