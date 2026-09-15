"""The presentation-only command proposal shared by AERIS stream consumers.

what  : `UiCommandEvent`, a command id, untrusted parameters, and the agent-authored reason for proposing it.
where : Emitted after evidence-bound interface selection and independently validated by the frontend bus.
how   : The payload deliberately remains generic here. Command-specific validation belongs to the mounted
        frontend registry, so this contract cannot drift into a second command implementation.
"""

from typing import Any, Literal

from pydantic import Field

from app.constants.events import AnalysisEventType
from app.schemas.events.base import StreamEvent


class UiCommandEvent(StreamEvent):
    """One non-authoritative request to change the presentation of known evidence."""

    type: Literal[AnalysisEventType.UI_COMMAND] = AnalysisEventType.UI_COMMAND
    run_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    params: dict[str, Any]
    reason: str = Field(min_length=1)
