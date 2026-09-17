"""Proves Phase 1.12 produces a reader-first report without weakening evidence boundaries.

what  : Tests the report dossier, editorial guard, Markdown, voice preparation, and PDF page contract.
where : The focused Phase 1.12 gate. Real-run visual verification remains an integration acceptance step.
how   : Uses small wire-shaped facts and deliberately unsafe editorial drafts; no model or storage is needed.
"""

from datetime import UTC, datetime
from io import BytesIO
from typing import Any

import pytest
from pypdf import PdfReader

from app.schemas.report import EditorialReportDraft, EvidenceNarrative, KeyFact, QuestionAnswer
from app.services.reports.generator import ReportEditorialUnavailable, apply_editorial_draft, build_report
from app.services.reports.markdown import render_chat_markdown
from app.services.reports.pdf.renderer import render_pdf
from app.services.reports.voice import render_voice_narration


def _values(*, refused: bool = False) -> dict[str, object]:
    primary = (
        "A fused classification cannot be asserted because 1 material cross-sensor conflict requires another observation."
        if refused else "Built-up land covers 12.3 hectares of the observed area."
    )
    return {
        "query": "Use optical and SAR together to identify built-up and water-covered regions",
        "confidence": None if refused else 0.86,
        "claims": [
            {"id": "clm_primary", "text": primary, "isPrimary": True, "confidence": None if refused else 0.86,
             "metrics": [{"label": "Area" if not refused else "Conflicts", "value": 12.3 if not refused else 1.0,
                          "unit": "ha" if not refused else "", "precision": 1 if not refused else 0}]},
            {"id": "clm_support", "text": "Surface water covers 4.8 hectares of S2B_TEST.",
             "isPrimary": False, "confidence": 0.8,
             "metrics": [{"label": "Water area", "value": 4.8, "unit": "ha", "precision": 1}]},
        ],
        "input_records": [
            {"sceneId": "S2B_TEST", "modality": "optical", "processingLevel": "L2A",
             "resolutionMetres": 10.0, "crs": "EPSG:32643"},
            {"sceneId": "S1_TEST", "modality": "sar", "processingLevel": "GRD",
             "resolutionMetres": 10.0, "crs": "EPSG:32643"},
        ],
        "evidence_items": [{"id": "ev_1"}, {"id": "ev_2"}], "layers": [{"id": "lyr_1"}],
        "stage_models": [
            {"modelId": "index-engine", "modelVersion": "1.4.0"},
            {"modelId": "sar-preprocess", "modelVersion": "1.3.0"},
            {"modelId": "optical-sar-fusion", "modelVersion": "1.11.0"},
        ],
        "cross_modal_result": {"verdict": {"blockedByConflict": refused}},
    }


def _figures() -> list[dict[str, object]]:
    return [{"figureId": "fig_internal_01", "title": "Optical Built-up - S2B_TEST",
             "caption": "Built-up evidence derived from the optical observation.",
             "claimIds": ["clm_primary"], "isPrimary": True}]


async def test_report_has_the_required_research_content_model() -> None:
    report = await build_report(
        run_id="run_test", values=_values(), figure_events=_figures(),
        generated_at=datetime(2026, 9, 14, tzinfo=UTC), use_language_model=False,
    )
    assert report.objective and report.executive_summary
    assert [(item.question, item.answer) for item in report.questions_and_answers] == [
        ("Use optical and SAR together to identify built-up and water-covered regions?",
         "Built-up land covers 12.3 hectares of the observed area."),
    ]
    assert report.key_facts and report.key_facts[0].interpretation
    assert report.evidence_narratives == [EvidenceNarrative(
        figure_id="fig_internal_01", title="Optical evidence for built-up land",
        what_it_shows="The optical analysis maps the pixels identified as built-up land in the supplied observation.",
        what_it_supports="It provides the mapped spatial evidence behind the principal finding.",
        why_it_is_credible="The figure is rendered from retained analysis output and is linked to a validated claim.",
    )]
    assert all(item.what_was_analysed and item.why_it_was_used for item in report.model_narratives)
    assert report.final_summary
    reader_text = report.reader_text()
    assert "run_test" not in reader_text and "fig_internal_01" not in reader_text and "S2B_TEST" not in reader_text


