"""Which comparison an investigation workspace is set up to make.

what  : `WorkspaceMode`.
where : Stored on the investigation, read by the analysis router when it chooses a pipeline graph, and sent
        on the investigation detail response. Transcribed from the frontend's `workspaceModeSchema`.
how   : A mode, not a status - it says what the operator is comparing, not how far along they are, which is
        why it lives here rather than in `statuses.py`.

        Only two values, and deliberately so. The frontend collapsed the standalone Cross-Modal page into a
        *lens* over the investigation workspace rather than a separate surface, so cross-modal is a mode of
        one workspace instead of a different one. A third value would mean a third comparator binding on the
        frontend, which is a coordinated change, not a backend one.

        `CROSS_MODAL` is spelled `crossModal` on the wire - the alias generator does not touch enum
        *values*, only field names, so the camelCase here is written out rather than derived.
"""

from enum import StrEnum


class WorkspaceMode(StrEnum):
    """What the investigation workspace is comparing."""

    # Two observations of the same ground at different dates. The default.
    TEMPORAL = "temporal"

    # An optical and a radar observation, analysed independently and joined by late fusion (PDF §9, p.19).
    CROSS_MODAL = "crossModal"
