"""The analysis stream union, as one discriminated type the renderers can exhaustively match on.

what  : `AnalysisStreamEvent` - the tagged union of every event Phase 1 can emit - and `parse_event()`,
        which reads one back from a journal line.
where : Imported by `services/pipeline/stream.py`, by both CLI renderers, and by Phase 2's SSE encoder.
how   : A `Field(discriminator="type")` union rather than a base class and `isinstance` checks. Pydantic
        then dispatches on the `type` string alone, so parsing a journal line back into the right model is
        one call and an unknown `type` is a validation error naming the field - which is what replay needs
        in order to fail on a journal written by a newer backend rather than silently drop the line.

        **Five of the seven analysis events, not seven.** `layer-ready` and `claim` carry payloads no
        subsystem builds yet, and are recorded in `constants/events.py` with the sub-phase that will build
        them. `tests/contracts/test_stream_events.py` fails if that list stops matching what is modelled
        here, so the union grows by decision rather than by drift.
"""

from typing import Annotated

from pydantic import Field, TypeAdapter

from app.schemas.events.answer import AnswerTokenEvent
from app.schemas.events.base import StreamEvent, serialise_event
from app.schemas.events.run import (
    InsufficientEvidence,
    InsufficientEvidenceRemedy,
    RunCompleteEvent,
    RunErrorEvent,
    RunStartEvent,
)
from app.schemas.events.trace import AnalysisTraceStep, TraceStepEvent

type AnalysisStreamEvent = Annotated[
    RunStartEvent | TraceStepEvent | AnswerTokenEvent | RunCompleteEvent | RunErrorEvent,
    Field(discriminator="type"),
]

# Built once at import. A `TypeAdapter` compiles its validator on construction, and replay parses one line
# per event - rebuilding the adapter per line is the difference between reading a journal and recompiling a
# schema a few thousand times.
ANALYSIS_STREAM_EVENT_ADAPTER: TypeAdapter[AnalysisStreamEvent] = TypeAdapter(AnalysisStreamEvent)

# The events that end a run, whatever the outcome. A consumer holding one of these knows nothing more is
# coming; naming the set here means a renderer does not decide that for itself.
TERMINAL_EVENT_TYPES: frozenset[type[StreamEvent]] = frozenset({RunCompleteEvent, RunErrorEvent})


def parse_event(payload: dict[str, object]) -> AnalysisStreamEvent:
    """Read one journalled event back into its model.

    Sync: it is called from a loop over file lines and does no I/O of its own. Raises
    `pydantic.ValidationError` on an unknown `type` or a malformed payload, which is the behaviour replay
    wants - a journal it cannot fully understand must not be replayed as though it were understood.
    """
    return ANALYSIS_STREAM_EVENT_ADAPTER.validate_python(payload)


__all__ = [
    "ANALYSIS_STREAM_EVENT_ADAPTER",
    "TERMINAL_EVENT_TYPES",
    "AnalysisStreamEvent",
    "AnalysisTraceStep",
    "AnswerTokenEvent",
    "InsufficientEvidence",
    "InsufficientEvidenceRemedy",
    "RunCompleteEvent",
    "RunErrorEvent",
    "RunStartEvent",
    "StreamEvent",
    "TraceStepEvent",
    "parse_event",
    "serialise_event",
]
