"""Builds compact print components from presentation-neutral report content."""

from html import escape
from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle

from app.schemas.report import EvidenceNarrative, KeyFact, ModelNarrative, QuestionAnswer, ReportFigure
from app.services.reports.pdf.theme import INK, PAPER, RULE


def prose(text: str, style) -> Paragraph:  # noqa: ANN001
    return Paragraph(escape(text), style)


def note_box(text: str, style, *, width: float = 171 * mm) -> Table:  # noqa: ANN001
    return Table([[Paragraph(escape(text), style)]], colWidths=[width], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.45, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))


def question_answer(item: QuestionAnswer, styles: dict) -> Table:
    return Table([[
        [Paragraph("QUESTION", styles["label"]), Paragraph(escape(item.question), styles["question"])],
        [Paragraph("DIRECT ANSWER", styles["label"]), Paragraph(escape(item.answer), styles["body_bold"])],
    ]], colWidths=[72 * mm, 99 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.45, RULE),
        ("LINEAFTER", (0, 0), (0, -1), 0.45, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))


def fact_grid(items: list[KeyFact], styles: dict, *, compact: bool = False) -> Table:
    cells = [
        [Paragraph(escape(item.label), styles["label"]), Paragraph(escape(item.value), styles["body_bold"])]
        + ([] if compact else [Paragraph(escape(item.interpretation), styles["evidence"])])
        for item in items[:4]
    ]
    rows = []
    for index in range(0, len(cells), 2):
        row = [cells[index], cells[index + 1] if index + 1 < len(cells) else [Spacer(1, 1)]]
        rows.append(row)
    return Table(rows or [[[Paragraph("No quantitative fact was asserted.", styles["body"])], [Spacer(1, 1)]]], colWidths=[84 * mm, 84 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPER), ("BOX", (0, 0), (-1, -1), 0.4, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.white), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))


def evidence_panel(figure: ReportFigure, narrative: EvidenceNarrative, path: Path | None, styles: dict, width: float, image_height: float = 100 * mm) -> list:
    content = [Paragraph(escape(narrative.title), styles["heading"])]
    if path is not None and path.exists():
        content.append(fitted_image(path, width, image_height))
    else:
        content.append(note_box("Visual evidence was retained in the run manifest but is not available in this export.", styles["caption"], width=width))
    if figure.caption:
        content.extend([Spacer(1, 1.5 * mm), Paragraph(escape(figure.caption), styles["caption"])])
    content.extend([
        Paragraph("WHAT THE IMAGE SHOWS", styles["label"]), Paragraph(escape(narrative.what_it_shows), styles["evidence"]),
        Paragraph("WHAT IT SUPPORTS", styles["label"]), Paragraph(escape(narrative.what_it_supports), styles["evidence"]),
        Paragraph("EVIDENCE BASIS", styles["label"]), Paragraph(escape(narrative.why_it_is_credible), styles["evidence"]),
    ])
    return content


def model_table(items: list[ModelNarrative], styles: dict) -> Table:
    rows = [[Paragraph("METHOD", styles["label"]), Paragraph("ANALYTICAL ROLE", styles["label"]), Paragraph("WHY USED", styles["label"])]]
    for item in items:
        rows.append([
            [Paragraph(escape(item.name), styles["body_bold"]), Paragraph(escape("Version " + item.version), styles["caption"])],
            [Paragraph(escape(item.what_was_analysed), styles["body"]), Paragraph(escape(item.contribution), styles["caption"])],
            Paragraph(escape(item.why_it_was_used), styles["body"]),
        ])
    return Table(rows, colWidths=[42 * mm, 67 * mm, 62 * mm], repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))


def findings_table(items: list[KeyFact], styles: dict) -> Table:
    rows = [[Paragraph("FINDING", styles["label"]), Paragraph("VALIDATED RESULT AND INTERPRETATION", styles["label"])]]
    rows.extend([
        Paragraph(escape(item.label), styles["body_bold"]),
        [Paragraph(escape(item.value), styles["body"]), Paragraph(escape(item.interpretation), styles["caption"])],
    ] for item in items)
    return Table(rows, colWidths=[43 * mm, 128 * mm], repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))


def fitted_image(path: Path, max_width: float, max_height: float) -> Image:
    with PILImage.open(path) as source:
        width, height = source.size
        ratio = min(max_width / width, max_height / height)
        stream = BytesIO()
        source.convert("RGB").save(stream, format="JPEG", quality=94, optimize=True)
    stream.seek(0)
    return Image(stream, width=width * ratio, height=height * ratio)
