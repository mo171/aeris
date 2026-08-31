"""Opens and closes a run on the wire, including the two ways a run can end without having failed.

what  : `RunStartEvent`, `RunCompleteEvent`, `RunErrorEvent`, and the `InsufficientEvidence` payload the
        completion carries when AERIS declines to answer.
where : Emitted by `services/sessions/run_handle.py` around the graph invocation - deliberately outside the
        graph, because a run that dies inside its first node still has to emit a terminal event.
how   : Three rules here are contract rather than preference, and each one has a specific wrong answer
        attached to breaking it.

        **`confidence` is `float | None` and never `0.0`** (`api-contract.md` §1 rule 2). Zero is the claim
        "no confidence"; `None` is "no claim". The frontend renders the second as an explicit refusal card
        and the first as a very bad result.

        **Insufficient evidence is a `run-complete`, not a `run-error`** (rule 7, PDF p.38). A system that
        reports "I cannot answer this from these two scenes, here is what would let me" has succeeded at
        the thing it is for. Routing it through the error path would show an operator an incident.

        **`run-error` carries only a message.** There is no code field on the frontend's schema, so a
        cancellation is distinguished by what the message says. `RunErrorEvent.cancelled()` exists so that
        the wording is written once instead of at each of the places that can abandon a run.
"""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field

from app.constants.events import AnalysisEventType
from app.constants.intents import Intent
from app.schemas.events.base import StreamEvent


class InsufficientEvidenceRemedy(StreamEvent):
    """One thing the operator could do that would let AERIS answer. Rendered as an actionable button."""

    id: str
    label: str
    prompt: str


class InsufficientEvidence(StreamEvent):
    """Why AERIS declined, and what would change that.

    `remedies` may be empty, and an empty list is a real answer - "nothing you can do with this input" -
    rather than a missing one. It is still required on the wire, because the frontend distinguishes an
    empty remedy list from an absent one when deciding whether to render the panel at all.
    """

    reason: str
    remedies: list[InsufficientEvidenceRemedy] = Field(default_factory=list)


class RunStartEvent(StreamEvent):
    """`run-start`. The first event of every run, emitted before the graph is invoked."""

    type: Literal[AnalysisEventType.RUN_START] = AnalysisEventType.RUN_START
    run_id: str
    intent: Intent
    started_at: datetime


class RunCompleteEvent(StreamEvent):
    """`run-complete`. The successful terminal event, including the successful refusal."""

    type: Literal[AnalysisEventType.RUN_COMPLETE] = AnalysisEventType.RUN_COMPLETE
    run_id: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    insufficient_evidence: InsufficientEvidence | None = None
    total_duration_ms: int = Field(ge=0)


class RunErrorEvent(StreamEvent):
    """`run-error`. The unsuccessful terminal event - a failure, or an abandonment the operator asked for."""

    type: Literal[AnalysisEventType.RUN_ERROR] = AnalysisEventType.RUN_ERROR
    run_id: str
    message: str

    @classmethod
    def cancelled(cls, run_id: str, reason: str) -> Self:
        """The terminal event of a run the operator abandoned.

        Worded once, here, rather than at each place that can abandon a run, because the operator reads this
        string and "Cancelled" alone does not say who cancelled it or why. `RunStatus.CANCELLED` - not
        `FAILED` - is what the run is recorded as; an intentional stop is never shown as an incident
        (`app/lib/exceptions.py`, `RunCancelledError`).
        """
        return cls(run_id=run_id, message=f"Run abandoned: {reason}")
