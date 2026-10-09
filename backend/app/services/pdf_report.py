"""Render a saved analysis as a printable PDF report (ReportLab, no external services).

Everything that comes from a log or from the AI is escaped before it reaches a
Paragraph, because ReportLab paragraphs interpret markup such as <img src=...>.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.config import APP_NAME, APP_VERSION
from app.models import Analysis

PAGE_W, _PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

INK = colors.HexColor("#0a111d")
TEXT = colors.HexColor("#1f2937")
MUTED = colors.HexColor("#6b7280")
RULE = colors.HexColor("#d9dee7")
ACCENT = colors.HexColor("#0e7490")
GREEN = colors.HexColor("#15803d")
PANEL = colors.HexColor("#f3f6fa")

SEVERITY_COLORS = {
    "LOW": "#15803d",
    "MEDIUM": "#b45309",
    "HIGH": "#c2410c",
    "CRITICAL": "#b91c1c",
}
SEVERITY_INFO = {
    "LOW": "Minor issue. The service still works.",
    "MEDIUM": "Degraded. A workaround is likely.",
    "HIGH": "A service or deployment is failing.",
    "CRITICAL": "Outage, data-loss risk, or security exposure.",
}

# ---------------------------------------------------------------------------
# Text handling. The built-in PDF fonts only cover Latin-1/cp1252, so common
# box-drawing and arrow characters are mapped to ASCII and anything else that
# cannot be drawn becomes "?".
# ---------------------------------------------------------------------------
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TRANSLATE = str.maketrans(
    {
        "│": "|", "┃": "|", "╷": "|", "╵": "|", "║": "|",
        "─": "-", "━": "-", "═": "=",
        "┌": "+", "┐": "+", "└": "+", "┘": "+", "├": "+", "┤": "+",
        "┬": "+", "┴": "+", "┼": "+", "╭": "+", "╮": "+", "╯": "+", "╰": "+",
        "→": "->", "←": "<-", "⇒": "=>", "✓": "v", "✔": "v", "✗": "x", "✘": "x",
        "\u00a0": " ",
    }
)


def pdf_text(value: object) -> str:
    """Make arbitrary text safe to draw with the built-in fonts."""
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_TRANSLATE)
    text = _CONTROL.sub("", text)
    return text.encode("cp1252", "replace").decode("cp1252")


def para_text(value: object) -> str:
    """Escaped text for a Paragraph (keeps line breaks)."""
    return escape(pdf_text(value)).replace("\n", "<br/>")


def mono_text(value: object) -> str:
    """Escaped text for a monospaced Paragraph (keeps spacing and line breaks)."""
    safe = escape(pdf_text(value)).replace("\t", "    ")
    safe = re.sub(r" {2,}", lambda m: "&nbsp;" * len(m.group(0)), safe)
    return safe.replace("\n", "<br/>")


def _fmt_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def pdf_filename(a: Analysis) -> str:
    stamp = a.created_at.strftime("%Y%m%d") if a.created_at else "report"
    return f"deploydoctor-diagnosis-{a.id}-{stamp}.pdf"


# ---------------------------------------------------------------------------
# Styles and building blocks
# ---------------------------------------------------------------------------
def _styles() -> dict[str, ParagraphStyle]:
    def style(name: str, **kw) -> ParagraphStyle:
        base = dict(fontName="Helvetica", fontSize=10, leading=14.5, textColor=TEXT)
        base.update(kw)
        return ParagraphStyle(name, **base)

    return {
        "brand": style("brand", fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK),
        "muted": style("muted", fontSize=9, leading=12, textColor=MUTED),
        "muted_body": style("muted_body", textColor=MUTED),
        "head_right": style("head_right", fontName="Helvetica-Bold", fontSize=11, leading=14, alignment=2, textColor=INK),
        "head_right_muted": style("head_right_muted", fontSize=9, leading=12, alignment=2, textColor=MUTED),
        "h2": style(
            "h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=INK,
            spaceBefore=14, spaceAfter=3, keepWithNext=1,
        ),
        "body": style("body"),
        "label": style("label", fontSize=8.5, leading=11, textColor=MUTED),
        "label_strong": style("label_strong", fontName="Helvetica-Bold", fontSize=9.5, leading=13, textColor=MUTED),
        "value": style("value", fontSize=10, leading=13.5),
        "sev": style(
            "sev", fontName="Helvetica-Bold", fontSize=13, leading=16, alignment=1, textColor=colors.white
        ),
        "conf": style("conf", fontSize=16, leading=19, alignment=1),
        "list": style("list", leftIndent=16, bulletIndent=2, spaceAfter=3, bulletFontName="Helvetica-Bold"),
        "mono": style("mono", fontName="Courier", fontSize=8.5, leading=11.5),
    }


def _section(story: list, st: dict, number: str, title: str, hint: str) -> None:
    heading = Paragraph(
        f'<font color="#0e7490">{number}</font>&nbsp;&nbsp;{escape(title)}'
        f'<font size="9" color="#6b7280">&nbsp;&nbsp;&nbsp;{escape(hint)}</font>',
        st["h2"],
    )
    rule = HRFlowable(width="100%", thickness=0.6, color=RULE, spaceBefore=1, spaceAfter=6)
    rule.keepWithNext = 1
    story.extend([heading, rule])


def _box(flowable, accent=ACCENT, background=PANEL) -> Table:
    box = Table([[flowable]], colWidths=[CONTENT_W])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("LINEBEFORE", (0, 0), (0, -1), 2.2, accent),
                ("LEFTPADDING", (0, 0), (-1, -1), 9),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return box


def _code_box(text: object, st: dict, accent=ACCENT) -> Table:
    return _box(Paragraph(mono_text(text), st["mono"]), accent=accent)


def _numbered(items: list, st: dict) -> list:
    return [Paragraph(para_text(t), st["list"], bulletText=f"{i}.") for i, t in enumerate(items, 1)]


def _bullets(items: list, st: dict) -> list:
    return [Paragraph(para_text(t), st["list"], bulletText="\u2022") for t in items]


class _NumberedCanvas(canvas.Canvas):
    """Draws a footer with 'Page X of Y' on every page."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        self.setStrokeColor(RULE)
        self.setLineWidth(0.5)
        self.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
        self.setFont("Helvetica", 8)
        self.setFillColor(MUTED)
        self.drawString(
            MARGIN, 10.5 * mm,
            "Generated by DeployDoctor. AI can be wrong: review every fix. Commands are suggestions only.",
        )
        self.drawRightString(PAGE_W - MARGIN, 10.5 * mm, f"Page {self._pageNumber} of {total}")


