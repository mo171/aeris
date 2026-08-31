"""Streams the written answer a word at a time, so the operator reads it as it is composed rather than after.

what  : `AnswerTokenEvent`.
where : Emitted by the answer-generation node from Phase 1.7 onwards. In 1.0 the probe graph emits a few so
        the renderer, the journal and the contract test all have a token path to exercise.
how   : "Tokens in word-sized chunks" (`api-contract.md` §3.1) - not per character, which floods the stream
        for no perceptible gain, and not per sentence, which is a paragraph appearing at once.

        There is deliberately no `index` or `isFinal` field: the frontend concatenates in arrival order and
        `run-complete` ends the sequence. Adding an index would invite a consumer to reorder, and a stream
        that can be reordered is one whose ordering nothing guarantees.
"""

from typing import Literal

from app.constants.events import AnalysisEventType
from app.schemas.events.base import StreamEvent


class AnswerTokenEvent(StreamEvent):
    """`answer-token`. One word-sized chunk of the written answer."""

    type: Literal[AnalysisEventType.ANSWER_TOKEN] = AnalysisEventType.ANSWER_TOKEN
    run_id: str
    text: str
