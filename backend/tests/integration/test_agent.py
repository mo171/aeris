"""The agent with the real language model, detector, VLM and scene: the 1.9 gate, the pause, the numbers, the swap.

what  : `aeris doctor`'s model row; plan prose from the model checked; a spoken request over the DOTA8
        crop answered by detector then VLM with the model phrasing exact numbers; a step struck out at the
        pause; the Mumbai scene with a refused count; evidence recalled across requests on a thread; the
        same suite of model calls against a second model with nothing but settings changed; the CLI.
where : Needs `LLM_PROVIDER` configured with a key, the detector and VLM weights, the DOTA8 crop and the
        Mumbai scene. Each skips by name when its input is missing.
how   : Every number asserted is a number a specialist computed: 3 basketball courts is the crop's label
        file, 2,667.3 ha is the index engine's water area on this scene (asserted through the claim's own
        metric, not typed in). The model's prose is asserted for *what it must not do* - invent a numeral,
        add a step, name an id the run does not hold - and for carrying every measured number exactly.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.agents.planner import build_plan
from app.agents.run import converse
from app.agents.state import StepRecord
from app.config import settings
from app.constants.datasets import DatasetId, DatasetSplit
from app.constants.raster import ProcessingLevel
from app.constants.vlm import NUMERAL_PATTERN
from app.lib.llm.chat_model import build_chat_model, probe_chat_model
from app.services.datasets.loader import split_directory

pytestmark = pytest.mark.integration

CROP = "P1470__1024__3296___1648"
SCENE = Path("data/datasets/sentinel2-l2a/mumbai_gate")


def requires_model() -> None:
    if settings.llm_provider == "none":
        pytest.skip("LLM_PROVIDER=none: no language model configured")


def crop_path() -> Path:
    path = split_directory(DatasetId.DOTA8, DatasetSplit.VALIDATION) / "images" / "val" / f"{CROP}.jpg"
    if not path.exists():
        pytest.skip(f"{path} is not on disk")
    return path


def scene_path() -> Path:
    if not (SCENE / "B08.tif").exists():
        pytest.skip(f"{SCENE} is not on disk")
    return SCENE


async def keep_all(plan: dict[str, Any], source: str) -> None:
    return None


def _exists(path: str) -> bool:
    return Path(path).exists()


async def test_the_configured_model_answers_the_doctor_probe() -> None:
    requires_model()
    health = await probe_chat_model()
    assert health.configured and health.reachable, health.detail
    assert health.version == f"llm:{settings.llm_provider}:{settings.llm_model}" and health.latency_ms is not None


async def test_the_model_phrases_the_plan_without_adding_steps_or_numbers() -> None:
    requires_model()
    steps = [
        StepRecord(id="step-1", query="count the ships in the harbour", intent="DETECT", tool="dota-detector", graph=None, method="rule",
                   rule="counts an object", refusal=None, objects=["ship"], unknown_objects=[], spectral_phrase=None, wants_count=True,
                   wants_location=False, wants_area=False),
        StepRecord(id="step-2", query="is the port busy", intent="SCENE_VQA", tool="rs-vlm", graph=None, method="rule",
                   rule="asks what the picture shows", refusal=None, objects=[], unknown_objects=["port"], spectral_phrase=None,
                   wants_count=False, wants_location=False, wants_area=False),
    ]
    plan, source = await build_plan("count the ships in the harbour and tell me if the port is busy", steps, model=build_chat_model())
    assert source == "llm", "the model's prose was rejected or failed; see the log"
    assert [step.id for step in plan.steps] == ["step-1", "step-2"] and [step.model_id for step in plan.steps] == ["dota-detector", "rs-vlm"]
    assert not NUMERAL_PATTERN.findall(plan.summary + " ".join(step.description for step in plan.steps))
    assert all(len(step.description) > 20 for step in plan.steps)


async def test_a_spoken_request_over_a_picture_is_planned_paused_run_and_phrased(isolated_pipeline_paths: Any) -> None:
    """Detector first, VLM second, the model phrases: the count is the label file's 3, spoken exactly."""
    requires_model()
    from app.models.loader import detect_device

    if not (await detect_device()).has_accelerator:
        pytest.skip("no accelerator for the detector and the VLM")
    seen: list[dict[str, Any]] = []

    async def approver(plan: dict[str, Any], source: str) -> None:
        seen.append({"plan": plan, "source": source})
        return None

    outcome = await converse("hey aeris, how many basketball courts are there, and does it look like a school?", approver=approver, image_paths=[crop_path()])
    assert seen and [s["modelId"] for s in seen[0]["plan"]["steps"]] == ["dota-detector", "rs-vlm"]
    [count, reading] = outcome.results
    assert count["state"] == "completed" and count["claims"][0]["metrics"][0]["value"] == 3.0
    assert reading["state"] == "completed" and "not a measurement" in reading["claims"][0]["text"]
    assert outcome.state["answer_source"] == "llm", outcome.trace[-1]["detail"]
    assert "3 basketball courts" in outcome.answer
    # Every numeral the model spoke is one a claim carries.
    permitted = set(NUMERAL_PATTERN.findall(" ".join(c["text"] for r in outcome.results for c in r["claims"])))
    assert set(NUMERAL_PATTERN.findall(outcome.answer)) <= permitted


