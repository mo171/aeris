"""Tests for evidence-bound, presentation-only interface control."""

from typing import Any

import pytest

from app.agents import graph
from app.agents.state import AgentState
from app.agents.tools.interface_tools import validate_ui_commands
from app.config import settings


def controller_state() -> AgentState:
    return AgentState(
        request_id="run-1",
        request="show the measured result",
        results=[
            {
                "request_id": "run-1",
                "claims": [{"id": "clm-1", "text": "Water was mapped."}],
                "evidence_ids": ["ev-1"],
                "layer_ids": ["layer-1"],
                "state": "completed",
                "run_id": "run-graph-1",
            }
        ],
        camera_targets={"target-1": {"latitude": 19.0, "longitude": 73.0, "altitudeMeters": 1000.0}},
        report_ids=["report-1"],
    )


def test_known_opaque_resources_resolve_but_hallucinated_ids_and_coordinates_are_dropped() -> None:
    calls = [
        {"name": "spotlight_claim", "args": {"claim_id": "clm-1", "reason": "the measured finding"}},
        {"name": "focus_camera_target", "args": {"camera_target_id": "target-made-up", "reason": "look there"}},
        {"name": "focus_camera_target", "args": {"camera_target_id": "target-1", "latitude": 99, "reason": "look there"}},
    ]
    commands = validate_ui_commands(calls, state=controller_state(), budget=10)
    assert commands == [
        {
            "commandId": "investigation.spotlightClaim",
            "params": {"claimId": "clm-1"},
            "reason": "the measured finding",
        },
        {
            "commandId": "globe.flyTo",
            "params": {"latitude": 19.0, "longitude": 73.0, "altitudeMeters": 1000.0},
            "reason": "look there",
        },
    ]


def test_interface_budget_and_reason_numeral_guard_are_enforced() -> None:
    calls = [
        {"name": "toggle_trace", "args": {"reason": "show the trace"}},
        {"name": "open_report", "args": {"report_id": "report-1", "reason": "open report 2"}},
        {"name": "focus_evidence", "args": {"evidence_id": "ev-1", "reason": "show evidence"}},
    ]
    commands = validate_ui_commands(calls, state=controller_state(), budget=2)
    assert [command["commandId"] for command in commands] == ["investigation.toggleTrace", "investigation.focusEvidence"]
    assert all("2" not in command["reason"] for command in commands)


@pytest.mark.asyncio
async def test_model_failure_emits_no_fallback_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openai")

    class BrokenModel:
        def bind_tools(self, tools: list[Any]) -> Any:
            raise AssertionError("bind_tools should be reached before invocation")

    monkeypatch.setattr(graph, "build_chat_model", lambda: BrokenModel())
    result = await graph.control_interface(controller_state())
    assert result["ui_commands"] == []
    assert "failed" in result["trace"][0]["state"]


@pytest.mark.asyncio
async def test_ai_disabled_path_requires_an_explicit_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "none")
    state = controller_state()
    result = await graph.control_interface(state)
    assert result["ui_commands"] == []
    state["ui_command_fixture"] = [{"name": "toggle_trace", "args": {"reason": "test fixture"}}]
    result = await graph.control_interface(state)
    assert result["ui_commands"][0]["commandId"] == "investigation.toggleTrace"
    assert "fixture" in result["trace"][0]["detail"]
