"""The typed contract for one independently cancellable, evidence-bound spoken utterance.

what  : `SpeechEvent` and `SpeechKind`, including truth source, provisional labelling and supersession.
where : Emitted by the voice surface and carried on either frontend stream.
how   : The category says whether speech is a result, provisional knowledge, progress, or a refusal.
        `provisional` must agree with that category; claim and interruption rules then prevent a
        non-result from masquerading as a grounded result.
"""

from enum import StrEnum
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from app.constants.events import AnalysisEventType
from app.schemas.events.base import StreamEvent


class SpeechKind(StrEnum):
    """The evidence source and presentation policy of one utterance."""

    GROUNDED = "grounded"
    PROVISIONAL = "provisional"
    PROGRESS = "progress"
    REFUSAL = "refusal"


class SpeechEvent(StreamEvent):
    """One spoken utterance and the evidence status the client must present with it."""

    type: Literal[AnalysisEventType.SPEECH] = AnalysisEventType.SPEECH
    run_id: str = Field(min_length=1)
    utterance_id: str = Field(min_length=1)
    kind: SpeechKind
    text: str = Field(min_length=1)
    audio_url: str | None = Field(default=None, min_length=1)
    claim_ids: list[Annotated[str, Field(min_length=1)]]
    interruptible: bool = True
    provisional: bool = False
    supersedes_utterance_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_claim_binding(self) -> Self:
        """Keep truth source, grounding, interruption, and audio location mutually consistent."""
        is_provisional = self.kind is SpeechKind.PROVISIONAL
        if self.provisional != is_provisional:
            raise ValueError("provisional must be true exactly when kind is provisional")
        if self.kind is SpeechKind.GROUNDED and not self.claim_ids:
            raise ValueError("grounded speech requires non-empty claim_ids")
        if is_provisional and self.claim_ids:
            raise ValueError("provisional speech must have empty claim_ids")
        if self.kind is SpeechKind.REFUSAL and self.interruptible:
            raise ValueError("refusal speech must be non-interruptible")

        if self.audio_url is not None:
            parsed = urlsplit(self.audio_url)
            is_root_relative = self.audio_url.startswith("/") and not self.audio_url.startswith("//")
            is_http_url = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
            if any(character.isspace() for character in self.audio_url) or not (
                is_root_relative or is_http_url
            ):
                raise ValueError("audio_url must be an absolute HTTP(S) URL or a root-relative path")
        return self
