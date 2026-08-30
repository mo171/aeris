"""The nine things an operator can be asking for. The router's entire output vocabulary.

what  : `Intent`, the classification S3 produces from a natural-language question.
where : Read by the router, and by the conditional edges that decide which specialist path a run takes.
        Transcribed from the frontend's investigation schema.
how   : Nine and only nine. A tenth intent is a change to the graph's topology and to the frontend's schema
        at the same time, so it is a coordinated change rather than a new enum member.

        `EVIDENCE_RECALL` is the one that does not run a model: it answers from evidence already produced in
        this investigation. Keeping it in the same vocabulary is deliberate - "what did you find in the
        north-east earlier" is a question the operator asks in the same sentence shape as the others, and
        routing it separately would mean classifying twice.
"""

from enum import StrEnum


class Intent(StrEnum):
    """What the operator's question is asking the system to do."""

    SCENE_VQA = "SCENE_VQA"
    GROUND = "GROUND"
    INDEX_QUERY = "INDEX_QUERY"
    DETECT = "DETECT"
    SEGMENT = "SEGMENT"
    CHANGE_DETECT = "CHANGE_DETECT"
    CHANGE_VQA = "CHANGE_VQA"
    CROSS_MODAL = "CROSS_MODAL"
    EVIDENCE_RECALL = "EVIDENCE_RECALL"
