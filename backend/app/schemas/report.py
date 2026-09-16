"""Defines the factual dossier and reader-facing narrative shared by every report surface.

what  : Typed report content, evidence explanations, model rationale, and the transport section projection.
where : Built by `services/reports/generator.py`; consumed by PDF, Markdown, voice, and future API adapters.
how   : Internal references remain separate from reader prose so renderers cannot accidentally print them.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.constants.reports import ReportSection
from app.lib.responses import CamelCaseModel


class QuestionAnswer(CamelCaseModel):
    question: str
    answer: str


class KeyFact(CamelCaseModel):
    label: str
    value: str
    interpretation: str


class EvidenceNarrative(CamelCaseModel):
    figure_id: str
    title: str
    what_it_shows: str
    what_it_supports: str
    why_it_is_credible: str


class EditorialEvidenceNarrative(BaseModel):
    figure_index: int = Field(ge=0)
    title: str = Field(min_length=5, max_length=70)
    what_it_shows: str
    what_it_supports: str
    why_it_is_credible: str


class ModelNarrative(CamelCaseModel):
    name: str
    version: str
    what_was_analysed: str
    why_it_was_used: str
    contribution: str


class ReportSectionDocument(CamelCaseModel):
    id: str
    kind: ReportSection
    heading: str
    body: str
    layer_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)


class ReportFinding(CamelCaseModel):
    text: str
    is_primary: bool = False
    confidence: float | None = None


class ReportFigure(CamelCaseModel):
    id: str
    title: str
    caption: str
    claim_ids: list[str] = Field(default_factory=list)
    is_primary: bool = False


class EditorialReportDraft(BaseModel):
    """The only prose shape the language model may return."""

    title: str = Field(min_length=8, max_length=110)
    subtitle: str = Field(min_length=8, max_length=160)
    objective: str = Field(min_length=20, max_length=700)
    executive_summary: str = Field(min_length=30, max_length=1_100)
    questions_and_answers: list[QuestionAnswer]
    key_facts: list[KeyFact]
    evidence_narratives: list[EditorialEvidenceNarrative]
    model_narratives: list[ModelNarrative]
    limitations: str = Field(min_length=15, max_length=1_200)
    final_summary: str = Field(min_length=20, max_length=1_000)
    voice_narration: str = Field(min_length=10, max_length=700)


class ReportDocument(CamelCaseModel):
    id: str
    investigation_id: str
    trace_id: str
    title: str
    subtitle: str
    question: str
    objective: str
    executive_summary: str
    generated_at: datetime
    questions_and_answers: list[QuestionAnswer] = Field(default_factory=list)
    key_facts: list[KeyFact] = Field(default_factory=list)
    findings: list[ReportFinding] = Field(default_factory=list)
    figures: list[ReportFigure] = Field(default_factory=list)
    evidence_narratives: list[EvidenceNarrative] = Field(default_factory=list)
    model_narratives: list[ModelNarrative] = Field(default_factory=list)
    limitations: str
    final_summary: str
    voice_narration: str
    is_evidence_limited: bool = False
    sections: list[ReportSectionDocument] = Field(default_factory=list)

    @property
    def report_id(self) -> str:
        """Canonical report handle used by interface-control; the wire field remains ``id``."""
        return self.id

    def reader_text(self) -> str:
        """Return only presentation prose, intentionally excluding internal reference fields."""
        parts = [self.title, self.subtitle, self.question, self.objective, self.executive_summary]
        parts.extend(item.question + " " + item.answer for item in self.questions_and_answers)
        parts.extend(item.label + " " + item.value + " " + item.interpretation for item in self.key_facts)
        parts.extend(item.text for item in self.findings)
        parts.extend(
            item.title + " " + item.what_it_shows + " " + item.what_it_supports + " " + item.why_it_is_credible
            for item in self.evidence_narratives
        )
        parts.extend(
            item.name + " " + item.version + " " + item.what_was_analysed + " " + item.why_it_was_used + " " + item.contribution
            for item in self.model_narratives
        )
        return " ".join(parts + [self.limitations, self.final_summary, self.voice_narration])
