"""Is the thing the operator opens and AERIS lives inside - one identity, one memory namespace, and every run started under it.

what  : `Session`, `open_session()`, and the run bookkeeping a session keeps.
where : Opened once by `cli/run.py`, and once per connected operator by Phase 2.4's WebSocket. Phase 1.9's
        agent holds one; Phase 1.13's voice loop holds one for as long as the operator is speaking to it.
how   : `product-truth.md` §1.6. A session is what makes AERIS *present* rather than a function that is
        called: it holds the thread, it knows what "it" and "the second one" refer to, and it is the thing
        that owns the runs rather than being owned by one.

        **A session is not a run, and this is the distinction the whole file exists to hold.** An operator
        asks several things in one sitting; some of those start ten-minute analyses that keep going while
        the next question is asked. So a session has *many* runs, some of them in flight at once, and it
        outlives all of them.

        **Each run gets its own LangGraph thread, and the thread id is the run id.** A checkpoint lineage
        belongs to one pipeline execution; sharing a thread across a session's runs would make the second
        run resume into the first one's half-finished state. The session id is what groups them and what
        namespaces memory - it is not a thread.

        **Closing a session does not kill its runs by default.** `aclose()` waits for them, and abandoning
        is a separate, explicit call. That ordering is the §1.3 rule applied one level up: leaving is not
        the same as cancelling, and a session that silently killed a ten-minute analysis on the way out
        would be the same mistake as barge-in cancelling a run.

        There is no persistence here yet. A session lives in the process, which is correct for Phase 1
        where the process *is* the application; Phase 2.4 gives it a row so a reconnecting browser finds
        the same session, and that is a change to this file and to nothing that uses it.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from app.constants.intents import Intent
from app.constants.pipeline import MEMORY_NAMESPACE_ROOT
from app.constants.statuses import RunStatus
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.exceptions import ResourceNotFoundError
from app.services.sessions.fanout import EventFanout
from app.services.sessions.run_handle import RunHandle, resume_run, start_run

logger = logging.getLogger(__name__)


class Session:
    """One sitting with AERIS: an identity, a memory namespace, and the runs launched under it."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.opened_at = datetime.now(UTC)
        self._runs: dict[str, RunHandle] = {}

    @property
    def memory_namespace(self) -> tuple[str, ...]:
        """Where this session's long-term memories are written.

        Carried by the session rather than passed to each `remember` call, because a memory written under
        the wrong namespace is invisible rather than wrong - the worst failure shape, since nothing
        surfaces and the operator simply finds AERIS has forgotten.
        """
        return (*MEMORY_NAMESPACE_ROOT, "session", self.session_id)

    @property
    def runs(self) -> tuple[RunHandle, ...]:
        """Every run started under this session, in the order they were started."""
        return tuple(self._runs.values())

    @property
    def running(self) -> tuple[RunHandle, ...]:
        """The runs still in flight. Non-empty is the normal state while a conversation continues."""
        return tuple(handle for handle in self._runs.values() if handle.is_running)

    def run(self, run_id: str) -> RunHandle:
        """One run by id, or a `ResourceNotFoundError` naming it."""
        handle = self._runs.get(run_id)
        if handle is None:
            raise ResourceNotFoundError(f"No run {run_id} in this session.", details={"runId": run_id})
        return handle

    async def start(
        self,
        *,
        graph: Any,
        query: str,
        intent: Intent,
        fanout: EventFanout,
        extra_state: dict[str, Any] | None = None,
    ) -> RunHandle:
        """Launch a run and return its handle immediately. The session is usable again on the next line."""
        run_id = new_identifier(IdentifierPrefix.RUN)
        initial_state: dict[str, Any] = {
            "run_id": run_id,
            "query": query,
            # `.value`, not the enum member - see `services/pipeline/state.py`. A checkpoint holds data.
            "intent": intent.value,
            "trace_step_ids": [],
            "answer_tokens": [],
            **(extra_state or {}),
        }

        handle = await start_run(
            run_id=run_id, graph=graph, initial_state=initial_state, fanout=fanout, intent=intent
        )
        self._runs[run_id] = handle
        return handle

    async def resume(self, *, graph: Any, run_id: str, intent: Intent, fanout: EventFanout) -> RunHandle:
        """Continue a run that stopped partway, from its checkpoint.

        Takes a `run_id` that this process may never have seen, because the common case is resuming a run
        a *previous* process started - the checkpoint is the source of truth, not this dictionary.
        """
        handle = await resume_run(run_id=run_id, graph=graph, fanout=fanout, intent=intent)
        self._runs[run_id] = handle
        return handle

    async def abandon_all(self, reason: str) -> None:
        """Stop every run in flight. Explicit, and never called on the way out of a session by itself."""
        in_flight = self.running
        if not in_flight:
            return
        logger.info(
            "abandoning every run in the session",
            extra={"session_id": self.session_id, "count": len(in_flight), "reason": reason},
        )
        await asyncio.gather(*(handle.abandon(reason) for handle in in_flight), return_exceptions=True)

    async def aclose(self) -> RunStatus | None:
        """Wait for every run to finish, then close the session.

        **Waits rather than cancels**, deliberately. Leaving a session is not the same statement as
        stopping the analysis it started; a caller that means the second says so by calling `abandon_all`
        first. Returns the status of the last run to finish, or `None` if the session started none.
        """
        in_flight = self.running
        if in_flight:
            logger.info(
                "waiting for runs still in flight before closing the session",
                extra={"session_id": self.session_id, "count": len(in_flight)},
            )
            await asyncio.gather(*(handle.wait() for handle in in_flight), return_exceptions=True)

        last = self.runs[-1] if self.runs else None
        return last.status if last else None


@asynccontextmanager
async def open_session() -> AsyncIterator[Session]:
    """Open a session for the lifetime of the block, closing it - and waiting for its runs - on the way out.

    The context manager is what makes "a session outlives its runs" enforceable rather than a convention:
    the block cannot exit while a run it started is still going, so a CLI invocation cannot return to the
    shell leaving a detached task writing to a journal nobody is reading.
    """
    session = Session(new_identifier(IdentifierPrefix.SESSION))
    logger.info("session opened", extra={"session_id": session.session_id})
    try:
        yield session
    finally:
        await session.aclose()
        logger.info("session closed", extra={"session_id": session.session_id})
