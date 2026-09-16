"""Evidence-bound presentation capabilities offered to the interface-control node."""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from langchain_core.tools import tool

from app.constants.ui_commands import UiCommand
from app.constants.vlm import NUMERAL_PATTERN

logger = logging.getLogger(__name__)


class UiResourceKind(StrEnum):
    CLAIM = "claim"
    EVIDENCE = "evidence"
    LAYER = "layer"
    CAMERA_TARGET = "camera-target"
    REPORT = "report"
    NONE = "none"


Resolver = Callable[[str | None, Mapping[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True, slots=True)
class UiCapability:
    """One registered frontend capability and its safe backend parameter resolver."""

    command_id: UiCommand
    tool_name: str
    description: str
    resource_kind: UiResourceKind
    model_parameter: str | None
    resolver: Resolver
    presentation_only: bool = True


def _mapping_items(value: Any) -> list[tuple[str, Any]]:
    if isinstance(value, Mapping):
        return [(str(key), item) for key, item in value.items()]
    if isinstance(value, list):
        return [(str(item.get("id")), item) for item in value if isinstance(item, Mapping) and item.get("id")]
    return []


def _resource_ids(state: Mapping[str, Any], kind: UiResourceKind) -> set[str]:
    results = state.get("results") or []
    request_id = state.get("request_id")
    current = [result for result in results if not request_id or not result.get("request_id") or result.get("request_id") == request_id]
    sources: dict[UiResourceKind, set[str]] = {
        UiResourceKind.CLAIM: {str(claim["id"]) for result in current for claim in result.get("claims") or [] if claim.get("id")},
        UiResourceKind.EVIDENCE: {
            str(identifier)
            for result in current
            for identifier in (result.get("evidence_ids") or [])
        } | {
            str(identifier)
            for result in current
            for claim in result.get("claims") or []
            for identifier in claim.get("evidenceIds") or claim.get("evidence_ids") or []
        },
        UiResourceKind.LAYER: {
            str(identifier)
            for result in current
            for identifier in (result.get("layer_ids") or result.get("layerIds") or [])
        },
        UiResourceKind.CAMERA_TARGET: set(), UiResourceKind.REPORT: set(), UiResourceKind.NONE: set(),
    }
    camera_sources = list(_mapping_items(state.get("camera_targets")))
    for result in current:
        camera_sources.extend(_mapping_items(result.get("camera_targets")))
    sources[UiResourceKind.CAMERA_TARGET].update(identifier for identifier, target in camera_sources if isinstance(target, Mapping))
    sources[UiResourceKind.REPORT].update(
        str(result["report_id"])
        for result in current
        if result.get("report_id") and result.get("report_status") == "completed" and result.get("state") == "completed"
    )
    return sources[kind]


def _identity_resolver(parameter: str, kind: UiResourceKind) -> Resolver:
    def resolve(value: str | None, state: Mapping[str, Any]) -> dict[str, Any] | None:
        return {parameter: value} if isinstance(value, str) and value in _resource_ids(state, kind) else None

    return resolve


def _camera_resolver(value: str | None, state: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(value, str) or value not in _resource_ids(state, UiResourceKind.CAMERA_TARGET):
        return None
    targets = dict(_mapping_items(state.get("camera_targets")))
    for result in state.get("results") or []:
        targets.update(dict(_mapping_items(result.get("camera_targets"))))
    target = dict(targets.get(value) or {})
    latitude, longitude = target.get("latitude"), target.get("longitude")
    altitude = target.get("altitudeMeters", target.get("altitude_meters"))
    numbers = (latitude, longitude)
    if not all(isinstance(number, (int, float)) and math.isfinite(float(number)) for number in numbers):
        return None
    if altitude is not None and (not isinstance(altitude, (int, float)) or not math.isfinite(float(altitude)) or altitude < 0):
        return None
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None
    params: dict[str, Any] = {"latitude": latitude, "longitude": longitude}
    if altitude is not None:
        params["altitudeMeters"] = altitude
    return params


def _empty_resolver(value: str | None, state: Mapping[str, Any]) -> dict[str, Any] | None:
    return {} if value is None else None


def _report_resolver(value: str | None, state: Mapping[str, Any]) -> dict[str, Any] | None:
    """Authorize the canonical report handle, while the UI opens the active investigation's one drawer."""
    return {} if isinstance(value, str) and value in _resource_ids(state, UiResourceKind.REPORT) else None


UI_CAPABILITIES: tuple[UiCapability, ...] = (
    UiCapability(UiCommand.INVESTIGATION_SPOTLIGHT_CLAIM, "spotlight_claim", "Highlight a validated finding", UiResourceKind.CLAIM, "claim_id", _identity_resolver("claimId", UiResourceKind.CLAIM)),
    UiCapability(UiCommand.INVESTIGATION_FOCUS_EVIDENCE, "focus_evidence", "Pan to validated evidence", UiResourceKind.EVIDENCE, "evidence_id", _identity_resolver("evidenceId", UiResourceKind.EVIDENCE)),
    UiCapability(UiCommand.INVESTIGATION_TOGGLE_LAYER, "toggle_layer", "Show or hide a validated evidence layer", UiResourceKind.LAYER, "layer_id", _identity_resolver("layerId", UiResourceKind.LAYER)),
    UiCapability(UiCommand.GLOBE_FLY_TO, "focus_camera_target", "Focus a known evidence camera target", UiResourceKind.CAMERA_TARGET, "camera_target_id", _camera_resolver),
    UiCapability(UiCommand.INVESTIGATION_OPEN_REPORT, "open_report", "Open the active investigation report; the handle authorizes it but does not select another report", UiResourceKind.REPORT, "report_id", _report_resolver),
    UiCapability(UiCommand.INVESTIGATION_TOGGLE_TRACE, "toggle_trace", "Expose the execution trace when it explains progress", UiResourceKind.NONE, None, _empty_resolver),
)
# Descriptive alias for callers that treat this as the interface-control registry.
INTERFACE_CAPABILITIES = UI_CAPABILITIES
CAPABILITY_BY_TOOL: dict[str, UiCapability] = {capability.tool_name: capability for capability in UI_CAPABILITIES}


@tool
def spotlight_claim(claim_id: str, reason: str) -> str:
    """Highlight one validated claim by opaque id."""
    return claim_id


@tool
def focus_evidence(evidence_id: str, reason: str) -> str:
    """Pan to one validated evidence item by opaque id."""
    return evidence_id


@tool
def toggle_layer(layer_id: str, reason: str) -> str:
    """Show or hide one validated evidence layer by opaque id."""
    return layer_id


@tool
def focus_camera_target(camera_target_id: str, reason: str) -> str:
    """Focus a known camera target by opaque id; never provide coordinates."""
    return camera_target_id


@tool
def open_report(report_id: str, reason: str) -> str:
    """Open a completed report by opaque id."""
    return report_id


@tool
def toggle_trace(reason: str) -> str:
    """Expose the trace when it helps explain progress."""
    return ""


INTERFACE_TOOLS = [spotlight_claim, focus_evidence, toggle_layer, focus_camera_target, open_report, toggle_trace]


def _reason(args: Mapping[str, Any]) -> str | None:
    value = args.get("reason")
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 280:
        return None
    value = value.strip()
    return None if NUMERAL_PATTERN.search(value) else value


def validate_ui_commands(
    tool_calls: list[dict[str, Any]], *, claim_ids: set[str] | None = None, evidence_ids: set[str] | None = None,
    layer_ids: set[str] | None = None, state: Mapping[str, Any] | None = None, budget: int | None = None,
) -> list[dict[str, Any]]:
    """Turn model calls into commands only after resource, reason and budget validation."""
    legacy = state is None
    if state is None:
        state = {
            "request_id": None,
            "results": [{"claims": [{"id": identifier} for identifier in claim_ids or set()], "evidence_ids": list(evidence_ids or set()), "layer_ids": list(layer_ids or set())}],
        }
    maximum = max(0, budget if budget is not None else len(tool_calls))
    commands: list[dict[str, Any]] = []
    for call in tool_calls:
        if len(commands) >= maximum:
            logger.warning("interface command budget exhausted", extra={"budget": maximum})
            break
        capability = CAPABILITY_BY_TOOL.get(str(call.get("name") or call.get("tool") or ""))
        if capability is None or not capability.presentation_only:
            logger.warning("unknown or non-presentation interface capability dropped", extra={"tool": call.get("name")})
            continue
        args = call.get("args") or {}
        if not isinstance(args, Mapping):
            continue
        reason = _reason(args)
        if reason is None and not legacy:
            logger.warning("interface command reason missing or contains an unsupported numeral", extra={"tool": capability.tool_name})
            continue
        value = args.get(capability.model_parameter) if capability.model_parameter else None
        params = capability.resolver(value, state)
        if params is None:
            logger.warning("model named an unknown or invalid interface resource", extra={"tool": capability.tool_name, "id": value})
            continue
        command: dict[str, Any] = {"commandId": capability.command_id.value, "params": params}
        if reason is not None:
            command["reason"] = reason
        commands.append(command)
    return commands


def default_ui_commands(claims: list[dict[str, Any]], evidence_ids: list[str]) -> list[dict[str, Any]]:
    """Legacy deterministic fixture helper; production AI-enabled flow never calls it."""
    commands: list[dict[str, Any]] = []
    primary = next((claim for claim in claims if claim.get("isPrimary") and claim.get("id")), None)
    if primary is not None:
        commands.append({"commandId": UiCommand.INVESTIGATION_SPOTLIGHT_CLAIM.value, "params": {"claimId": primary["id"]}})
        first_evidence = next(iter(primary.get("evidenceIds") or evidence_ids), None)
        if first_evidence:
            commands.append({"commandId": UiCommand.INVESTIGATION_FOCUS_EVIDENCE.value, "params": {"evidenceId": first_evidence}})
    return commands
