"""Holds what AERIS is allowed to remember between sessions, kept apart from what any one run was doing.

what  : `open_memory_store()`, and `operator_namespace()` - the tuple every operator-scoped memory is
        written under.
where : Opened beside the checkpointer by `cli/run.py` and passed to `StateGraph.compile(store=...)`.
        Phase 1.9 adds the `remember` and `recall` tools that write and read through it.
how   : `product-truth.md` §1.6 - AERIS has two memories, and **the checkpointer is not one of them.** A
        checkpoint is the resume point of a single run; it is deleted when a run is cleaned up and it says
        nothing across sessions. Long-term memory is the opposite: it outlives every run, and losing it
        loses what the operator taught the system.

        That difference is why this is a **second SQLite file** rather than another table in the first. The
        two have opposite lifetimes, and sharing a file makes "clear the checkpoints" a command that can
        destroy the operator's memories. No amount of care at the call site makes that safe again.

        **Phase 1.0 wires it and writes nothing into it, deliberately.** What 1.0 owes is that the store
        exists, that it is configured in exactly one place, and that a session carries its namespace - so
        the phase which adds `remember` has somewhere to put things rather than a design decision to make.
        An empty store proven to open and round-trip is a smaller claim than a populated one, and it is one
        `tests/integration/test_pipeline_spine.py` actually checks.

        Namespaces are tuples and they are prefixed, for the same reason Redis keys are
        (`constants/redis_keys.py`): a store with no namespace convention cannot be listed, exported or
        cleaned up without already knowing every writer.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.store.sqlite.aio import AsyncSqliteStore

from app.config import settings
from app.constants.pipeline import MEMORY_NAMESPACE_ROOT, MEMORY_SCOPE_OPERATOR
from app.lib.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


def operator_namespace() -> tuple[str, ...]:
    """The namespace for memories about the operator rather than about one investigation.

    Sync, and a function rather than a constant, because Phase 1.9 adds an investigation-scoped sibling
    that takes an id - and having one of the pair be a constant and the other a function is the kind of
    asymmetry that gets one of them called wrongly.
    """
    return (*MEMORY_NAMESPACE_ROOT, MEMORY_SCOPE_OPERATOR)


@asynccontextmanager
async def open_memory_store() -> AsyncIterator[AsyncSqliteStore]:
    """Open long-term memory for the lifetime of the block, creating its schema on first use."""
    database_path = settings.memory_database_path
    logger.debug("opening long-term memory store", extra={"path": str(database_path)})

    try:
        async with AsyncSqliteStore.from_conn_string(str(database_path)) as store:
            await store.setup()
            yield store
    except OSError as error:
        raise ConfigurationError(
            f"Could not open long-term memory at {database_path}. "
            "PIPELINE_MEMORY_DATABASE_PATH must point somewhere this process can write.",
            details={"path": str(database_path)},
        ) from error
