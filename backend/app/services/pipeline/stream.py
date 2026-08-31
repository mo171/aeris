"""The one way a node speaks to the outside world, so that no node ever formats an event by hand.

what  : `emit()`, which writes one typed event into the LangGraph custom stream, plus `emit_answer_token()`
        for the one event a node sends in a tight loop.
where : Called from inside pipeline nodes only. Events emitted *around* a run - `run-start`,
        `run-complete`, `run-error` - come from `services/sessions/run_handle.py` instead, because a run
        that dies inside its first node still has to produce a terminal event and there is no node left to
        produce it from.
how   : **This is not an `EventSink`, and the difference matters** (ADR-002 deleted that protocol). There
        is no interface, no registry, no implementation to choose between. `get_stream_writer()` is
        LangGraph's own accessor for the writer belonging to the current run; this module adds the two
        things a caller would otherwise get wrong - the serialisation rule, and the type.

        **Typed in, `dict` out, once, here.** `serialise_event()` applies `by_alias=True` and
        `mode="json"`, either of which is one keyword away from being forgotten at a call site and both of
        which cause the frontend to reject the whole event (0.7 measured both). A node passes a model; the
        wire dictionary is produced in exactly one place.

        **`emit()` is sync.** LangGraph's writer is a sync callable - it appends to the run's stream queue
        and does no I/O - so making this a coroutine would add an await point in the middle of every node
        for nothing, and `code-standards.md` §7 asks for async where there is I/O, not everywhere.

        Calling this outside a node raises `RuntimeError` from LangGraph ("Called get_config outside of a
        runnable context"), and that is left to propagate rather than caught. An event emitted where
        nothing is listening is a bug in the caller, and swallowing it would produce a run whose trace is
        silently missing stages.
"""

from langgraph.config import get_stream_writer

from app.schemas.events.answer import AnswerTokenEvent
from app.schemas.events.base import StreamEvent, serialise_event


def emit(event: StreamEvent) -> None:
    """Write one event into the stream of the run this code is executing inside."""
    writer = get_stream_writer()
    writer(serialise_event(event))


def emit_answer_token(run_id: str, text: str) -> None:
    """Stream one word-sized chunk of the written answer.

    Given its own function because it is the one event emitted in a loop, and because a loop is where a
    caller is most likely to reach for a raw dictionary to save building a model. The model is cheap; the
    event that skips it is the one that reaches the frontend spelled `run_id`.
    """
    emit(AnswerTokenEvent(run_id=run_id, text=text))
