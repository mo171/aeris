"""The Phase 2.5 Gate Test: Inngest Retry & Durability over PostgreSQL Checkpointer.

what  : Proves ADR-002:
        1. One Inngest function wraps one graph invocation.
        2. Inngest guarantees durable execution and retries with backoff.
        3. LangGraph checkpoints each node to PostgreSQL via AsyncPostgresSaver.
        4. When an Inngest attempt fails or is interrupted mid-pipeline, the subsequent
           Inngest retry resumes execution from the PostgreSQL checkpoint rather than
           re-executing completed stages.
where : `tests/integration/inngest/test_run_investigation.py`. Needs live Postgres & Redis.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
import inngest
import pytest

from app.constants.intents import Intent
from app.constants.pipeline import GraphName
from app.constants.stages import PipelineStage
from app.constants.statuses import RunStatus
from app.constants.tasks import EventName
from app.db.models.run import Run as DbRun
from app.inngest.functions.run_investigation import fn_run_investigation
from app.lib import database
from app.main import app
from app.services.pipeline.checkpointer import open_checkpointer, read_thread_state
from app.services.pipeline.graphs import GRAPH_BUILDERS
from app.services.pipeline.memory_store import open_memory_store
from app.services.sessions.fanout import EventFanout
from app.services.sessions.session import open_session

pytestmark = pytest.mark.integration


class MockStep:
    """Mock Inngest Step runner that executes handlers synchronously."""

    async def run(self, step_id: str, handler: Any, *args: Any) -> Any:
        import inspect

        if inspect.iscoroutinefunction(handler):
            return await handler(*args)
        res = handler(*args)
        if inspect.isawaitable(res):
            return await res
        return res


@pytest.mark.asyncio
async def test_inngest_retry_resumes_from_postgres_checkpoint_without_reexecuting_s1() -> None:
    """The Phase 2.5 Durability Gate.

    Validates that:
    1. A run interrupted after Stage S1 leaves a durable checkpoint in PostgreSQL.
    2. The Inngest retry attempt loads the checkpoint and resumes directly from S20.
    3. The durable DbRun record in Postgres reaches COMPLETE.
    """
    unique_id = uuid4().hex[:8]
    run_id = f"run-gate-{unique_id}"

    # 1. Setup durable Investigation via API
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scenes_resp = await client.get("/api/v1/imagery?limit=1")
        assert scenes_resp.status_code == 200
        scene_id = scenes_resp.json()["items"][0]["id"]

        create_resp = await client.post(
            "/api/v1/investigations",
            json={
                "projectId": "prj_default",
                "sceneIds": [scene_id],
                "seedQuery": f"Gate test {unique_id}",
            },
        )
        assert create_resp.status_code in (200, 201)
        investigation_id = create_resp.json()["investigationId"]

    # Record durable Run in Postgres
    async with database.get_session() as db_session:
        run_record = DbRun(
            id=run_id,
            investigation_id=investigation_id,
            query="Verify Inngest checkpoint durability",
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
            checkpoint_thread_id=run_id,
        )
        db_session.add(run_record)
        await db_session.commit()

    # 2. Simulate Attempt 0: Run is started, completes S1, and is interrupted/abandoned before S20 completes
    fanout0 = EventFanout()
    s1_completed = asyncio.Event()

    from app.schemas.events import TraceStepEvent
    from app.constants.statuses import TraceStepState

    async def on_event0(event: Any) -> None:
        if (
            isinstance(event, TraceStepEvent)
            and event.step.stage_code == PipelineStage.S1
            and event.step.state == TraceStepState.COMPLETED
        ):
            s1_completed.set()

    fanout0.register("s1_tracker", on_event0)

    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = GRAPH_BUILDERS[GraphName.PROBE]().compile(checkpointer=checkpointer, store=store)

        async with open_session() as session:
            handle0 = await session.start(
                graph=graph,
                query="Verify Inngest checkpoint durability",
                intent=Intent.SCENE_VQA,
                fanout=fanout0,
                extra_state={"probe_pause_seconds": 2.0},  # S20 will pause for 2s
                run_id=run_id,
            )

            # Wait deterministically for Stage S1 to complete
            await asyncio.wait_for(s1_completed.wait(), timeout=5.0)

            # Abandon the run mid-node during S20 (simulating worker crash or timeout during S20)
            await handle0.abandon("Simulated Inngest worker crash")
            assert handle0.status is RunStatus.CANCELLED

        # 3. Assert that Stage S1 was checkpointed durably to PostgreSQL
        snapshot_after_crash = await read_thread_state(graph, run_id)
        assert snapshot_after_crash.values is not None
        assert "trace_step_ids" in snapshot_after_crash.values
        # Exactly 1 step (S1) must be checkpointed in PostgreSQL
        assert len(snapshot_after_crash.values["trace_step_ids"]) == 1
        tokens_before_resume = list(snapshot_after_crash.values.get("answer_tokens", []))
        assert len(tokens_before_resume) > 0  # S1 emitted "Understood: ..."

    # 4. Simulate Inngest Retry (Attempt 1): Inngest triggers fn_run_investigation
    inngest_event = inngest.Event(
        name=EventName.INVESTIGATION_REQUESTED.value,
        data={
            "investigation_id": investigation_id,
            "run_id": run_id,
            "query": "Verify Inngest checkpoint durability",
            "graph_name": GraphName.PROBE.value,
            "extra_state": {"probe_pause_seconds": 0.01},
        },
    )

    ctx = MagicMock()
    ctx.event = inngest_event
    ctx.attempt = 1
    step = MockStep()

    # Execute the Inngest function handler
    result = await fn_run_investigation._handler(ctx, step)
    assert result["run_id"] == run_id
    assert result["status"] == RunStatus.COMPLETE.value

    # 5. Verify the final resumed state in PostgreSQL
    async with open_checkpointer() as checkpointer, open_memory_store() as store:
        graph = GRAPH_BUILDERS[GraphName.PROBE]().compile(checkpointer=checkpointer, store=store)
        final_snapshot = await read_thread_state(graph, run_id)

        # Both S1 and S20 must now be recorded (total of 2 steps)
        trace_steps = final_snapshot.values["trace_step_ids"]
        assert len(trace_steps) == 2

        # Verify S1 was not re-executed:
        # In S1, answer_tokens appends ["Understood: ..."].
        # If S1 had re-executed on resume, "Understood" would appear twice.
        understood_tokens = [t for t in final_snapshot.values["answer_tokens"] if "Understood" in t]
        assert len(understood_tokens) == 1, (
            f"Stage S1 must not be re-executed on Inngest retry resume! Found {len(understood_tokens)} times."
        )

    # 6. Verify durable DbRun record in Postgres is updated to COMPLETE
    async with database.get_session() as db_session:
        persisted_run = await db_session.get(DbRun, run_id)
        assert persisted_run is not None
        assert persisted_run.status is RunStatus.COMPLETE
        assert persisted_run.completed_at is not None
        assert persisted_run.error_message is None
