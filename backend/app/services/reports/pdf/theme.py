"""Defines the restrained AERIS print palette, typography, and reusable paragraph styles."""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

NAVY = colors.HexColor("#0B1628")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#596579")
RULE = colors.HexColor("#BAC3CF")
PAPER = colors.HexColor("#F4F6F8")
WHITE = colors.white
TEAL = colors.HexColor("#147D88")


def build_styles() -> dict[str, ParagraphStyle]:
    fonts = {"AerisSans": "segoeui.ttf", "AerisSansBold": "segoeuib.ttf", "AerisSerif": "cambria.ttc", "AerisSerifBold": "cambriab.ttf"}
    for name, filename in fonts.items():
        path = Path("C:/Windows/Fonts") / filename
        if path.exists() and name not in pdfmetrics.getRegisteredFontNames():
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=0))
            except TypeError:
                pdfmetrics.registerFont(TTFont(name, path))
    sans = "AerisSans" if "AerisSans" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    sans_bold = "AerisSansBold" if "AerisSansBold" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    serif = "AerisSerif" if "AerisSerif" in pdfmetrics.getRegisteredFontNames() else "Times-Roman"
    serif_bold = "AerisSerifBold" if "AerisSerifBold" in pdfmetrics.getRegisteredFontNames() else "Times-Bold"
    base = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle("brand", parent=base["Normal"], fontName=sans_bold, fontSize=10, leading=12, textColor=TEAL, spaceAfter=18),
        "cover_title": ParagraphStyle("cover_title", parent=base["Title"], fontName=serif, fontSize=31, leading=36, textColor=WHITE, spaceAfter=12),
        "cover_deck": ParagraphStyle("cover_deck", parent=base["Normal"], fontName=sans, fontSize=11, leading=16, textColor=colors.HexColor("#D6DCE5"), spaceAfter=18),
        "cover_body": ParagraphStyle("cover_body", parent=base["Normal"], fontName=serif, fontSize=14, leading=21, textColor=WHITE),
        "title": ParagraphStyle("title", parent=base["Heading1"], fontName=serif, fontSize=23, leading=28, textColor=NAVY, spaceAfter=9),
        "deck": ParagraphStyle("deck", parent=base["Normal"], fontName=sans, fontSize=9.3, leading=14, textColor=MUTED, spaceAfter=12),
        "heading": ParagraphStyle("heading", parent=base["Heading2"], fontName=sans_bold, fontSize=11.5, leading=15, textColor=INK, spaceBefore=6, spaceAfter=5),
        "question": ParagraphStyle("question", parent=base["Normal"], fontName=serif_bold, fontSize=10.5, leading=15, textColor=INK, spaceAfter=4),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName=serif, fontSize=9.4, leading=14.2, textColor=INK, spaceAfter=6),
        "body_bold": ParagraphStyle("body_bold", parent=base["BodyText"], fontName=serif_bold, fontSize=10.5, leading=15.5, textColor=INK),
        "label": ParagraphStyle("label", parent=base["Normal"], fontName=sans_bold, fontSize=7.5, leading=10, textColor=TEAL, spaceAfter=2),
        "caption": ParagraphStyle("caption", parent=base["Normal"], fontName=sans, fontSize=7.8, leading=11, textColor=MUTED, spaceAfter=4),
        "evidence": ParagraphStyle("evidence", parent=base["BodyText"], fontName=serif, fontSize=8.5, leading=12.5, textColor=INK, spaceAfter=4),
    }