async def test_unsafe_editorial_draft_is_rejected_as_a_whole() -> None:
    report = await build_report(run_id="run_test", values=_values(), figure_events=_figures(), use_language_model=False)
    unsafe = EditorialReportDraft(
        title="Analysis run_test", subtitle="An unsupported certainty claim", objective="Prove 99.9 hectares are developed.",
        executive_summary="Everything is certain and no qualification applies.", questions_and_answers=[], key_facts=[], evidence_narratives=[],
        model_narratives=[], limitations="No limitations.", final_summary="Everything is certain.",
        voice_narration="Everything is certain.",
    )
    assert await apply_editorial_draft(report, unsafe) == report


async def test_audit_style_editorial_draft_is_accepted_with_soft_guarding() -> None:
    report = await build_report(run_id="run_test", values=_values(refused=True), figure_events=_figures(), use_language_model=False)
    audit_style = EditorialReportDraft(
        title="Built-Up And Water Mapping",
        subtitle="Independent optical and radar evidence with spatial cross-comparison.",
        objective="The supplied observations were analysed independently before the report compares their evidence.",
        executive_summary="The supplied optical and radar observations were analysed independently. The report compares those sensor-specific results, and the final page records the boundary on a combined conclusion.",
        questions_and_answers=[QuestionAnswer(question="Use optical and SAR together to identify built-up and water-covered regions?", answer="The report compares the sensor-specific outputs.")],
        key_facts=[KeyFact(label="Mapped evidence", value="Surface water covers 4.8 hectares of the optical observation.", interpretation="This is a validated supporting measurement.")],
        evidence_narratives=[
            {
                "figure_index": 0,
                "title": "Optical Built-Up Map",
                "what_it_shows": "The figure shows the optical branch's mapped built-up evidence.",
                "what_it_supports": "It supports the mapped optical contribution to the fusion review.",
                "why_it_is_credible": "It is linked to a retained validated claim.",
            }
        ],
        model_narratives=report.model_narratives,
        limitations="A fused classification cannot be asserted because 1 material cross-sensor conflict requires another observation.",
        final_summary="A fused classification cannot be asserted because 1 material cross-sensor conflict requires another observation.",
        voice_narration="We analysed the supplied observations and the report compares them.",
    )

    edited = await apply_editorial_draft(report, audit_style)
    assert edited.executive_summary == audit_style.executive_summary
    assert edited.voice_narration == audit_style.voice_narration


async def test_evidence_limited_body_may_keep_ai_refusal_language_with_soft_guarding() -> None:
    report = await build_report(run_id="run_test", values=_values(refused=True), figure_events=_figures(), use_language_model=False)
    body_refusal = EditorialReportDraft(
        title="Built-Up And Water Mapping",
        subtitle="AERIS maps the requested evidence with conflict review.",
        objective="AERIS maps built-up land and water from the supplied observations.",
        executive_summary="AERIS mapped both requested classes but cannot produce a fused conclusion because the conflict requires a third observation.",
        questions_and_answers=[QuestionAnswer(question="Use optical and SAR together to identify built-up and water-covered regions?", answer="AERIS cannot produce a fused conclusion.")],
        key_facts=[KeyFact(label="Mapped evidence", value="Surface water covers 4.8 hectares of the optical observation.", interpretation="This is a validated supporting measurement.")],
        evidence_narratives=[
            {
                "figure_index": 0,
                "title": "Optical Built-Up Map",
                "what_it_shows": "The figure shows the optical branch's mapped built-up evidence.",
                "what_it_supports": "It supports the mapped optical contribution to the fusion review.",
                "why_it_is_credible": "It is linked to a retained validated claim.",
            }
        ],
        model_narratives=report.model_narratives,
        limitations="A fused classification cannot be asserted because 1 material cross-sensor conflict requires another observation.",
        final_summary="A fused classification cannot be asserted because 1 material cross-sensor conflict requires another observation.",
        voice_narration="AERIS retained one unresolved conflict while reporting the mapped evidence.",
    )

    edited = await apply_editorial_draft(report, body_refusal)
    assert edited.executive_summary == body_refusal.executive_summary
    assert edited.questions_and_answers == body_refusal.questions_and_answers


