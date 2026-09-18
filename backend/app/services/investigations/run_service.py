"""Durable run lifecycle and dispatch service.

Connects investigations to the underlying LangGraph engine:
- Mints run_id and inserts initial durable Run record in Postgres.
- Prepares initial state (query, intent, parameter overrides, rerun step).
- Launches LangGraph run as a detached background task.
- Fans events out to provenance journal, figure writer, and HTTP stream consumers.
- Updates durable Run record upon terminal completion (COMPLETE, FAILED, CANCELLED).
- Fully decoupled from HTTP: if client disconnects, the run continues to checkpoint.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any

from geoalchemy2.shape import from_shape
from shapely.geometry import box
from sqlalchemy import select

from app.constants.geo import STORAGE_SRID
from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.statuses import RunStatus
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.db.models.investigation import Investigation as DbInvestigation, InvestigationScene as DbInvestigationScene
from app.db.models.run import Run as DbRun
from app.db.models.scene import Scene as DbScene
from app.lib import database
from app.lib.exceptions import ResourceNotFoundError
from app.schemas.events import AnalysisStreamEvent
from app.schemas.investigations import AnalysisRunRequest
from app.services.pipeline.checkpointer import open_checkpointer
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.figure_writer import open_figure_writer
from app.services.sessions.journal_writer import open_journal
from app.services.sessions.session import open_session

logger = logging.getLogger(__name__)


async def start_investigation_run(
    investigation_id: str,
    request: AnalysisRunRequest,
) -> tuple[str, AsyncIterator[AnalysisStreamEvent]]:
    """Initiate an analysis run and return (run_id, event_stream_generator)."""
    run_id = new_identifier(IdentifierPrefix.RUN)

    async with database.get_session() as session:
        inv = await session.get(DbInvestigation, investigation_id)
        if inv is None:
            raise ResourceNotFoundError(
                f"Investigation {investigation_id} not found",
                details={"investigationId": investigation_id},
            )

        # Convert region_bounds if present
        region_geom = None
        if request.region_bounds:
            b = request.region_bounds
            region_geom = from_shape(box(b.west, b.south, b.east, b.north), srid=STORAGE_SRID)

        # Record durable run row in DB
        db_run = DbRun(
            id=run_id,
            investigation_id=investigation_id,
            query=request.query,
            intent=None,
            status=RunStatus.RUNNING,
            region_bounds=region_geom,
            plan_id=request.plan_id,
            operation_id=request.operation_id,
            started_at=datetime.now(UTC),
            checkpoint_thread_id=run_id,
        )
        session.add(db_run)
        await session.commit()

        # Fetch scene slots
        slots_stmt = select(DbInvestigationScene).where(
            DbInvestigationScene.investigation_id == investigation_id
        )
        slots_res = await session.execute(slots_stmt)
        slots = list(slots_res.scalars().all())

    # Determine graph name based on slots and available imagery
    graph_name = GraphName.PROBE
    extra_state: dict[str, Any] = {
        "probe_pause_seconds": 0.05,
        "parameter_overrides": request.parameter_overrides,
        "rerun_from_step_id": request.rerun_from_step_id,
        "parent_run_id": request.parent_run_id,
        "region_bounds": (
            (request.region_bounds.west, request.region_bounds.south, request.region_bounds.east, request.region_bounds.north)
            if request.region_bounds
            else None
        ),
    }

    # If real scenes are available and files exist on disk, bind them
    if slots:
        async with database.get_session() as session:
            scenes = [await session.get(DbScene, s.scene_id) for s in slots]
            valid_scenes = [s for s in scenes if s is not None and s.cog_object_key]
            if valid_scenes and Path(valid_scenes[0].cog_object_key).exists():
                graph_name = GraphName.SINGLE_IMAGE
                extra_state["scene_directory"] = valid_scenes[0].cog_object_key
                extra_state["scene_id"] = valid_scenes[0].id

    queue: asyncio.Queue[AnalysisStreamEvent | None] = asyncio.Queue()
    fanout = EventFanout()

    async def sse_event_consumer(event: AnalysisStreamEvent) -> None:
        await queue.put(event)

    fanout.register("sse_stream", sse_event_consumer)

    # Launch execution in detached task
    asyncio.create_task(
        _execute_detached_run(
            run_id=run_id,
            investigation_id=investigation_id,
            query=request.query,
            graph_name=graph_name,
            fanout=fanout,
            extra_state=extra_state,
            queue=queue,
        )
    )

    async def event_generator() -> AsyncIterator[AnalysisStreamEvent]:
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event

    return run_id, event_generator()


async def _execute_detached_run(
    *,
    run_id: str,
    investigation_id: str,
    query: str,
    graph_name: GraphName,
    fanout: EventFanout,
    extra_state: dict[str, Any],
    queue: asyncio.Queue[AnalysisStreamEvent | None],
) -> None:
    """Execute LangGraph run, manage journals, and update durable DB record."""
    status = RunStatus.FAILED
    error_msg: str | None = None
    confidence: float | None = None

    try:
        async with open_checkpointer() as checkpointer, open_memory_store() as store:
            graph = GRAPH_BUILDERS[graph_name]().compile(checkpointer=checkpointer, store=store)

            async with open_session() as session:
                handle = await session.start(
                    graph=graph,
                    query=query,
                    intent=Intent.SCENE_VQA,
                    fanout=fanout,
                    extra_state=extra_state,
                )

                async with open_journal(handle.run_id) as journal, open_figure_writer(handle.run_id) as figures:
                    fanout.register("journal", journal)
                    fanout.register("figures", figures)
                    status = await handle.wait()
                    error_msg = handle.error
                    confidence = await handle._final_confidence()

    except Exception as exc:
        logger.exception("detached run error", extra={"run_id": run_id})
        status = RunStatus.FAILED
        error_msg = str(exc)
    finally:
        # Update durable DB record
        try:
            async with database.get_session() as db_session:
                r = await db_session.get(DbRun, run_id)
                if r is not None:
                    r.status = status
                    r.completed_at = datetime.now(UTC)
                    r.error_message = error_msg
                    r.confidence = confidence
                    r.total_duration_ms = max(
                        0,
                        round((datetime.now(UTC) - r.started_at).total_seconds() * 1000),
                    )
                    await db_session.commit()
        except Exception:
            logger.exception("failed to update run status in database", extra={"run_id": run_id})

        # Signal stream end
        await queue.put(None)
