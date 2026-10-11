"""Small ReportLab toolkit shared by the documentation generators (consistent styling across PDFs)."""
import json
import os
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle)

ACCENT = colors.HexColor("#1F4E79")
LIGHT = colors.HexColor("#EEF3F8")

_FONTS = {"Body": ("arial.ttf", "Helvetica"), "Body-Bold": ("arialbd.ttf", "Helvetica-Bold"),
          "Mono": ("consola.ttf", "Courier")}
FONT = {}
try:
    from reportlab.lib.fonts import addMapping
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    win = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for name, (ttf, _) in _FONTS.items():
        pdfmetrics.registerFont(TTFont(name, str(win / ttf)))
        FONT[name] = name
    addMapping("Body", 0, 0, "Body"); addMapping("Body", 1, 0, "Body-Bold")
    addMapping("Body", 0, 1, "Body"); addMapping("Body", 1, 1, "Body-Bold")
except Exception:  # non-Windows: fall back to built-in fonts
    FONT = {k: v[1] for k, v in _FONTS.items()}

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", parent=ss["Title"], fontName=FONT["Body-Bold"], fontSize=22, leading=27,
                            textColor=ACCENT, alignment=TA_LEFT, spaceAfter=4),
    "subtitle": ParagraphStyle("st", parent=ss["Normal"], fontName=FONT["Body"], fontSize=11, textColor=colors.grey, spaceAfter=10),
    "h1": ParagraphStyle("h1", parent=ss["Heading1"], keepWithNext=1, fontName=FONT["Body-Bold"], fontSize=15, textColor=ACCENT, spaceBefore=12, spaceAfter=6),
    "h2": ParagraphStyle("h2", parent=ss["Heading2"], keepWithNext=1, fontName=FONT["Body-Bold"], fontSize=12, textColor=ACCENT, spaceBefore=9, spaceAfter=4),
    "h3": ParagraphStyle("h3", parent=ss["Heading3"], keepWithNext=1, fontName=FONT["Body-Bold"], fontSize=10.5, spaceBefore=6, spaceAfter=3),
    "body": ParagraphStyle("b", parent=ss["Normal"], fontName=FONT["Body"], fontSize=10, leading=14.2, spaceAfter=5),
    "small": ParagraphStyle("s", parent=ss["Normal"], fontName=FONT["Body"], fontSize=8.6, leading=11.2),
    "cell": ParagraphStyle("c", parent=ss["Normal"], fontName=FONT["Body"], fontSize=8.4, leading=10.6),
    "cellb": ParagraphStyle("cb", parent=ss["Normal"], fontName=FONT["Body-Bold"], fontSize=8.4, leading=10.6, textColor=colors.white),
    "code": ParagraphStyle("code", parent=ss["Code"], fontName=FONT["Mono"], fontSize=7.6, leading=9.6,
                           backColor=colors.HexColor("#F5F7FA"), borderPadding=5, leftIndent=3, spaceBefore=3, spaceAfter=7),
}


def esc(t) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class Doc:
    def __init__(self, path: Path, title: str, subtitle: str):
        self.path, self.title, self.story = Path(path), title, []
        self.story += [Paragraph(esc(title), S["title"]), Paragraph(esc(subtitle), S["subtitle"]),
                       HRFlowable(width="100%", color=ACCENT, thickness=1.3, spaceAfter=10)]

    def h1(self, t): self.story.append(Paragraph(esc(t), S["h1"]))
    def h2(self, t): self.story.append(Paragraph(esc(t), S["h2"]))
    def h3(self, t): self.story.append(Paragraph(esc(t), S["h3"]))
    def p(self, t, raw=False): self.story.append(Paragraph(t if raw else esc(t), S["body"]))
    def small(self, t): self.story.append(Paragraph(esc(t), S["small"]))
    def space(self, h=6): self.story.append(Spacer(1, h))
    def page(self): self.story.append(PageBreak())

    def bullets(self, items, raw=False):
        self.story.append(ListFlowable([ListItem(Paragraph(x if raw else esc(x), S["body"]), leftIndent=12) for x in items],
                                       bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8))

    def code(self, text, max_lines=60):
        if not isinstance(text, str):
            text = json.dumps(text, indent=2, default=str)
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[:max_lines] + [f"... ({len(text.splitlines()) - max_lines} more lines)"]
        wrapped = []
        for ln in lines:
            while len(ln) > 118:
                wrapped.append(ln[:118]); ln = "    " + ln[118:]
            wrapped.append(ln)
        self.story.append(Preformatted("\n".join(wrapped), S["code"]))

    def table(self, rows, widths=None, header=True, font=None):
        data = [[Paragraph(esc(c), S["cellb"] if (header and i == 0) else S["cell"]) for c in r] for i, r in enumerate(rows)]
        t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#C9D3DE")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), ACCENT)]
            style += [("BACKGROUND", (0, i), (-1, i), LIGHT) for i in range(2, len(rows), 2)]
        t.setStyle(TableStyle(style))
        self.story += [t, Spacer(1, 8)]

    def image(self, path, width_mm=170):
        from reportlab.lib.utils import ImageReader
        iw, ih = ImageReader(str(path)).getSize()
        w = width_mm * mm
        self.story += [Image(str(path), width=w, height=w * ih / iw), Spacer(1, 6)]

    def keep(self, *flowables):
        self.story.append(KeepTogether(list(flowables)))

    def build(self):
        def footer(c, d):
            c.saveState(); c.setFont(FONT["Body"], 7.5); c.setFillColor(colors.grey)
            c.drawString(18 * mm, 10 * mm, self.title)
            c.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {d.page}"); c.restoreState()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        SimpleDocTemplate(str(self.path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                          bottomMargin=18 * mm, title=self.title, author="Supply Chain Disruption Assistant").build(
            self.story, onFirstPage=footer, onLaterPages=footer)
        print("wrote", self.path)
