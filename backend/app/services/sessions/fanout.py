"""Lets one run's event stream reach several readers at once, so nothing has to choose between the trace and the journal.

what  : `EventFanout`, which delivers every event to every registered consumer, and the `StreamConsumer`
        callable shape.
where : Built by `cli/run.py` with the trace renderer and the journal writer, and passed to
        `services/sessions/run_handle.py`. Phase 1.13 registers the speech synthesiser here too, and Phase
        2.3 registers the SSE encoder.
how   : `graph.astream()` is a single async iterator - iterating it twice is not possible, and the first
        consumer to read it consumes it. So something has to stand between one producer and many readers,
        and this is the smallest thing that does.

        **Sequential await, in registration order, not a queue per consumer.** Queues would buy the ability
        to survive a slow consumer, at the price of a bound, a drop policy, and a second failure mode where
        events are lost silently. The consumers here are a file append and a terminal draw - microseconds -
        against a producer whose steps are model inference measured in minutes. There is nothing to buffer.
        The phase that adds a genuinely slow consumer (network delivery, in 2.3) is the phase to revisit
        this, and it will have a reason rather than an anticipation.

        **Order is the contract, so the journal is registered first.** The journal is provenance; the trace
        renderer is decoration. If the process dies between two consumers, the journal is the one that has
        to already have the event.

        **A consumer that raises is detached, never fatal.** A terminal renderer failing on a resized
        window must not lose an analysis that took ten minutes. The failure is logged with the consumer's
        name and that consumer stops receiving events; the run continues. The inverse - letting a renderer
        kill a run - is the more expensive mistake by a wide margin.
"""

import logging
from collections.abc import Awaitable, Callable

from app.schemas.events import AnalysisStreamEvent

logger = logging.getLogger(__name__)

# A consumer is a plain async callable, deliberately not a protocol. `folder-archtecture.md`: "Consumers of
# the LangGraph stream. Not a protocol - just consumers." ADR-002 deleted `EventSink`, which abstracted over
# *how events get out*; LangGraph owns that now. This abstracts nothing - it is the type of a function.
type StreamConsumer = Callable[[AnalysisStreamEvent], Awaitable[None]]


class EventFanout:
    """Delivers each event to every consumer, in order, surviving any one of them failing."""

    def __init__(self) -> None:
        self._consumers: dict[str, StreamConsumer] = {}

    def register(self, name: str, consumer: StreamConsumer) -> None:
        """Add a consumer under a name that will appear in the log if it fails.

        Named rather than anonymous because the only thing worse than a renderer that breaks is a log line
        saying that *a* consumer broke. Sync: it mutates a dictionary.
        """
        if name in self._consumers:
            raise ValueError(f"A consumer named {name!r} is already registered on this fan-out.")
        self._consumers[name] = consumer

    @property
    def consumer_names(self) -> tuple[str, ...]:
        """Who is currently receiving events, in delivery order. Shrinks when a consumer is detached."""
        return tuple(self._consumers)

    async def publish(self, event: AnalysisStreamEvent) -> None:
        """Deliver one event to every consumer, in registration order."""
        for name, consumer in list(self._consumers.items()):
            try:
                await consumer(event)
            except Exception:
                # Detached rather than retried. A consumer that failed once on this event will fail on the
                # next one, and a run whose every event logs a traceback is unreadable.
                del self._consumers[name]
                logger.exception(
                    "stream consumer failed and was detached; the run continues",
                    extra={"consumer": name, "event_type": event.type},
                )
