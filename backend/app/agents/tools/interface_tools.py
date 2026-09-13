"""The interface commands the agent may fire, as LangChain tools the synthesis model is bound with - each checked against the run.

what  : `spotlight_claim`, `focus_evidence`, `toggle_layer`, `INTERFACE_TOOLS`, `validate_ui_commands()`,
        `default_ui_commands()`.
where : `agents/graph.py`'s synthesise node: `model.bind_tools(INTERFACE_TOOLS)`; the model's tool calls
        become `ui-command` requests only after `validate_ui_commands` has checked every id against the
        claims, evidence and layers the steps actually produced. Without a model, `default_ui_commands`
        spotlights the first primary claim and focuses its first evidence item.
how   : The ids mirror `frontend/lib/constants/commands.ts` (`constants/ui_commands.py`), the subset that
        names something in the run. A command with an id the run does not hold is dropped and logged - a
        model that asks the interface to spotlight a claim that does not exist is the one failure mode
        that must not reach the operator's screen. The wire event for these lands with the assistant
        stream in Phase 2; here they are data on the agent's state and lines in the CLI.
"""

import logging
from typing import Any

from langchain_core.tools import tool

from app.constants.ui_commands import AGENT_UI_COMMANDS, UiCommand

logger = logging.getLogger(__name__)


@tool
def spotlight_claim(claim_id: str) -> str:
    """Highlight one claim in the interface and its evidence on the map. Use the claim's id exactly."""
    return claim_id


@tool
def focus_evidence(evidence_id: str) -> str:
    """Pan the map to one evidence item. Use the evidence id exactly."""
    return evidence_id


@tool
def toggle_layer(layer_id: str) -> str:
    """Show or hide one evidence layer. Use the layer id exactly."""
    return layer_id


INTERFACE_TOOLS = [spotlight_claim, focus_evidence, toggle_layer]

_COMMAND_FOR_TOOL: dict[str, UiCommand] = {
    spotlight_claim.name: UiCommand.INVESTIGATION_SPOTLIGHT_CLAIM,
    focus_evidence.name: UiCommand.INVESTIGATION_FOCUS_EVIDENCE,
    toggle_layer.name: UiCommand.INVESTIGATION_TOGGLE_LAYER,
}


def validate_ui_commands(
    tool_calls: list[dict[str, Any]], *, claim_ids: set[str], evidence_ids: set[str], layer_ids: set[str]
) -> list[dict[str, Any]]:
    """The model's tool calls as `ui-command` requests, minus any that name something the run does not hold."""
    known = {"claimId": claim_ids, "evidenceId": evidence_ids, "layerId": layer_ids}
    commands: list[dict[str, Any]] = []
    for call in tool_calls:
        command = _COMMAND_FOR_TOOL.get(call.get("name", ""))
        if command is None:
            logger.warning("model called a tool that is not an interface command; dropped", extra={"tool": call.get("name")})
            continue
        parameter = AGENT_UI_COMMANDS[command]
        value = next(iter((call.get("args") or {}).values()), None)
        if parameter and value not in known[parameter]:
            logger.warning("model named an id the run does not hold; dropped", extra={"command": command.value, "id": value})
            continue
        commands.append({"commandId": command.value, "params": {parameter: value} if parameter else {}})
    return commands


def default_ui_commands(claims: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    """Without a model: spotlight the first primary claim that has an id, focus its first evidence item."""
    commands: list[dict[str, Any]] = []
    primary = next((claim for claim in claims if claim.get("isPrimary") and claim.get("id")), None)
    if primary is not None:
        commands.append({"commandId": UiCommand.INVESTIGATION_SPOTLIGHT_CLAIM.value, "params": {"claimId": primary["id"]}})
        first_evidence = next(iter(primary.get("evidenceIds") or evidence_ids), None)
        if first_evidence:
            commands.append({"commandId": UiCommand.INVESTIGATION_FOCUS_EVIDENCE.value, "params": {"evidenceId": first_evidence}})
    return commands
