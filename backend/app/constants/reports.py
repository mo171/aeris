"""The eight sections of a report, and the order they are streamed in.

what  : `ReportSection` and `REPORT_SECTION_ORDER`.
where : Read by the report stream (`GET /investigations/{id}/report`), which emits one `report-section` event
        per section, and by the PDF export. Transcribed from the frontend's report schema.
how   : The order is a constant here rather than an assumption in the renderer, because two surfaces consume
        it - the streamed panel and the PDF - and they must agree.

        The order is also an argument. `LIMITATIONS` comes after `CONFIDENCE` and before `CONCLUSION`, so a
        reader reaches what the analysis could not establish before reaching what it concluded. A report that
        buries its limitations after the conclusion is a report that has been written to persuade.
"""

from enum import StrEnum
from typing import Final


class ReportSection(StrEnum):
    """One section of a generated report."""

    SUMMARY = "summary"
    INPUTS = "inputs"
    FINDINGS = "findings"
    EVIDENCE = "evidence"
    MODELS = "models"
    CONFIDENCE = "confidence"
    LIMITATIONS = "limitations"
    CONCLUSION = "conclusion"


REPORT_SECTION_ORDER: Final[tuple[ReportSection, ...]] = (
    ReportSection.SUMMARY,
    ReportSection.INPUTS,
    ReportSection.FINDINGS,
    ReportSection.EVIDENCE,
    ReportSection.MODELS,
    ReportSection.CONFIDENCE,
    ReportSection.LIMITATIONS,
    ReportSection.CONCLUSION,
)