async def test_editorial_draft_can_use_unlisted_context_as_soft_editorial_prose() -> None:
    report = await build_report(run_id="run_test", values=_values(), figure_events=_figures(), use_language_model=False)
    invented_context = EditorialReportDraft(
        title="Basketball Court Mapping",
        subtitle="AERIS evidence narrative for the supplied observation.",
        objective="AERIS maps the requested objects in the supplied observation.",
        executive_summary="AERIS mapped the requested objects and retained a synthesis map showing cross-sensor agreement.",
        questions_and_answers=[QuestionAnswer(question="Count the basketball courts?", answer="AERIS found the requested objects and retained a synthesis map.")],
        key_facts=[KeyFact(label="Built-up extent", value="Built-up land covers 12.3 hectares of the observed area.", interpretation="This is the retained validated area measurement.")],
        evidence_narratives=[
            {
                "figure_index": 0,
                "title": "Object Detection Map",
                "what_it_shows": "The figure shows the mapped detections.",
                "what_it_supports": "It supports the reported count.",
                "why_it_is_credible": "It is linked to a retained validated claim.",
            }
        ],
        model_narratives=report.model_narratives,
        limitations="The assessment is bounded by the supplied imagery and retained evidence.",
        final_summary="AERIS reports the retained evidence.",
        voice_narration="AERIS retained a synthesis map showing cross-sensor agreement.",
    )

    edited = await apply_editorial_draft(report, invented_context)
    assert "cross-sensor agreement" in edited.voice_narration
    assert "synthesis map" in edited.executive_summary


async def test_evidence_limited_reports_still_use_ai_authored_body_prose() -> None:
    report = await build_report(run_id="run_test", values=_values(refused=True), figure_events=_figures(), use_language_model=False)
    draft = EditorialReportDraft(
        title="Built-Up And Water Mapping",
        subtitle="AERIS fused optical and radar evidence with explicit conflict review.",
        objective="Use AERIS optical and radar analysis to map built-up land and surface water, then retain any unresolved sensor disagreement for review.",
        executive_summary=(
            "AERIS analysed the supplied optical and radar observations for built-up land and surface water, then joined the "
            "spatial evidence into a reviewable fusion ledger. The report gives the validated sensor measurements first, "
            "then separates corroborated and conflicting locations so the useful map evidence remains visible."
        ),
        questions_and_answers=[
            QuestionAnswer(
                question="Use optical and SAR together to identify built-up and water-covered regions?",
                answer="AERIS mapped the requested land-cover evidence from both sensors and retained one unresolved cross-sensor conflict for final review.",
            )
        ],
        key_facts=[
            KeyFact(label="Mapped evidence", value="Surface water covers 4.8 hectares of the optical observation.", interpretation="This is a validated supporting measurement."),
        ],
        evidence_narratives=[
            {
                "figure_index": 0,
                "title": "Optical Built-Up Map",
                "what_it_shows": "The figure shows the optical branch's mapped built-up evidence.",
                "what_it_supports": "It supports the mapped optical contribution to the fusion review.",
                "why_it_is_credible": "It is linked to a retained validated claim.",
            }
        ],
        model_narratives=report.model_narratives,
        limitations="A fused classification cannot be asserted because 1 material cross-sensor conflict requires another observation.",
        final_summary="A fused classification cannot be asserted because 1 material cross-sensor conflict requires another observation.",
        voice_narration="AERIS mapped the available evidence, with one cross-sensor conflict retained as evidence-limited.",
    )

    edited = await apply_editorial_draft(report, draft)

    assert edited.executive_summary == draft.executive_summary
    assert edited.objective == draft.objective
    assert edited.questions_and_answers == draft.questions_and_answers
    assert edited.limitations == draft.limitations
    assert edited.final_summary == draft.final_summary


