"""Lets a running pipeline be stopped at a safe point instead of wherever the interpreter happened to be.

what  : `AbandonmentSignal`, the context binding that puts one in reach of a node, and
        `raise_if_abandoned()` - the check every node boundary performs.
where : Bound by `services/sessions/run_handle.py` around the graph invocation; checked by
        `services/pipeline/node.py` before and after every node.
how   : **`asyncio.Task.cancel()` alone is not enough, and this is the reason this module exists.**

        Cancelling a task raises `CancelledError` at the next `await`, which can be anywhere - halfway
        through writing an artefact, between two of the four bands of a composite, inside a `to_thread`
        call that will keep running to completion regardless because a thread cannot be cancelled. What
        comes out is a run whose state is whatever the interpreter reached, and a node that is not safely
        re-runnable on resume.

        A cooperative signal converts that into a decision the pipeline makes. The operator's stop sets a
        flag; the next node boundary sees it and raises `RunCancelledError`, which LangGraph handles as an
        ordinary node failure - so the checkpoint is intact and the run resumes from the last completed
        stage rather than from S1. Verified, not assumed: `tests/integration/test_pipeline_spine.py`
        abandons a run mid-graph and then resumes it to completion.

        Hard cancellation is still the backstop, because a node can fail to reach a boundary at all - a
        stalled socket read, a model that hangs. `run_handle.py` waits `pipeline_abandon_grace_seconds` for
        the cooperative stop and only then cancels the task. Two mechanisms, in that order, because the
        first one leaves the run resumable and the second one may not.

        The signal travels by `ContextVar`, not by an argument threaded through every node signature. A
        node's signature is `async def node(state) -> update` and belongs to LangGraph; adding a parameter
        to it would put our plumbing into the library's contract. Python copies the context into every task
        it spawns, which is the same mechanism LangGraph's own `get_stream_writer()` relies on.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.lib.exceptions import RunCancelledError

logger = logging.getLogger(__name__)


class AbandonmentSignal:
    """A one-way flag saying that the operator has asked this run to stop, and why.

    One-way on purpose: there is no `clear()`. A run that was abandoned and then un-abandoned would have to
    decide what to do about the node that already raised, and there is no correct answer. Resuming an
    abandoned run is done by starting a new run against the same thread, which goes through the checkpoint
    and is therefore explicit.
    """

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id
        self._reason: str | None = None

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def is_requested(self) -> bool:
        return self._reason is not None

    @property
    def reason(self) -> str | None:
        """Why the run was abandoned, in the operator's terms. `None` while the run is live."""
        return self._reason

    def request(self, reason: str) -> None:
        """Ask the run to stop at its next node boundary.

        Sync, and it must be: this is called from the place handling the operator's interruption, which
        cannot afford to await anything, and it does nothing but set a field. The first reason wins - a
        second request does not overwrite the first, because the first is the one that explains what
        actually stopped the run.
        """
        if self._reason is not None:
            logger.debug("run already abandoned; keeping the first reason", extra={"run_id": self._run_id})
            return
        self._reason = reason
        logger.info("run abandonment requested", extra={"run_id": self._run_id, "reason": reason})

    def raise_if_requested(self) -> None:
        """Stop here if the operator has asked. Raises `RunCancelledError`, never `CancelledError`.

        Deliberately a different exception from `asyncio.CancelledError`. `CancelledError` inherits from
        `BaseException` so that no `except Exception` swallows it - which also means it tears through the
        `finally` blocks that close artefacts and release the GPU lock. An abandonment is an ordinary,
        expected outcome of a run and is raised as an ordinary exception, so those blocks run.
        """
        if self._reason is not None:
            raise RunCancelledError(f"Run abandoned: {self._reason}", details={"runId": self._run_id})


# Bound for the lifetime of one graph invocation. `None` outside a run - a node reached with no signal
# bound is a node running outside a `run_handle`, which `raise_if_abandoned` treats as "nothing to check"
# rather than as an error, because that is exactly the situation in a unit test of a single node.
_current_signal: ContextVar[AbandonmentSignal | None] = ContextVar("aeris_abandonment_signal", default=None)


@contextmanager
def bound_signal(signal: AbandonmentSignal) -> Iterator[AbandonmentSignal]:
    """Make `signal` the one every node boundary inside this block checks."""
    token = _current_signal.set(signal)
    try:
        yield signal
    finally:
        _current_signal.reset(token)


def current_signal() -> AbandonmentSignal | None:
    """The signal for the run this code is executing inside, or `None` outside a run."""
    return _current_signal.get()


def raise_if_abandoned() -> None:
    """The node-boundary check. Called by `pipeline_node`, so a node body never has to remember it.

    Sync because it does no I/O, and because a sync function can be called from inside a `math/` kernel's
    progress loop later without dragging the event loop into it.
    """
    signal = _current_signal.get()
    if signal is not None:
        signal.raise_if_requested()
