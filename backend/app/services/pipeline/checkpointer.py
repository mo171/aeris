"""Gives every run the ability to survive the process that started it - resume, replay and durability, in one object.

what  : `open_checkpointer()`, which yields a configured LangGraph checkpointer, `read_thread_state()`
        for asking what a thread got through before it stopped, and `read_state_for_step()` for branching.
where : Opened once per CLI invocation by `cli/run.py`, and once per worker by Phase 2.5's Inngest
        functions. Passed to `StateGraph.compile(checkpointer=...)` and to nothing else.
how   : **This module is configuration, not implementation** (ADR-002). LangGraph's `AsyncPostgresSaver` is
        the whole of resume, replay and durability; what is written here is which connection it opens and how
        hard it commits. Everything below is a decision about those two questions.

        **Why SQLite in Phase 1 and Postgres in Phase 2.** A checkpoint is per-run scratch belonging to the
        process running the pipeline. In Phase 1 that was one CLI process on one machine, and a file was the
        correct shape - no container to be up, no connection pool, and `aeris run` worked on a laptop with
        Docker stopped. Phase 2.5 moves it to Postgres because Inngest workers are several processes that
        must see each other's checkpoints across process boundaries. `graph.compile()` takes either, so that
        move is a change here and nowhere else.

        **Why a context manager and not a module-level singleton** like `lib/redis.py` and `lib/storage.py`.
        Those hold pooled connections to shared infrastructure that many call sites reach for
        independently. A checkpointer is opened once, handed to exactly one `compile()` call, and must be
        closed before the process exits. `from_conn_string` is LangGraph's own context manager; wrapping it
        in a singleton would mean writing the teardown it already has.
"""

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import StateSnapshot

from app.config import settings
from app.lib.exceptions import ConfigurationError