# ---------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------
def build_pdf(a: Analysis) -> bytes:
    st = _styles()
    sev = a.severity if a.severity in SEVERITY_COLORS else "MEDIUM"
    sev_color = colors.HexColor(SEVERITY_COLORS[sev])
    pct = max(0, min(100, round(float(a.confidence or 0) * 100)))
    conf_hex = "#15803d" if pct >= 80 else "#b45309" if pct >= 50 else "#b91c1c"
    generated = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    story: list = []

    # Header
    header = Table(
        [[
            [Paragraph(APP_NAME, st["brand"]), Paragraph("AI-powered deployment troubleshooter", st["muted"])],
            [
                Paragraph("Incident diagnosis report", st["head_right"]),
                Paragraph(f"Generated {generated}", st["head_right_muted"]),
            ],
        ]],
        colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.45],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACCENT),
            ]
        )
    )
    story += [header, Spacer(1, 12)]

    if a.ai_model == "fallback":
        banner = Table(
            [[Paragraph(
                "The AI answer could not be validated, so this is a low-confidence fallback. "
                "It is not a diagnosis. Run the analysis again with a shorter, more focused log.",
                st["body"],
            )]],
            colWidths=[CONTENT_W],
        )
        banner.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#f59e0b")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story += [banner, Spacer(1, 10)]

    # Vitals: severity, what it means, confidence
    sev_w, conf_w = 36 * mm, 32 * mm
    vitals = Table(
        [[
            Paragraph(sev, st["sev"]),
            Paragraph(para_text(SEVERITY_INFO[sev]), st["body"]),
            Paragraph(
                f'<font color="{conf_hex}"><b>{pct}%</b></font><br/>'
                f'<font size="8" color="#6b7280">confidence</font>',
                st["conf"],
            ),
        ]],
        colWidths=[sev_w, CONTENT_W - sev_w - conf_w, conf_w],
        rowHeights=[18 * mm],
    )
    vitals.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (0, 0), sev_color),
                ("BACKGROUND", (1, 0), (-1, 0), PANEL),
                ("BOX", (0, 0), (-1, -1), 0.6, RULE),
                ("LEFTPADDING", (1, 0), (1, 0), 12),
                ("RIGHTPADDING", (1, 0), (1, 0), 8),
            ]
        )
    )
    story += [vitals, Spacer(1, 8)]

    # Meta grid
    label_w = 30 * mm
    value_w = (CONTENT_W - 2 * label_w) / 2
    rows = [
        ("Affected component", a.affected_component, "Category", a.category),
        ("Analyzed", _fmt_dt(a.created_at), "Model", a.ai_model or "-"),
        ("Analysis ID", f"#{a.id}", "Report version", f"{APP_NAME} {APP_VERSION}"),
    ]
    meta = Table(
        [
            [
                Paragraph(para_text(k1), st["label"]), Paragraph(para_text(v1), st["value"]),
                Paragraph(para_text(k2), st["label"]), Paragraph(para_text(v2), st["value"]),
            ]
            for k1, v1, k2, v2 in rows
        ],
        colWidths=[label_w, value_w, label_w, value_w],
    )
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, RULE),
            ]
        )
    )
    story.append(meta)

    # 1 Symptom, 2 Root cause
    _section(story, st, "1", "Symptom", "What is failing")
    story.append(Paragraph(para_text(a.summary), st["body"]))
    _section(story, st, "2", "Root cause", "Why it is failing")
    story.append(Paragraph(para_text(a.root_cause), st["body"]))

    # 3 Evidence
    _section(story, st, "3", "Evidence", "Lines from the log that support the diagnosis")
    if a.evidence:
        for line in a.evidence:
            story += [_code_box(line, st), Spacer(1, 4)]
    else:
        story.append(Paragraph("No verifiable evidence lines were found in the log.", st["muted_body"]))

    # 4 Fix
    _section(story, st, "4", "Fix", "What to do about it")
    if a.recommended_fix:
        story += _numbered(list(a.recommended_fix), st)
    else:
        story.append(Paragraph("No fix steps were returned.", st["muted_body"]))
    if a.commands:
        story += [
            Spacer(1, 6),
            Paragraph("Commands", st["label_strong"]),
            Paragraph(
                "Recommendations only. Review each command before running it. "
                "DeployDoctor never executes anything.",
                st["muted"],
            ),
            Spacer(1, 4),
        ]
        for command in a.commands:
            story += [_code_box(command, st, accent=GREEN), Spacer(1, 4)]

    # 5 Prevention
    _section(story, st, "5", "Prevention", "How to stop it happening again")
    if a.prevention:
        story += _bullets(list(a.prevention), st)
    else:
        story.append(Paragraph("No prevention advice was returned.", st["muted_body"]))

    # DevOps insight
    if a.devops_insight:
        story += [
            Spacer(1, 14),
            _box(
                [
                    Paragraph("<b>DevOps Insight</b>", st["body"]),
                    Spacer(1, 3),
                    Paragraph(para_text(a.devops_insight), st["body"]),
                ],
                background=colors.HexColor("#eef7fb"),
            ),
        ]

    story += [
        Spacer(1, 16),
        Paragraph(
            "This report was generated by an AI model and can be wrong. Review every fix before "
            "applying it. Commands are suggestions and were not executed.",
            st["muted"],
        ),
    ]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=22 * mm,
        title=f"{APP_NAME} diagnosis #{a.id}",
        author=APP_NAME,
        subject="Incident diagnosis report",
        creator=f"{APP_NAME} {APP_VERSION}",
    )
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()
