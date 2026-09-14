"""Proves Phase 1.12 produces a reader-first report without weakening evidence boundaries.

what  : Tests the report dossier, editorial guard, Markdown, voice preparation, and PDF page contract.
where : The focused Phase 1.12 gate. Real-run visual verification remains an integration acceptance step.
how   : Uses small wire-shaped facts and deliberately unsafe editorial drafts; no model or storage is needed.
"""

from datetime import UTC, datetime
from io import BytesIO

from pypdf import PdfReader

from app.schemas.report import EditorialReportDraft, EvidenceNarrative
from app.services.reports.generator import apply_editorial_draft, build_report
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
