"""Gives every run the ability to survive the process that started it - resume, replay and durability, in one object.

what  : `open_checkpointer()`, which yields a configured LangGraph checkpointer, and `read_thread_state()`
        for asking what a thread got through before it stopped.
where : Opened once per CLI invocation by `cli/run.py`, and once per worker by Phase 2.5's Inngest
        functions. Passed to `StateGraph.compile(checkpointer=...)` and to nothing else.
how   : **This module is configuration, not implementation** (ADR-002). LangGraph's `AsyncSqliteSaver` is
        the whole of resume, replay and durability; what is written here is which file it opens and how
        hard it commits. Everything below is a decision about those two questions.

        **Why SQLite in Phase 1 and Postgres in Phase 2.** A checkpoint is per-run scratch belonging to the
        process running the pipeline. In Phase 1 that is one CLI process on one machine, and a file is the
        correct shape - no container to be up, no connection pool, and `aeris run` works on a laptop with
        Docker stopped. Phase 2.5 moves it to Postgres because Inngest workers are several processes that
        must see each other's checkpoints. `graph.compile()` takes either, so that move is a change here
        and nowhere else.

        **Why `durability="sync"`.** Measured, not taken from the documentation. A process killed mid-node
        leaves zero checkpoints under `exit` - the whole run is recomputed - and `async` leaves a window in
        which the most recent one is lost. `sync` commits before the next node starts. A pipeline node here
        is model inference measured in minutes and a SQLite commit is sub-millisecond, so the trade is not
        close. The measurement is recorded in `tests/integration/test_pipeline_durability.py`.

        **Why a context manager and not a module-level singleton** like `lib/redis.py` and `lib/storage.py`.
        Those hold pooled connections to shared infrastructure that many call sites reach for
        independently. A checkpointer is opened once, handed to exactly one `compile()` call, and must be
        closed before the process exits or the last WAL frames are never checkpointed into the database.
        `from_conn_string` is LangGraph's own context manager; wrapping it in a singleton would mean
        writing the teardown it already has.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import StateSnapshot

from app.config import settings
from app.lib.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def open_checkpointer() -> AsyncIterator[AsyncSqliteSaver]:
    """Open the run checkpointer for the lifetime of the block, creating its schema on first use.

    `setup()` is called explicitly rather than left to the first write. LangGraph would create the tables
    lazily, which means the first failure of a misconfigured path arrives partway through a run instead of
    before it starts - and `config.py` exists to convert exactly that class of late failure into an early
    one.
    """
    database_path = settings.checkpoint_database_path
    logger.debug("opening run checkpointer", extra={"path": str(database_path)})

    try:
        async with AsyncSqliteSaver.from_conn_string(str(database_path)) as checkpointer:
            await checkpointer.setup()
            yield checkpointer
    except OSError as error:
        # A directory that cannot be created, a read-only volume, a path that is already a directory.
        # Raised as a configuration error because that is what it is, and because the message then names
        # the setting the operator has to change.
        raise ConfigurationError(
            f"Could not open the run checkpointer at {database_path}. "
            "PIPELINE_CHECKPOINT_DATABASE_PATH must point somewhere this process can write.",
            details={"path": str(database_path)},
        ) from error


async def read_thread_state(graph: Any, thread_id: str) -> StateSnapshot:
    """What a thread got through, and which node it would run next.

    `snapshot.next` is the load-bearing part and is easy to misread: it is **empty for a finished run** and
    non-empty for one that stopped partway. That is how resume tells "already done, nothing to do" from
    "stopped before S13", without keeping a status of its own that could disagree with the checkpoint.

    The graph is typed `Any` because `CompiledStateGraph` is generic over four type parameters, and naming
    them here would tie this helper to one state schema. It is called with whichever graph the CLI built.
    """
    return await graph.aget_state({"configurable": {"thread_id": thread_id}})
