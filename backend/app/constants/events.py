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
        `constants/contracts.py`.** Phase 1.0 can honestly produce five of the seven analysis events; the
        other two carry a layer and a claim, and no subsystem builds either yet. Declaring a model for them
        now would be a claim about the system that nothing verifies. Recording them here instead keeps the
        gap mechanical: the test that pairs this enum against the frontend union passes only because every
        member it cannot emit is listed, with the sub-phase that will.
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


# Events the frontend already parses that no backend subsystem can populate yet, each with the sub-phase
# that will. Not a to-do list: `tests/contracts/test_stream_events.py` fails if an entry here names an event
# the frontend does not define, or if an event is neither modelled nor listed.
EVENT_TYPES_NOT_YET_EMITTED: Final[dict[AnalysisEventType, str]] = {
    AnalysisEventType.LAYER_READY: (
        "Carries a layer and the evidence records drawn on it. Phase 1.5 builds evidence and Phase 1.2.1 "
        "builds layers; until one of them exists there is nothing to put in the payload."
    ),
    AnalysisEventType.CLAIM: (
        "Carries a validated claim object. Phase 1.5 - `evidence/` - is what produces one, and a claim "
        "model written before the subsystem that fills it would be a shape nothing verifies."
    ),
}
