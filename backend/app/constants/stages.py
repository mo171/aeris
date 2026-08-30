"""The twenty pipeline stage codes, and which of them leave an inspectable artefact behind.

what  : `PipelineStage`, an S1-S20 `StrEnum`, plus `ARTEFACT_PRODUCING_STAGES`.
where : Read by every trace step the graph emits, and by the provenance rules that decide what gets
        retained. Transcribed from `frontend/lib/constants/pipeline-stages.ts`.
how   : Codes only. The human-readable label for each stage lives in the frontend and nowhere here -
        `api-contract.md` §1 rule 4: the wire carries codes, the frontend carries copy. Sending
        "Specialist analysis" instead of `S13` would put display copy in two places, where it will disagree.

        `ARTEFACT_PRODUCING_STAGES` is the set the frontend marks `producesArtefact: true`. It matters
        because a trace step for one of these stages **must** carry an artefact URI (`api-contract.md` §1
        rule 10) - the operator can click it, and a missing URI is a dead end in the interface rather than a
        silent omission.
"""

from enum import StrEnum
from typing import Final


class PipelineStage(StrEnum):
    """One stage of the analysis pipeline, S1 through S20."""

    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"
    S5 = "S5"
    S6 = "S6"
    S7 = "S7"
    S8 = "S8"
    S9 = "S9"
    S10 = "S10"
    S11 = "S11"
    S12 = "S12"
    S13 = "S13"
    S14 = "S14"
    S15 = "S15"
    S16 = "S16"
    S17 = "S17"
    S18 = "S18"
    S19 = "S19"
    S20 = "S20"


# S7 cloud mask, S9 co-registration residual, S12 index map, S13 specialist output, S15 evidence assembly.
ARTEFACT_PRODUCING_STAGES: Final[frozenset[PipelineStage]] = frozenset(
    {
        PipelineStage.S7,
        PipelineStage.S9,
        PipelineStage.S12,
        PipelineStage.S13,
        PipelineStage.S15,
    }
)