async def test_build_report_uses_the_editorial_model_when_available(monkeypatch) -> None:
    class FakeEditorialModel:
        def with_structured_output(self, _schema: type[EditorialReportDraft]) -> "FakeEditorialModel":
            return self

        async def ainvoke(self, _prompt: str) -> EditorialReportDraft:
            return EditorialReportDraft(
                title="AERIS Built-Up Mapping",
                subtitle="AI-authored evidence narrative for the retained observations.",
                objective="AERIS assesses the supplied observations and reports the validated land-cover evidence.",
                executive_summary=(
                    "AERIS identified built-up land across the observed area and retained the supporting evidence in the report. "
                    "The answer is written from the validated measurement record rather than from file names or backend identifiers."
                ),
                questions_and_answers=[
                    QuestionAnswer(question="Use optical and SAR together to identify built-up and water-covered regions?", answer="Built-up land covers 12.3 hectares of the observed area.")
                ],
                key_facts=[
                    KeyFact(label="Built-up extent", value="Built-up land covers 12.3 hectares of the observed area.", interpretation="This is the retained validated area measurement.")
                ],
                evidence_narratives=[
                    {
                        "figure_index": 0,
                        "title": "Optical Built-Up Map",
                        "what_it_shows": "The figure shows the mapped built-up evidence.",
                        "what_it_supports": "It supports the reported built-up area.",
                        "why_it_is_credible": "It is linked to a retained validated claim.",
                    }
                ],
                model_narratives=[
                    {
                        "name": "Spectral-index analysis",
                        "version": "1.4.0",
                        "what_was_analysed": "The supplied optical observation.",
                        "why_it_was_used": "It provides deterministic land-cover evidence.",
                        "contribution": "It produced the validated built-up measurement.",
                    }
                ],
                limitations="The assessment is bounded by the supplied imagery and retained evidence.",
                final_summary="AERIS reports 12.3 hectares of built-up land from the retained evidence.",
                voice_narration="AERIS reports 12.3 hectares of built-up land from the retained evidence.",
            )

    def fake_build_chat_model() -> Any:
        return FakeEditorialModel()

    monkeypatch.setattr("app.lib.llm.chat_model.build_chat_model", fake_build_chat_model)

    report = await build_report(run_id="run_test", values=_values(), figure_events=_figures(), use_language_model=True)

    assert report.executive_summary.startswith("AERIS identified built-up land")
    assert report.objective.startswith("AERIS assesses")
    assert report.title == "AERIS Built-Up Mapping"


async def test_product_report_generation_fails_instead_of_publishing_fallback(monkeypatch) -> None:
    monkeypatch.setattr("app.lib.llm.chat_model.build_chat_model", lambda: None)

    with pytest.raises(ReportEditorialUnavailable):
        await build_report(run_id="run_test", values=_values(), figure_events=_figures(), use_language_model=True)


async def test_provider_failure_retries_ai_once_before_failing_without_fallback(monkeypatch) -> None:
    class FailingEditorialModel:
        calls = 0

        def with_structured_output(self, _schema: type[EditorialReportDraft]) -> "FailingEditorialModel":
            return self

        async def ainvoke(self, _prompt: str) -> EditorialReportDraft:
            self.calls += 1
            raise RuntimeError("temporary provider failure")

    model = FailingEditorialModel()
    monkeypatch.setattr("app.lib.llm.chat_model.build_chat_model", lambda: model)

    with pytest.raises(ReportEditorialUnavailable):
        await build_report(run_id="run_test", values=_values(), figure_events=_figures(), use_language_model=True)

    assert model.calls == 2


async def test_markdown_and_voice_are_generated_from_the_same_edited_report() -> None:
    report = await build_report(run_id="run_test", values=_values(), figure_events=_figures(), use_language_model=False)
    markdown = await render_chat_markdown(report)
    voice = await render_voice_narration(report)
    assert markdown.startswith("## Answer") and "## Evidence interpretation" in markdown
    assert "12.3 hectares" in markdown and "4.8 hectares" in markdown and "S2B_TEST" not in markdown
    assert voice == report.voice_narration and "#" not in voice and "S2B_TEST" not in voice


async def test_pdf_page_contract_keeps_models_and_limits_on_the_last_two_pages() -> None:
    report = await build_report(run_id="run_test", values=_values(refused=True), figure_events=_figures(), use_language_model=False)
    payload = await render_pdf(report, figure_paths=())
    pages = [page.extract_text() or "" for page in PdfReader(BytesIO(payload)).pages]
    assert payload.startswith(b"%PDF-")
    assert all(term in pages[1] for term in ("Objective", "Executive summary", "Question and direct answer", "Key facts"))
    assert "Models and analytical roles" in pages[-2]
    assert "Limitations and final assessment" in pages[-1]
    assert "1 material cross-sensor conflict" in pages[-1]
    assert "1 material cross-sensor conflict" not in pages[1]
    assert "fig_internal_01" not in " ".join(pages)
