"""Server-side PDF generation for the shortlist report using ReportLab."""

from io import BytesIO
from datetime import datetime, timezone
from typing import List, Dict, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

# Brand colors
ACCENT = colors.HexColor("#4338CA")
ACCENT_LIGHT = colors.HexColor("#EEF2FF")
DARK = colors.HexColor("#1A1A2E")
MUTED = colors.HexColor("#6B7280")
SUCCESS = colors.HexColor("#059669")
WARNING = colors.HexColor("#D97706")
DANGER = colors.HexColor("#DC2626")
BORDER = colors.HexColor("#E5E7EB")


def generate_shortlist_pdf(
    results: List[Dict],
    rubric,
    title: str = "CohortFilter AI — Shortlist Report"
) -> bytes:
    """Generate a PDF shortlist report. Returns raw bytes."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CFTitle", parent=styles["Title"],
        fontSize=18, textColor=DARK, spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "CFSubtitle", parent=styles["Normal"],
        fontSize=10, textColor=MUTED, spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "CFHeading", parent=styles["Heading2"],
        fontSize=13, textColor=ACCENT, spaceBefore=16, spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "CFBody", parent=styles["Normal"],
        fontSize=9, textColor=DARK, leading=13,
    )
    small_style = ParagraphStyle(
        "CFSmall", parent=styles["Normal"],
        fontSize=8, textColor=MUTED, leading=11,
    )

    elements = []

    # ── Header ──────────────────────────────────────────
    elements.append(Paragraph(title, title_style))
    rubric_dict = rubric.model_dump() if hasattr(rubric, "model_dump") else rubric
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    elements.append(Paragraph(
        f"Generated {now} &bull; Program: {rubric_dict.get('program_focus', 'N/A')} &bull; "
        f"{len(results)} applications shortlisted",
        subtitle_style,
    ))
    elements.append(HRFlowable(width="100%", thickness=1, color=BORDER))
    elements.append(Spacer(1, 8))

    # ── Rubric Summary ──────────────────────────────────
    elements.append(Paragraph("Scoring Rubric", heading_style))
    dims = rubric_dict.get("dimensions", [])
    if dims:
        dim_data = [["Dimension", "Weight"]]
        for d in dims:
            dim_data.append([d["name"], f"{d['weight']:.0%}"])
        dim_table = Table(dim_data, colWidths=[3.5 * inch, 1.2 * inch])
        dim_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT_LIGHT]),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(dim_table)

    dealbreakers = rubric_dict.get("dealbreakers", [])
    if dealbreakers:
        elements.append(Spacer(1, 6))
        db_text = " &bull; ".join(d["rule"] for d in dealbreakers)
        elements.append(Paragraph(f"<b>Dealbreakers:</b> {db_text}", small_style))

    elements.append(Spacer(1, 12))

    # ── Ranked Shortlist Table ──────────────────────────
    elements.append(Paragraph("Ranked Shortlist", heading_style))

    header = ["#", "Startup", "Founder", "Score", "Flags", "Summary"]
    col_widths = [0.35 * inch, 1.3 * inch, 1.0 * inch, 0.6 * inch, 1.0 * inch, 2.3 * inch]
    table_data = [header]

    for r in results:
        score = r.get("total_score", 0)
        flags = ", ".join(r.get("risk_flags", []))[:60]
        summary = r.get("summary", "")[:120]
        row = [
            str(r.get("rank", "")),
            Paragraph(str(r.get("startup_name", "")), body_style),
            Paragraph(str(r.get("founder_name", "")), body_style),
            str(score),
            Paragraph(flags, small_style),
            Paragraph(summary, small_style),
        ]
        table_data.append(row)

    main_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    # Color-code score cells
    table_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ACCENT_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    for i, r in enumerate(results, start=1):
        score = r.get("total_score", 0)
        if r.get("dealbreaker_hit"):
            table_styles.append(("TEXTCOLOR", (3, i), (3, i), DANGER))
        elif score >= 700:
            table_styles.append(("TEXTCOLOR", (3, i), (3, i), SUCCESS))
        elif score >= 400:
            table_styles.append(("TEXTCOLOR", (3, i), (3, i), WARNING))
        else:
            table_styles.append(("TEXTCOLOR", (3, i), (3, i), DANGER))

    main_table.setStyle(TableStyle(table_styles))
    elements.append(main_table)

    # ── Footer ──────────────────────────────────────────
    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    elements.append(Paragraph(
        "Generated by CohortFilter AI &bull; Powered by AMD MI300X + Llama 3 70B",
        ParagraphStyle("Footer", parent=small_style, alignment=TA_CENTER),
    ))

    doc.build(elements)
    return buf.getvalue()
