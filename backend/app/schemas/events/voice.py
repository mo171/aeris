"""The typed contract for one independently cancellable, evidence-bound spoken utterance.

what  : `SpeechEvent`, including provisional labelling and later supersession.
where : Emitted by the voice surface and carried on either frontend stream.
how   : Empty claim ids are allowed only for explicitly provisional speech. This is the wire-level honesty
        boundary that prevents an unsourced utterance from looking like a grounded result.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.constants.events import AnalysisEventType
from app.schemas.events.base import StreamEvent


class SpeechEvent(StreamEvent):
    """One spoken utterance and the evidence status the client must present with it."""

    type: Literal[AnalysisEventType.SPEECH] = AnalysisEventType.SPEECH
    run_id: str = Field(min_length=1)
    utterance_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    audio_url: str | None = Field(default=None, min_length=1)
    claim_ids: list[Annotated[str, Field(min_length=1)]]
    interruptible: bool = True
    provisional: bool = False
    supersedes_utterance_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_claim_binding(self) -> Self:
        """Keep provisional knowledge visibly distinct from claim-grounded speech."""
        if self.provisional and self.claim_ids:
            raise ValueError("provisional speech must have empty claim_ids")
        if not self.provisional and not self.claim_ids:
            raise ValueError("empty claim_ids require provisional=true")
        return self
