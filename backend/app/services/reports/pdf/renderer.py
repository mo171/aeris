"""Renders the canonical report into a publication-style A4 document.

what  : Detailed and briefing PDF bytes from one `ReportDocument` plus the exact retained figure files.
where : Called by `services/reports/exporters.py`; it contains no editorial or scientific decisions.
how   : ReportLab runs in a worker thread. Page roles are fixed so models and limitations are always last.
"""

import asyncio
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.report import ReportDocument
from app.services.reports.pdf.components import (
    evidence_panel,
    fact_grid,
    findings_table,
    model_table,
    note_box,
    prose,
    question_answer,
)
from app.services.reports.pdf.theme import MUTED, NAVY, RULE, TEAL, build_styles


async def render_pdf(report: ReportDocument, *, figure_paths: tuple[Path, ...] = (), summary_only: bool = False) -> bytes:
    return await asyncio.to_thread(_render_pdf, report, figure_paths, summary_only)


def _render_pdf(report: ReportDocument, figure_paths: tuple[Path, ...], summary_only: bool) -> bytes:
    styles = build_styles()
    path_by_id = {path.stem: path for path in figure_paths}
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=20 * mm,
        bottomMargin=17 * mm, title=report.title, author="AERIS Earth Observation Intelligence",
    )
    story = _cover(report, styles) + [PageBreak()] + _decision_brief(report, styles)
    if summary_only:
        story += [PageBreak()] + _final_page(report, styles)
    else:
        if len(report.key_facts) > 4:
            story += [PageBreak()] + _findings_page(report, styles)
        story += _evidence_pages(report, path_by_id, styles)
        story += [PageBreak()] + _models_page(report, styles)
        story += [PageBreak()] + _final_page(report, styles)
    document.build(story, onFirstPage=_cover_canvas, onLaterPages=_body_canvas)
    return output.getvalue()


def _cover(report: ReportDocument, styles: dict) -> list:
    return [
        Spacer(1, 17 * mm), Paragraph("AERIS  /  RESEARCH REPORT", styles["brand"]),
        Paragraph(report.title, styles["cover_title"]), Paragraph(report.subtitle, styles["cover_deck"]),
        Spacer(1, 9 * mm), Paragraph("INVESTIGATION QUESTION", styles["brand"]),
        Paragraph(report.questions_and_answers[0].question if report.questions_and_answers else report.question, styles["cover_body"]),
        Spacer(1, 18 * mm), Paragraph("PRIMARY ASSESSMENT", styles["brand"]),
        Table([[Paragraph(report.executive_summary if report.is_evidence_limited else report.final_summary, styles["cover_body"])]], colWidths=[165 * mm], style=TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#607087")), ("PADDING", (0, 0), (-1, -1), 11),
        ])),
        Spacer(1, 22 * mm), Paragraph(report.generated_at.strftime("Prepared %d %B %Y"), styles["cover_deck"]),
    ]


def _decision_brief(report: ReportDocument, styles: dict) -> list:
    story = [
        Paragraph("Investigation brief", styles["title"]),
        Paragraph("The research objective, direct answer, and most decision-relevant facts are presented before methods or supporting imagery.", styles["deck"]),
        Paragraph("Objective", styles["heading"]), prose(report.objective, styles["body"]),
        Paragraph("Executive summary", styles["heading"]), note_box(report.executive_summary, styles["body_bold"]),
        Spacer(1, 4 * mm), Paragraph("Question and direct answer", styles["heading"]),
    ]
    story.extend(question_answer(item, styles) for item in report.questions_and_answers)
    if report.is_evidence_limited:
        area_facts = [item for item in report.key_facts[1:] if "area" in item.label.lower()]
        brief_facts = area_facts[:4]
    else:
        brief_facts = report.key_facts[:4]
    story.extend([Spacer(1, 4 * mm), Paragraph("Key facts", styles["heading"]), fact_grid(brief_facts, styles, compact=report.is_evidence_limited)])
    return story