if sys.platform == "win32":
    import asyncio
    try:
        from asyncio import WindowsSelectorEventLoopPolicy
        if not isinstance(asyncio.get_event_loop_policy(), WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    except (ImportError, AttributeError):
        pass

logger = logging.getLogger(__name__)


def postgres_connection_string() -> str:
    """Derive clean psycopg connection string from settings.database_url."""
    return str(settings.database_url).replace("+asyncpg", "")


@asynccontextmanager
async def open_checkpointer(
    conn_string: str | None = None,
    *,
    allow_sqlite_fallback: bool = True,
) -> AsyncIterator[AsyncPostgresSaver | AsyncSqliteSaver]:
    """Open the run checkpointer for the lifetime of the block, creating its schema on first use.

    `setup()` is called explicitly rather than left to the first write. LangGraph would create the tables
    lazily, which means the first failure of a misconfigured path arrives partway through a run instead of
    before it starts - and `config.py` exists to convert exactly that class of late failure into an early
    one.
    """
    if conn_string is None:
        conn_string = postgres_connection_string()

    # If an explicit SQLite connection or path is provided (e.g. in legacy tests), open SQLite
    if conn_string.startswith("sqlite") or conn_string.endswith((".sqlite", ".db")):
        logger.debug("opening sqlite checkpointer", extra={"path": conn_string})
        try:
            async with AsyncSqliteSaver.from_conn_string(conn_string) as checkpointer:
                await checkpointer.setup()
                yield checkpointer
            return
        except OSError as error:
            raise ConfigurationError(
                f"Could not open the SQLite run checkpointer at {conn_string}.",
                details={"path": conn_string},
            ) from error

    logger.debug("opening postgres checkpointer", extra={"database_url": settings.database_url_without_password})

    checkpointer_cm = None
    checkpointer_entered = False
    use_fallback = False
    setup_error = None

    try:
        checkpointer_cm = AsyncPostgresSaver.from_conn_string(conn_string)
        checkpointer = await checkpointer_cm.__aenter__()
        checkpointer_entered = True
        await checkpointer.setup()
    except Exception as error:
        setup_error = error
        if checkpointer_cm is not None and checkpointer_entered:
            try:
                await checkpointer_cm.__aexit__(type(error), error, error.__traceback__)
            except Exception:
                pass
            checkpointer_cm = None
        if not allow_sqlite_fallback:
            raise ConfigurationError(
                f"Could not open the Postgres run checkpointer: {error}",
                details={"database_url": settings.database_url_without_password},
            ) from error
        use_fallback = True

    if use_fallback:
        fallback_path = settings.checkpoint_database_path
        logger.warning(
            "Could not connect to Postgres checkpointer (%s); falling back to SQLite at %s",
            setup_error,
            fallback_path,
        )
        try:
            async with AsyncSqliteSaver.from_conn_string(str(fallback_path)) as fallback_checkpointer:
                await fallback_checkpointer.setup()
                yield fallback_checkpointer
            return
        except Exception as fallback_error:
            raise ConfigurationError(
                f"Could not open the Postgres checkpointer ({setup_error}) nor fallback SQLite ({fallback_error}).",
                details={"database_url": settings.database_url_without_password, "sqlite_path": str(fallback_path)},
            ) from setup_error

    try:
        yield checkpointer
    finally:
        if checkpointer_cm is not None:
            await checkpointer_cm.__aexit__(None, None, None)


async def read_thread_state(graph: Any, thread_id: str) -> StateSnapshot:
    """What a thread got through, and which node it would run next.

    `snapshot.next` is the load-bearing part and is easy to misread: it is **empty for a finished run** and
    non-empty for one that stopped partway. That is how resume tells "already done, nothing to do" from
    "stopped before S13", without keeping a status of its own that could disagree with the checkpoint.

    The graph is typed `Any` because `CompiledStateGraph` is generic over four type parameters, and naming
    them here would tie this helper to one state schema. It is called with whichever graph the CLI built,
    or with a checkpointer instance directly.
    """
    config = {"configurable": {"thread_id": thread_id}}
    if hasattr(graph, "aget_state"):
        return await graph.aget_state(config)

    if hasattr(graph, "aget_tuple"):
        checkpoint_tuple = await graph.aget_tuple(config)
        if checkpoint_tuple is None:
            return StateSnapshot(
                values={},
                next=(),
                config=config,
                metadata={},
                created_at=None,
                parent_config=None,
                tasks=(),
                interrupts=(),
            )
        channel_values = checkpoint_tuple.checkpoint.get("channel_values", {})
        return StateSnapshot(
            values=channel_values,
            next=(),
            config=checkpoint_tuple.config,
            metadata=checkpoint_tuple.metadata,
            created_at=checkpoint_tuple.checkpoint.get("ts"),
            parent_config=checkpoint_tuple.parent_config,
            tasks=(),
            interrupts=(),
        )

    raise TypeError(f"Expected CompiledStateGraph or Checkpointer, got {type(graph).__name__}")


async def read_state_for_step(
    checkpointer: Any,
    thread_id: str,
    step_id: str,
) -> StateSnapshot | None:
    """Finds the checkpoint where the given step was completed, for branching."""
    config = {"configurable": {"thread_id": thread_id}}

    def extract_values(cp: Any) -> dict[str, Any]:
        if hasattr(cp, "values") and isinstance(cp.values, dict):
            return cp.values
        if hasattr(cp, "checkpoint") and isinstance(cp.checkpoint, dict):
            return cp.checkpoint.get("channel_values", {}) or {}
        return {}

    def matches_step(cp: Any, vals: dict[str, Any]) -> bool:
        trace_steps = vals.get("trace_step_ids", [])
        if isinstance(trace_steps, list) and step_id in trace_steps:
            return True
        metadata = getattr(cp, "metadata", {}) or {}
        if (
            metadata.get("step_id") == step_id
            or metadata.get("stage") == step_id
            or metadata.get("node") == step_id
        ):
            return True
        if vals.get("step_id") == step_id:
            return True
        return False

    def to_snapshot(cp: Any) -> StateSnapshot:
        if isinstance(cp, StateSnapshot):
            return cp
        vals = extract_values(cp)
        checkpoint_dict = getattr(cp, "checkpoint", {}) or {}
        return StateSnapshot(
            values=vals,
            next=(),
            config=getattr(cp, "config", config),
            metadata=getattr(cp, "metadata", {}),
            created_at=checkpoint_dict.get("ts") if isinstance(checkpoint_dict, dict) else None,
            parent_config=getattr(cp, "parent_config", None),
            tasks=(),
            interrupts=(),
        )

    # Collect checkpoints from either a compiled graph or a checkpointer
    checkpoints: list[Any] = []
    if hasattr(checkpointer, "aget_state_history"):
        async for item in checkpointer.aget_state_history(config):
            checkpoints.append(item)
    elif hasattr(checkpointer, "alist"):
        async for item in checkpointer.alist(config):
            checkpoints.append(item)
    else:
        return None

    # Checkpoints are returned newest-first (reverse chronological).
    # Filter matching checkpoints where step_id completed.
    matching: list[Any] = []
    for cp in checkpoints:
        vals = extract_values(cp)
        if matches_step(cp, vals):
            matching.append(cp)

    if not matching:
        return None

    # The oldest matching checkpoint represents when the step was first completed.
    earliest_match = matching[-1]
    return to_snapshot(earliest_match)
