"""Gives every stream event one serialisation rule, so no producer has to remember the two that matter.

what  : `StreamEvent`, the base class of every event on every stream, and `serialise_event()`.
where : Inherited by `events/run.py`, `events/trace.py` and `events/answer.py`. Called by
        `services/pipeline/stream.py` on the way into the LangGraph stream, and by the journal writer.
how   : Two serialisation rules decide whether a payload is accepted or rejected wholesale, and both are
        one keyword argument away from being got wrong at every call site (0.7 proved this against the
        frontend's own schemas):

        - **`by_alias=True`** turns `next_cursor` into `nextCursor`. Without it the frontend's Zod rejects
          the entire event.
        - **`mode="json"`** turns a `datetime` into `2026-08-31T12:00:00Z`. The default returns a live
          `datetime` object, and `.isoformat()` returns `+00:00`, which the frontend's `z.iso.datetime()`
          rejects. Four characters, invisible on both sides.

        So no producer calls `model_dump` directly. `serialise_event()` is the only conversion, and
        `tests/contracts/test_stream_events.py` validates its output against the vendored union.

        `StreamEvent` carries no `type` field of its own. Each subclass declares it as a `Literal`, which
        is what makes the union discriminated on the Python side as well as on the wire - so a `match` over
        events narrows, and a missing branch is a type error rather than a silent fall-through.
"""

from typing import Any

from app.lib.responses import CamelCaseModel


class StreamEvent(CamelCaseModel):
    """Base class for every event the backend streams. Subclasses declare `type` as a `Literal`."""


def serialise_event(event: StreamEvent) -> dict[str, Any]:
    """The single conversion from an event model to the object that goes on the wire and into the journal.

    Sync, and correctly so (code-standards.md §7): it does no I/O and cannot plausibly do any later. It is
    also called from inside `get_stream_writer()`, whose writer is a sync callable.
    """
    return event.model_dump(by_alias=True, mode="json")
