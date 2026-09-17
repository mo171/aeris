"""Names every event that crosses the stream, and records which of them nothing emits yet.

what  : `AnalysisEventType` and `AssistantEventType` - the `type` discriminators of the two stream unions
        the frontend parses - plus `EVENT_TYPES_NOT_YET_EMITTED`, the members agreed on but still owed.
where : Read by `app/schemas/events/`, by the CLI renderers that switch on a type, and by
        `tests/contracts/test_stream_events.py`, which compares these values against the frontend's union.
how   : `api-contract.md` §3 says these events are "exactly the objects the CLI prints and journals", which
        is what makes Phase 2 a transport swap rather than a rewrite. That only holds if the names match,
        and the frontend spells them as string literals inside a discriminated union rather than as an
        exported enum - so there is nothing for the 0.7 vocabulary test to pair them against automatically.
        The check is therefore direct: a test reads the union's discriminators out of the vendored contract
        and asserts these enums equal them.

        **`EVENT_TYPES_NOT_YET_EMITTED` is the same idea as `FRONTEND_ONLY_VOCABULARIES` in
        `constants/contracts.py`.** Events without a backend model are listed here with the phase that will
        supply one. The test that pairs this enum against the frontend union passes only because every gap
        is explicit, so the map is empty by earning it, not by default.
"""

from enum import StrEnum
from typing import Final


class AnalysisEventType(StrEnum):
    """The discriminator of the analysis stream - `POST /investigations/{id}/runs` in Phase 2."""

    RUN_START = "run-start"
    TRACE_STEP = "trace-step"
    LAYER_READY = "layer-ready"
    CLAIM = "claim"
    ANSWER_TOKEN = "answer-token"
    FIGURE_READY = "figure-ready"
    UI_COMMAND = "ui-command"
    SPEECH = "speech"
    RUN_COMPLETE = "run-complete"
    RUN_ERROR = "run-error"


class AssistantEventType(StrEnum):
    """The discriminator of the assistant stream - `POST /assistant/stream` in Phase 2.

    Deliberately a separate enum rather than a superset. The two streams share the *idea* of a trace step
    and differ in its shape: an analysis trace step carries a `stageCode` from S1-S20, an assistant one
    carries a free-text `label`. One enum over both would let a route emit an analysis-shaped step onto the
    assistant stream, which the frontend would reject at its schema boundary with no useful message.
    """

    MESSAGE_START = "message-start"
    TRACE_STEP = "trace-step"
    TOKEN = "token"
    MESSAGE_COMPLETE = "message-complete"
    STREAM_ERROR = "stream-error"
    UI_COMMAND = "ui-command"
    SPEECH = "speech"
    FIGURE_READY = "figure-ready"


# Events the frontend already parses that no backend subsystem can populate yet, each with the sub-phase
# that will. Not a to-do list: `tests/contracts/test_stream_events.py` fails if an entry here names an event
# the frontend does not define, or if an event is neither modelled nor listed.
#
# Empty since Phase 1.5, when `layer-ready` and `claim` gained the evidence subsystem that fills them. Kept
# as the seam rather than deleted: an event the frontend adds next lands here first, with a phase.
EVENT_TYPES_NOT_YET_EMITTED: Final[dict[AnalysisEventType, str]] = {}

# The mirror of the map above: events the **backend** emits that the **frontend** does not parse yet.
# An entry keeps backend-first additions explicit without weakening the exact vocabulary comparison. The
# staleness test requires removal as soon as the frontend parser ships.
EVENT_TYPES_NOT_YET_PARSED_BY_THE_FRONTEND: Final[dict[AnalysisEventType, str]] = {}
