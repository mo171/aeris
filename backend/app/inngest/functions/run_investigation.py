"""Durable investigation execution function for Inngest (Phase 2.5).

what  : `fn_run_investigation`, an Inngest function triggered on `aeris/investigation.requested`.
where : `app/inngest/functions/run_investigation.py`. Registered in `INNGEST_FUNCTIONS`.
how   : Per ADR-002:
        - Inngest guarantees the run happens, retries with exponential backoff on failure,
          and manages dead-letter semantics.
        - LangGraph manages graph state and durability via PostgreSQL `AsyncPostgresSaver`.
        - If an Inngest worker crashes or fails mid-run, Inngest retries the function. On retry,
          the function inspects PostgreSQL checkpoints for `run_id` and resumes from the last completed
          checkpoint rather than re-executing completed stages.
        - Real-time events fan out to Redis Pub/Sub (`RedisEventPublisher`), MinIO figures, and
          the local run journal.
"""

from datetime import UTC, datetime
import logging
from typing import Any

import inngest

from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.statuses import RunStatus
from app.constants.tasks import EventName
from app.db.models.run import Run as DbRun
from app.lib import database
from app.lib.inngest import get_inngest_client
from app.lib.redis import get_client as get_redis_client
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.figure_writer import open_figure_writer
from app.services.sessions.journal_writer import open_journal
from app.services.sessions.redis_stream import RedisEventPublisher
from app.services.sessions.session import open_session

logger = logging.getLogger(__name__)

inngest_client = get_inngest_client()


@inngest_client.create_function(
    fn_id="aeris-run-investigation",
    name="Run AERIS Investigation",
    trigger=inngest.TriggerEvent(event=EventName.INVESTIGATION_REQUESTED),
    cancel=[
        inngest.Cancel(
            event=EventName.INVESTIGATION_CANCELLED,
            if_exp="async.data.run_id == event.data.run_id",
        )
    ],
    retries=3,
)
async def fn_run_investigation(
    ctx: inngest.Context, step: inngest.Step | None = None
) -> dict[str, Any]:
    """Execute or resume an investigation run inside Inngest."""
    step_runner = step or ctx.step
    event_data = ctx.event.data or {}
    investigation_id: str = event_data["investigation_id"]
    run_id: str = event_data["run_id"]
    query: str = event_data.get("query", "")
    graph_name_str = event_data.get("graph_name", GraphName.PROBE.value)
    graph_name = GraphName(graph_name_str)
    extra_state: dict[str, Any] = event_data.get("extra_state", {})

    logger.info(
        f"Inngest fn_run_investigation triggered for run_id={run_id}, attempt={ctx.attempt}"
    )

    async def _execute() -> dict[str, Any]:
        redis_client = await get_redis_client()
        redis_publisher = RedisEventPublisher(investigation_id, redis_client)

        fanout = EventFanout()
        fanout.register("redis_stream", redis_publisher)

        async with open_checkpointer() as checkpointer, open_memory_store() as store:
            graph = GRAPH_BUILDERS[graph_name]().compile(checkpointer=checkpointer, store=store)

            # Check if this thread has an existing checkpoint to resume from
            snapshot = await read_thread_state(graph, run_id)
            has_checkpoint = bool(snapshot.values)

            async with open_session() as session:
                if has_checkpoint:
                    logger.info("Resuming run from Postgres checkpoint", extra={"run_id": run_id})
                    handle = await session.resume(
                        graph=graph,
                        run_id=run_id,
                        intent=Intent.SCENE_VQA,
                        fanout=fanout,
                    )
                else:
                    logger.info("Starting fresh run with Postgres checkpointing", extra={"run_id": run_id})
                    handle = await session.start(
                        graph=graph,
                        query=query,
                        intent=Intent.SCENE_VQA,
                        fanout=fanout,
                        extra_state=extra_state,
                        run_id=run_id,
                    )

                async with open_journal(handle.run_id) as journal, open_figure_writer(handle.run_id) as figures:
                    fanout.register("journal", journal)
                    fanout.register("figures", figures)
                    status = await handle.wait()
                    error_msg = handle.error
                    confidence = await handle._final_confidence()

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
            logger.exception("Failed to update run status in database", extra={"run_id": run_id})

        if status is RunStatus.FAILED:
            raise RuntimeError(error_msg or f"Investigation run {run_id} failed")

        return {
            "run_id": run_id,
            "status": status.value,
            "confidence": confidence,
        }

    try:
        return await step_runner.run("execute_investigation", _execute)
    except Exception as exc:
        logger.exception(f"FATAL exception in fn_run_investigation: {exc}")
        raise