async def test_a_step_struck_out_at_the_pause_is_not_run_and_the_answer_says_so(isolated_pipeline_paths: Any) -> None:
    requires_model()
    from app.models.loader import detect_device

    if not (await detect_device()).has_accelerator:
        pytest.skip("no accelerator")

    async def strike_second(plan: dict[str, Any], source: str) -> list[str]:
        return [plan["steps"][0]["id"]]

    outcome = await converse("count the basketball courts, then describe the scene", approver=strike_second, image_paths=[crop_path()])
    [count, described] = outcome.results
    assert count["state"] == "completed" and described["state"] == "skipped" and described["detail"] == "struck out by the operator"
    assert outcome.state["approved_step_ids"] == ["step-1"]


async def test_a_scene_request_runs_the_graph_refuses_the_count_and_phrases_the_measured_area(isolated_pipeline_paths: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    requires_model()
    monkeypatch.setattr(settings, "answer_generator", "template")  # the graph's own S16; the agent's synthesis is what is under test
    outcome = await converse(
        "map the water bodies in this scene and give me their area, then count the cars on the roads",
        approver=keep_all, scene_directory=scene_path(), declared_level=ProcessingLevel.L2A,
    )
    plan = outcome.plan
    assert [s["stageCode"] for s in plan["steps"]] == ["S12", "S13"] and [s["isEnabled"] for s in plan["steps"]] == [True, False]
    [water, cars] = outcome.results
    assert water["state"] == "completed" and water["run_id"] and _exists(water["journal"])
    assert cars["state"] == "skipped" and "0.56 m" in cars["detail"]
    area = next(m["value"] for c in water["claims"] if c["isPrimary"] for m in c["metrics"] if m["label"] == "Area")
    assert f"{area:,.1f}" in outcome.answer and outcome.state["answer_source"] == "llm", outcome.trace[-1]["detail"]
    assert "0.56 m" in outcome.answer or "cars" in outcome.answer.lower()
    commands = outcome.state["ui_commands"]
    assert commands and commands[0]["commandId"] == "investigation.spotlightClaim"
    assert commands[0]["params"]["claimId"] in {c["id"] for c in water["claims"]}
    # The record on disk for the operator.
    assert _exists(str(Path(water["journal"]).parent / water["run_id"] / "provenance.json"))


async def test_evidence_is_recalled_across_requests_on_a_thread_without_a_model_run(isolated_pipeline_paths: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    requires_model()
    monkeypatch.setattr(settings, "answer_generator", "template")
    first = await converse("show me the water bodies", approver=keep_all, scene_directory=scene_path(), declared_level=ProcessingLevel.L2A)
    second = await converse("what did you find about the water earlier", approver=keep_all, agent_id=first.agent_id)
    [recall] = second.results
    assert recall["intent"] == "EVIDENCE_RECALL" and recall["state"] == "completed"
    assert recall["run_id"] == first.results[0]["run_id"] and recall["latency_ms"] == 0
    assert any("recalled" in step["detail"].lower() for step in second.trace if step["label"].startswith("Step"))


async def test_the_gate_a_second_model_with_only_settings_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-002's claim: the provider abstraction is `init_chat_model`. The plan prose, the arbiter and the
    phrasing all run against another model with no code edit - here the second OpenAI model the account
    has; a second *provider* is the same two settings and its key."""
    requires_model()
    second = {"openai": "gpt-4.1-mini"}.get(settings.llm_provider)
    if second is None:
        pytest.skip(f"no second model listed for provider {settings.llm_provider}")
    monkeypatch.setattr(settings, "llm_model", second)
    monkeypatch.setattr(settings, "llm_reasoning_effort", None)
    health = await probe_chat_model()
    assert health.reachable and health.version.endswith(second), health.detail
    steps = [StepRecord(id="step-1", query="where are the water bodies", intent="INDEX_QUERY", tool="index-engine", graph="index-query", method="rule",
                        rule="spectral target 'water bodies' asked as area, map or location", refusal=None, objects=[], unknown_objects=[],
                        spectral_phrase="water bodies", wants_count=False, wants_location=True, wants_area=False)]
    plan, source = await build_plan("where are the water bodies", steps, model=build_chat_model())
    assert source == "llm" and len(plan.steps) == 1
    from app.services.answer.constrained import phrase_claims

    claims = [{"text": "Water covers 2,667.3 hectares of the scene: 22.9% of the ground observed.", "isPrimary": True,
               "metrics": [{"label": "Area", "value": 2667.3, "unit": "ha", "precision": 1}, {"label": "Share", "value": 22.9, "unit": "%", "precision": 1}]}]
    answer = await phrase_claims("where are the water bodies", claims, model=build_chat_model())
    assert answer.source == "llm" and "2,667.3" in answer.text and "22.9%" in answer.text, answer.rejection_reason


def test_the_agent_command_writes_the_record_and_exits_zero() -> None:
    if settings.llm_provider == "none":
        pytest.skip("LLM_PROVIDER=none")
    path = crop_path()
    completed = subprocess.run(
        [sys.executable, "-m", "app.cli.main", "agent", "how many basketball courts are there?", "--image", str(path), "--yes"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]
    assert "3 basketball courts" in completed.stdout
    record_line = next(line for line in completed.stdout.splitlines() if line.strip().startswith("record"))
    folder = Path(record_line.split("record", 1)[1].strip())
    assert folder.is_dir(), record_line
    record = json.loads((folder / "record.json").read_text(encoding="utf-8"))
    assert record["request"] == "how many basketball courts are there?"
    assert record["answerSource"] == "llm" and record["results"][0]["claims"][0]["metrics"][0]["value"] == 3.0