def _evidence_pages(report: ReportDocument, paths: dict[str, Path], styles: dict) -> list:
    story: list = []
    for start in range(0, len(report.evidence_narratives), 2):
        story.append(PageBreak())
        batch = report.evidence_narratives[start:start + 2]
        story.extend([
            Paragraph("Visual evidence", styles["title"]),
            Paragraph("Each panel is interpreted against its linked validated finding; the image is evidence, not decoration.", styles["deck"]),
        ])
        cells = []
        for narrative in batch:
            figure = next(item for item in report.figures if item.id == narrative.figure_id)
            cells.append(evidence_panel(figure, narrative, paths.get(figure.id), styles, 80 * mm, 88 * mm))
        if len(cells) == 1:
            narrative = batch[0]
            figure = next(item for item in report.figures if item.id == narrative.figure_id)
            story.extend(evidence_panel(figure, narrative, paths.get(figure.id), styles, 168 * mm, 133 * mm))
        else:
            story.append(Table([cells], colWidths=[84 * mm, 84 * mm], style=TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (0, -1), 5), ("LEFTPADDING", (1, 0), (1, -1), 5),
                ("RIGHTPADDING", (1, 0), (1, -1), 0),
            ])))
    return story


def _findings_page(report: ReportDocument, styles: dict) -> list:
    findings = report.key_facts[1:] if report.is_evidence_limited else report.key_facts
    return [
        Paragraph("Complete validated findings", styles["title"]),
        Paragraph("Every quantitative result remains verbatim from a validated claim. Interpretive text explains relevance without changing a value.", styles["deck"]),
        findings_table(findings, styles),
    ]


def _models_page(report: ReportDocument, styles: dict) -> list:
    return [
        Paragraph("Models and analytical roles", styles["title"]),
        Paragraph("This method record explains what each analytical component examined, why it was selected, and how its output contributed to the result.", styles["deck"]),
        model_table(report.model_narratives, styles), Spacer(1, 6 * mm),
        Paragraph("How the evidence was assembled", styles["heading"]),
        prose("Inputs were validated before specialist analysis. Each analytical component then produced a retained result with a model or method record. Claims were constructed from those outputs and linked to visible evidence. Only after validation did the language model organise the findings into this reader-facing explanation.", styles["body"]),
        Paragraph("Interpretation boundary", styles["heading"]),
        prose("Specialist and deterministic methods produced the retained evidence. The language model organised and explained those validated results; it did not measure pixels, alter geometry, or create quantitative findings.", styles["body"]),
    ]


def _final_page(report: ReportDocument, styles: dict) -> list:
    return [
        Paragraph("Limitations and final assessment", styles["title"]),
        Paragraph("The final page separates what the evidence established from what must remain unresolved.", styles["deck"]),
        Paragraph("Question and answer", styles["heading"]),
        question_answer(report.questions_and_answers[0], styles) if report.questions_and_answers else note_box(report.final_summary, styles["body_bold"]),
        Spacer(1, 6 * mm), Paragraph("What could not be fully grounded", styles["heading"]), prose(report.limitations, styles["body"]),
        Spacer(1, 6 * mm), Paragraph("Final assessment", styles["heading"]), prose(report.final_summary, styles["body_bold"]),
        Spacer(1, 11 * mm), Paragraph("Reproducibility note", styles["heading"]),
        prose("The companion manifest retains input hashes, model versions, processing parameters, claim-to-evidence links, geometries, and render specifications. Transfer identifiers are intentionally excluded from this reader-facing document.", styles["body"]),
    ]


def _cover_canvas(canvas, document) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.setStrokeColor(TEAL)
    canvas.setLineWidth(0.75)
    canvas.line(document.leftMargin, 26 * mm, A4[0] - document.rightMargin, 26 * mm)
    canvas.restoreState()


def _body_canvas(canvas, document) -> None:  # noqa: ANN001
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.45)
    canvas.line(document.leftMargin, A4[1] - 13 * mm, A4[0] - document.rightMargin, A4[1] - 13 * mm)
    font = "AerisSans" if "AerisSans" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    canvas.setFont(font, 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(document.leftMargin, 8 * mm, "AERIS Research Report")
    canvas.drawRightString(A4[0] - document.rightMargin, 8 * mm, f"Page {document.page}")
    canvas.restoreState()
