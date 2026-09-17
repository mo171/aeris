"""Runs one pipeline graph over one request as a function: start, journal, figures, wait, read the checkpoint back.

what  : `AnalysisRequest` - what a run is asked and over what; `RunOutcome` - what came back; and
        `run_analysis()`, the one function that runs a graph for the CLI and for the agent.
where : `cli/analyse.py` (with a console, so the live trace draws) and `agents/tools/analysis_tools.py`
        (without one). One function, so the agent's run and the operator's run are the same run: same
        journal, same figures on disk, same provenance record, same checkpoint read at the end.
how   : The graph is chosen by the request's name through `GRAPH_BUILDERS` (a table), compiled with the
        run checkpointer and the memory store, started through a session (which owns the run id, the
        fan-out and the abandonment signal), and observed by the journal writer and the figure writer;
        the console's trace renderer joins when a console is given. The outcome is read from the
        checkpoint - `read_thread_state` - for the reason `cli/analyse.py` gives: the checkpoint is what a
        resumed run would see, and two sources for one number is how they come to disagree.

        `AnalysisRequest.initial_state()` is the only place the router's decision becomes pipeline state:
        the index target, the detector classes, the land-cover classes, the flags. Every key it writes is
        one `services/pipeline/state.py` declares and a node reads.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.raster import ProcessingLevel
from app.constants.statuses import RunStatus
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.figure_writer import open_figure_writer
from app.services.sessions.journal_writer import journal_path, open_journal
from app.services.sessions.session import open_session
from app.services.spectral.indices import IndexTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    """One question over one input (or a pair), and everything the router resolved about it."""

    graph: GraphName
    query: str
    intent: Intent
    # The primary input: a scene directory, a GeoTIFF or a picture. For a pair, the later date.
    scene: Path
    reference: Path | None = None
    declared_level: ProcessingLevel | None = None
    declared_resolution_metres: float | None = None
    is_sar: bool = False
    reference_is_sar: bool = False
    declared_registered: bool = False
    # The specialist the router chose, a `ModelId` value; the single-image graph's GROUND edge reads it.
    tool: str | None = None
    target: IndexTarget | None = None
    objects: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()
    wants_location: bool = False
    
    # Phase 2 Overrides & Re-run
    parameter_overrides: dict[str, Any] | None = None
    rerun_from_step_id: str | None = None
    parent_run_id: str | None = None

    def initial_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "scene_directory": str(self.scene), "scene_id": self.scene.name if self.scene.is_dir() else self.scene.stem,
            "declared_level": self.declared_level.value if self.declared_level else None,
            "declared_resolution_metres": self.declared_resolution_metres, "is_sar": self.is_sar,
            "objects": list(self.objects), "classes": list(self.classes), "wants_location": self.wants_location, "tool": self.tool,
            "parameter_overrides": self.parameter_overrides,
            "rerun_from_step_id": self.rerun_from_step_id,
            "parent_run_id": self.parent_run_id,
        }
        if self.reference is not None:
            state.update({
                "reference_directory": str(self.reference),
                "reference_scene_id": self.reference.name if self.reference.is_dir() else self.reference.stem,
                "reference_is_sar": self.reference_is_sar, "declared_registered": self.declared_registered,
            })
        if self.target is not None:
            state.update({
                "index": self.target.index.value, "target_lower": self.target.lower, "target_upper": self.target.upper,
                "target_label": self.target.label, "target_phrase": self.target.phrase,
            })
        return state


@dataclass(frozen=True, slots=True)
class RunOutcome:
    run_id: str
    status: RunStatus
    # The checkpointed state at the end: claims, evidence, measurement, answer tokens, provenance paths.
    values: dict[str, Any]
    journal: Path
    figures: tuple[Path, ...] = field(default=())
    # Why the run did not complete, in the words the `run-error` event carried; `None` when it did.
    error: str | None = None

    @property
    def claims(self) -> list[dict[str, Any]]:
        return list(self.values.get("claims") or [])

    @property
    def answer(self) -> str:
        return " ".join(self.values.get("answer_tokens") or [])

    @property
    def markdown_answer(self) -> str:
        return str(self.values.get("chat_markdown") or self.answer)

    @property
    def voice_narration(self) -> str:
        return str(self.values.get("voice_narration") or self.answer)


async def run_analysis(request: AnalysisRequest, *, console: Console | None = None) -> RunOutcome:
    """Run the request's graph end to end and return what the checkpoint holds when it stops."""
    from app.services.pipeline.invalidation import compute_invalidation_plan

    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = GRAPH_BUILDERS[request.graph]().compile(checkpointer=checkpointer, store=store)
        initial_state = request.initial_state()

        if request.parent_run_id is not None:
            parent_snapshot = await read_thread_state(graph, request.parent_run_id)
            parent_values = parent_snapshot.values or {}
            plan = compute_invalidation_plan(request.graph, changed_parameters=request.parameter_overrides)
            initial_state["reused_stages"] = [s.value for s in plan.reused_stages]
            initial_state["reuse_inference"] = plan.reuse_inference

            # Restore cached state keys for reused stages
            keys_to_restore = [
                "registration",
                "input_kind",
                "modality",
                "cloud_mask_path",
                "cloud_mask_object_key",
                "cloud_mask_storage_uri",
            ]
            if plan.reuse_inference:
                keys_to_restore.extend([
                    "change_probability_path",
                    "change_probability_object_key",
                    "change_probability_storage_uri",
                    "change_model_id",
                    "change_model_version",
                    "input_files",
                ])
            for key in keys_to_restore:
                if key in parent_values and key not in initial_state:
                    initial_state[key] = parent_values[key]

        async with open_session() as session:
            fanout = EventFanout()
            handle = await session.start(
                graph=graph, query=request.query, intent=request.intent, fanout=fanout, extra_state=initial_state,
            )
            async with open_journal(handle.run_id) as journal, open_figure_writer(handle.run_id) as figures:
                # Journal first: provenance before decoration (`services/sessions/fanout.py`).
                fanout.register("journal", journal)
                if console is not None:
                    from app.cli.renderers.trace_renderer import TraceRenderer

                    with TraceRenderer(console) as renderer:
                        fanout.register("trace", renderer)
                        fanout.register("figures", figures)
                        status = await handle.wait()
                else:
                    fanout.register("figures", figures)
                    status = await handle.wait()
            values = dict((await read_thread_state(graph, handle.run_id)).values) if status is RunStatus.COMPLETE else {}
            if status is RunStatus.COMPLETE:
                # One canonical report is projected into chat, speech preparation, and export files. The
                # projections are generated after the figure writer closes so PDFs can embed the exact bytes
                # a Phase 2 client would download.
                from app.schemas.events import serialise_event
                from app.services.reports.exporters import write_report_bundle

                figure_events = [serialise_event(event) for event in figures.events]
                bundle = await write_report_bundle(
                    run_id=handle.run_id, values=values, figure_paths=tuple(figures.written), figure_events=figure_events,
                )
                values.update({
                    "report_id": bundle.report.report_id,
                    "report_status": "completed",
                    "chat_markdown": bundle.markdown_path.read_text(encoding="utf-8"),
                    "voice_narration": bundle.voice_path.read_text(encoding="utf-8"),
                    "report_pdf_path": str(bundle.pdf_path), "report_json_path": str(bundle.json_path),
                    "report_summary_pdf_path": str(bundle.summary_pdf_path),
                    "report_geojson_path": str(bundle.geojson_path), "report_markdown_path": str(bundle.markdown_path),
                    "report_voice_path": str(bundle.voice_path),
                })
            return RunOutcome(
                handle.run_id, status, dict(values), journal_path(handle.run_id), tuple(figures.written), error=handle.error,
            )
