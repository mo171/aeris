"""Drives the agent graph for one request: start, pause at the plan, resume with the operator's decision, return the state.

what  : `AgentOutcome`, `Approver`, `converse()`.
where : `cli/agent.py` (an approver that prints the plan and asks) and the tests (an approver that
        strikes a step out programmatically). Phase 2's `/assistant/stream` is the same function with a
        streaming approver.
how   : The graph is compiled with the run checkpointer; the thread is the conversation (`agent_id`).
        `ainvoke` returns with `__interrupt__` when `approve` pauses; the approver is handed the plan and
        answers with the step ids to keep (or `None` for all); the graph resumes from the checkpoint with
        `Command(resume=...)` and runs to the end. A second request on the same thread sees the first's
        results, which is what evidence recall reads.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.types import Command

from app.agents.graph import build_agent_graph
from app.constants.raster import ProcessingLevel
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.llm.tracing import enable_tracing_if_configured
from app.services.pipeline.checkpointer import open_checkpointer

logger = logging.getLogger(__name__)

# Given the plan (wire form) and who wrote its prose; returns the step ids to keep, or None for all.
Approver = Callable[[dict[str, Any], str], Awaitable[list[str] | None]]


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    agent_id: str
    request_id: str
    state: dict[str, Any]

    @property
    def answer(self) -> str:
        return str(self.state.get("answer") or "")

    @property
    def plan(self) -> dict[str, Any]:
        return dict(self.state.get("plan") or {})

    @property
    def results(self) -> list[dict[str, Any]]:
        return [r for r in self.state.get("results") or [] if r.get("request_id") == self.request_id]

    @property
    def trace(self) -> list[dict[str, Any]]:
        return [t for t in self.state.get("trace") or [] if str(t.get("id", "")).startswith(self.request_id)]


async def converse(
    request: str, *, approver: Approver, agent_id: str | None = None, scene_directory: Path | None = None,
    reference_directory: Path | None = None, declared_registered: bool = False,
    image_paths: list[Path] | None = None, sar: list[bool] | None = None, declared_level: ProcessingLevel | None = None,
    ground_sample_distance: float | None = None,
) -> AgentOutcome:
    enable_tracing_if_configured()
    agent_id = agent_id or new_identifier(IdentifierPrefix.SESSION)
    request_id = new_identifier(IdentifierPrefix.RUN)
    config = {"configurable": {"thread_id": agent_id}}
    async with open_checkpointer() as checkpointer:
        graph = build_agent_graph().compile(checkpointer=checkpointer)
        state = await graph.ainvoke(
            {
                "agent_id": agent_id, "request_id": request_id, "request": request,
                "scene_directory": str(scene_directory) if scene_directory else None,
                "reference_directory": str(reference_directory) if reference_directory else None, "declared_registered": declared_registered,
                "image_paths": [str(p) for p in image_paths or []], "sar": list(sar or [False] * len(image_paths or [])),
                "declared_level": declared_level.value if declared_level else None, "ground_sample_distance": ground_sample_distance,
            },
            config,
        )
        interrupts = state.get("__interrupt__") or []
        if interrupts:
            payload = interrupts[0].value
            kept = await approver(payload["plan"], payload.get("planSource", "template"))
            # Always a dict: LangGraph 1.2 trips over `Command(resume=None)`; `enabledStepIds: None` keeps every step.
            state = await graph.ainvoke(Command(resume={"enabledStepIds": kept}), config)
    return AgentOutcome(agent_id, request_id, dict(state))
