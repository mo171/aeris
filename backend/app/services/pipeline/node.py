"""Makes the execution trace and the stop-here check structural, instead of two things every node author must remember.

what  : `pipeline_node`, the decorator every stage function wears. It mints the step id, emits the step
        twice, times it, and checks abandonment on the way in and on the way out.
where : Applied in `services/pipeline/nodes/` (one stage each) and in `graphs/probe.py`. Nothing else
        wraps a node.
how   : Two obligations sit on every node, and both are the kind that get forgotten in the fourteenth one.

        **The trace is emitted twice.** `api-contract.md` §3.1: once `running`, then again terminal with
        `durationMs` - "that transition *is* the execution-trace UI, and it is the product's credibility
        signal". A stage that only appears once it has finished shows the operator a list of things that
        already happened; a stage that appears and then completes shows them a system working. Emitting
        both by hand means every node has the same six lines around its two lines of substance, and the
        one that forgets the second emission leaves a row spinning forever.

        **The step id is minted once and reused for both emissions**, because the frontend keys on it to
        replace the row rather than append a second one.

        **The boundary is where a run may stop** (`product-truth.md` §1.3). Checked before the node body
        and again after it: before, so an abandoned run does not start another stage; after, so a stage
        that did complete is recorded as completed and the run stops cleanly at the next edge with its
        checkpoint intact.

        **This is not `StepRunner`** - the protocol ADR-002 deleted, which owned retries, an executor, an
        event sink and a context object. This is `functools.wraps` around one async function. It chooses
        nothing, dispatches nothing, and retries nothing: a failure propagates, LangGraph records it, and
        the retry policy lives in Inngest from 2.5 where it can survive the process (ADR-001).

        **Timing is `perf_counter`, never wall time.** A duration measured across an NTP correction is how
        a stage comes to report a negative number of milliseconds.
"""

import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec

from app.constants.stages import PipelineStage
from app.constants.statuses import TraceStepState
from app.db.identifiers import IdentifierPrefix, new_identifier
from app.lib.exceptions import RunCancelledError
from app.schemas.events.trace import AnalysisTraceStep, TraceStepEvent
from app.services.pipeline.cancellation import raise_if_abandoned
from app.services.pipeline.state import PipelineState
from app.services.pipeline.stream import emit

logger = logging.getLogger(__name__)

Parameters = ParamSpec("Parameters")
NodeUpdate = dict[str, Any] | None


def pipeline_node(
    stage: PipelineStage,
    *,
    detail: str | None = None,
) -> Callable[[Callable[Parameters, Awaitable[NodeUpdate]]], Callable[Parameters, Awaitable[NodeUpdate]]]:
    """Wrap one stage function so it traces itself and stops when asked.

    `detail` is the line the operator reads beside the stage while it runs - "co-registering 2 scenes at
    10 m". It is a static string here because a node that wants a computed one emits its own updated step;
    most do not, and the alternative is every node building a `TraceStepEvent` to say one sentence.
    """

    def decorate(
        node_function: Callable[Parameters, Awaitable[NodeUpdate]],
    ) -> Callable[Parameters, Awaitable[NodeUpdate]]:
        @functools.wraps(node_function)
        async def traced_node(*args: Parameters.args, **kwargs: Parameters.kwargs) -> NodeUpdate:
            # Before anything else. An abandoned run must not start another stage, and raising here means
            # no trace step is emitted at all - the stage genuinely never ran, so it never appears.
            raise_if_abandoned()

            state = _state_from(args, kwargs)
            run_id = state["run_id"]
            step_id = new_identifier(IdentifierPrefix.TRACE_STEP)
            started_at = time.perf_counter()

            _emit_step(run_id, step_id, stage, TraceStepState.RUNNING, detail=detail, duration_ms=None)

            try:
                update = await node_function(*args, **kwargs)
            except RunCancelledError as error:
                # The operator stopped this stage from inside its body - a long node checking the signal in
                # its own loop. `FAILED` is used because the frontend's vocabulary has no `cancelled` state
                # for a step (`traceStepStateSchema`), and the two alternatives are worse: inventing a
                # value breaks the contract outright (api-contract.md §7), and `SKIPPED` would claim the
                # stage never ran. The detail says what actually happened. A `cancelled` member is a
                # reasonable thing to ask the frontend for; until it exists, this is the honest mapping.
                _emit_step(
                    run_id, step_id, stage, TraceStepState.FAILED,
                    detail=str(error), duration_ms=_elapsed_ms(started_at),
                )
                raise
            except Exception as error:
                _emit_step(
                    run_id, step_id, stage, TraceStepState.FAILED,
                    detail=str(error), duration_ms=_elapsed_ms(started_at),
                )
                logger.exception("pipeline stage failed", extra={"run_id": run_id, "stage": stage.value})
                raise

            _emit_step(
                run_id, step_id, stage, TraceStepState.COMPLETED,
                detail=detail, duration_ms=_elapsed_ms(started_at),
            )

            # After the terminal emission, so a stage that did complete is recorded as completed and the
            # run stops at the following edge rather than losing the work it just finished.
            raise_if_abandoned()

            return _with_trace_step_id(update, step_id)

        return traced_node

    return decorate


def _state_from(args: tuple[Any, ...], kwargs: dict[str, Any]) -> PipelineState:
    """The state LangGraph passed in, wherever it put it.

    LangGraph calls a node positionally, but a node may also declare `runtime` or `config` parameters, and
    a caller in a test may pass `state=` by keyword. Reading it defensively costs three lines and removes
    a whole class of `IndexError` that would otherwise surface as a node failing before it started.
    """
    if args and isinstance(args[0], dict):
        return args[0]
    state = kwargs.get("state")
    if isinstance(state, dict):
        return state
    raise TypeError(
        "A pipeline node's first argument must be the state dictionary. "
        f"Got {type(args[0]).__name__ if args else 'nothing'}."
    )


def _with_trace_step_id(update: NodeUpdate, step_id: str) -> NodeUpdate:
    """Record this stage in the state's trace, without the node having to.

    `trace_step_ids` uses an `add` reducer, so returning a one-element list appends rather than replaces
    even when two branches complete at once.

    A node that returns something other than a partial-state dictionary - a LangGraph `Command`, say - is
    rejected loudly rather than silently losing its trace entry. No node needs one today; the phase that
    first does will see this message instead of a trace with a hole in it.
    """
    if update is None:
        return {"trace_step_ids": [step_id]}
    if not isinstance(update, dict):
        raise TypeError(
            f"A @pipeline_node must return a partial state dictionary or None, got {type(update).__name__}. "
            "Routing with a Command is not supported by this decorator yet - see services/pipeline/node.py."
        )
    return {**update, "trace_step_ids": [*update.get("trace_step_ids", []), step_id]}


def _emit_step(
    run_id: str,
    step_id: str,
    stage: PipelineStage,
    state: TraceStepState,
    *,
    detail: str | None,
    duration_ms: int | None,
) -> None:
    """One trace-step emission. Private because a node emits through the decorator, never directly."""
    emit(
        TraceStepEvent(
            run_id=run_id,
            step=AnalysisTraceStep(
                id=step_id,
                stage_code=stage,
                state=state,
                detail=detail,
                duration_ms=duration_ms,
            ),
        )
    )


def _elapsed_ms(started_at: float) -> int:
    """Milliseconds since `started_at`, from a monotonic clock, never negative."""
    return max(0, round((time.perf_counter() - started_at) * 1000))
