"""Integration tests for the Postgres checkpointer migration (Phase 2.5).

Verifies that:
1. `open_checkpointer()` yields an `AsyncPostgresSaver` connected to PostgreSQL.
2. `checkpointer.setup()` creates the required checkpoint tables in Postgres.
3. Thread state can be written and read back via `read_thread_state()`.
4. `read_state_for_step()` accurately retrieves checkpoint snapshots for a given step ID.
"""

from operator import add
from typing import Annotated, TypedDict

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import text

from app.lib.database import get_engine
from app.services.pipeline.checkpointer import (
    open_checkpointer,
    read_state_for_step,
    read_thread_state,
)

pytestmark = pytest.mark.integration


class DummyState(TypedDict):
    val: str
    trace_step_ids: Annotated[list[str], add]


@pytest.mark.asyncio
async def test_open_checkpointer_yields_postgres_saver() -> None:
    """Verify open_checkpointer yields an AsyncPostgresSaver instance."""
    async with open_checkpointer() as checkpointer:
        assert isinstance(checkpointer, AsyncPostgresSaver)


@pytest.mark.asyncio
async def test_checkpointer_setup_creates_tables() -> None:
    """Verify checkpointer.setup() creates checkpoints, checkpoint_blobs, and checkpoint_writes tables."""
    async with open_checkpointer() as checkpointer:
        await checkpointer.setup()

    engine = await get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN ('checkpoints', 'checkpoint_blobs', 'checkpoint_writes')"
            )
        )
        existing_tables = {row[0] for row in result.fetchall()}

    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes"}.issubset(existing_tables)


@pytest.mark.asyncio
async def test_read_thread_state_round_trip() -> None:
    """Write state to a thread and verify read_thread_state reads it back intact."""
    thread_id = "test_thread_1"

    async with open_checkpointer() as checkpointer:
        if hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(thread_id)

        builder = StateGraph(DummyState)
        builder.add_node("step_a", lambda s: {"val": "saved_state", "trace_step_ids": ["step_a"]})
        builder.add_edge(START, "step_a")
        builder.add_edge("step_a", END)
        graph = builder.compile(checkpointer=checkpointer)

        await graph.ainvoke(
            {"val": "initial", "trace_step_ids": []},
            {"configurable": {"thread_id": thread_id}},
        )

        # Verify via compiled graph
        snapshot_from_graph = await read_thread_state(graph, thread_id)
        assert snapshot_from_graph.values["val"] == "saved_state"
        assert snapshot_from_graph.values["trace_step_ids"] == ["step_a"]

        # Verify via checkpointer directly
        snapshot_from_cp = await read_thread_state(checkpointer, thread_id)
        assert snapshot_from_cp.values["val"] == "saved_state"
        assert snapshot_from_cp.values["trace_step_ids"] == ["step_a"]


@pytest.mark.asyncio
async def test_read_state_for_step() -> None:
    """Verify read_state_for_step finds the exact checkpoint corresponding to a step."""
    thread_id = "test_thread_multi_step"

    async with open_checkpointer() as checkpointer:
        if hasattr(checkpointer, "adelete_thread"):
            await checkpointer.adelete_thread(thread_id)

        builder = StateGraph(DummyState)
        builder.add_node("step_1", lambda s: {"val": "val_1", "trace_step_ids": ["step_1"]})
        builder.add_node("step_2", lambda s: {"val": "val_2", "trace_step_ids": ["step_2"]})
        builder.add_edge(START, "step_1")
        builder.add_edge("step_1", "step_2")
        builder.add_edge("step_2", END)
        graph = builder.compile(checkpointer=checkpointer)

        await graph.ainvoke(
            {"val": "init", "trace_step_ids": []},
            {"configurable": {"thread_id": thread_id}},
        )

        # Step 1 state
        snap_1 = await read_state_for_step(checkpointer, thread_id, "step_1")
        assert snap_1 is not None
        assert snap_1.values["val"] == "val_1"
        assert snap_1.values["trace_step_ids"] == ["step_1"]

        # Step 2 state
        snap_2 = await read_state_for_step(checkpointer, thread_id, "step_2")
        assert snap_2 is not None
        assert snap_2.values["val"] == "val_2"
        assert snap_2.values["trace_step_ids"] == ["step_1", "step_2"]

        # Non-existent step
        snap_missing = await read_state_for_step(checkpointer, thread_id, "non_existent_step")
        assert snap_missing is None
