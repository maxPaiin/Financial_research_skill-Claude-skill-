"""
Stage 4: Assemble the final English-only PDF from three layer .md files.

Reads:
  <work-dir>/layer1_extraction.md
  <work-dir>/layer2_screening.md
  <work-dir>/layer3_ranked_advice.md

Outputs:
  /mnt/user-data/outputs/financial_research_report.pdf (default)

PDF section order (§3.4):
  1.  Cover
  2.  Disclaimer (front)
  3.  Honest framing
  4.  Executive summary (auto-generated bullets)
  5.  Layer 1: Extraction summary
  6.  Layer 2: Overlap matrix
  7.  Layer 2: Quality screen results
  8.  Layer 2: Data quality summary
  9.  Layer 3: Ranked watchlist
  10. Layer 3: Tier groupings
  11. Methodology disclosure
  12. Disclaimer (back)

Target: 18–26 pages (A4, 18mm margins, 10pt body, sans-serif).
English-only — no CJK font required.
"""

from __future__ import annotations

import argparse
import html
import re
from datetime import date
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    )
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False

# Paths resolved relative to this file so the skill works regardless of where
# it's mounted (the previous hardcoded /home/claude/... made the disclaimer
# silently fall back to a placeholder string — see review §B5).
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
_ASSETS_DIR = _PROJECT_ROOT / "assets"
_WORK_DIR = Path("/home/claude/work")

_MARGIN = 18 * mm
_PAGE_WIDTH, _PAGE_HEIGHT = A4 if _HAS_REPORTLAB else (210, 297)

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_TABLE_SEP_RE = re.compile(r"^\|?[\s\-:|]+\|?$")


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return f"_[{path.name} not found]_"


def _escape_inline(s: str) -> str:
    """Escape HTML-special chars for ReportLab Paragraph; restore **bold** as <b>.

    ReportLab's Paragraph parses its input as mini-XML, so a holding name like
    "S&P Global" or "Procter & Gamble" would crash the build. We escape first
    (which leaves the `**` markdown bold markers untouched), then rewrite
    `**text**` into `<b>text</b>` — see review §B7.
    """
    s = html.escape(s, quote=False)
    s = _BOLD_RE.sub(r"<b>\1</b>", s)
    return s


def _parse_table_row(line: str) -> list[str]:
    inner = line.strip().strip("|")
    return [c.strip() for c in inner.split("|")]


def _is_table_separator(line: str) -> bool:
    stripped = line.strip()
    return bool(_TABLE_SEP_RE.match(stripped)) and "-" in stripped


def _build_table(rows: list[list[str]], styles) -> "Table | None":
    if not rows:
        return None
    n_cols = max(len(r) for r in rows)
    if n_cols == 0:
        return None

    # Pad ragged rows so ReportLab's Table doesn't choke on uneven row widths.
    padded = [r + [""] * (n_cols - len(r)) for r in rows]

    header_style = styles["TableHeader"]
    body_style = styles["TableCell"]
    data = []
    for i, row in enumerate(padded):
        style = header_style if i == 0 else body_style
        data.append([
            Paragraph(_escape_inline(cell) if cell else "&nbsp;", style)
            for cell in row
        ])

    usable_width = _PAGE_WIDTH - 2 * _MARGIN
    col_widths = [usable_width / n_cols] * n_cols

    tbl = Table(data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return tbl


def _md_to_paragraphs(text: str, styles) -> list:
    """Lightweight markdown → ReportLab flowables.

    Recognizes:
      - ATX headings (`#`, `##`, `###`)
      - Bullet lists (`-` or `*`)
      - Blockquotes (`>`) — rendered italic
      - Pipe-style tables — buffered until the table block ends, then emitted
        as a ReportLab Table flowable (§B6 fix)
      - Inline `**bold**`
      - Plain text paragraphs
    """
    elements: list = []
    table_buf: list[list[str]] = []

    def flush_table():
        if table_buf:
            tbl = _build_table(table_buf, styles)
            if tbl is not None:
                elements.append(tbl)
                elements.append(Spacer(1, 3 * mm))
            table_buf.clear()

    for line in text.splitlines():
        stripped = line.rstrip()
        leading = stripped.lstrip()

        if leading.startswith("|"):
            if _is_table_separator(stripped):
                continue
            row = _parse_table_row(stripped)
            if row:
                table_buf.append(row)
            continue

        # Non-table line — flush any buffered table first
        flush_table()

        if stripped.startswith("### "):
            elements.append(Paragraph(_escape_inline(stripped[4:]), styles["Heading3"]))
        elif stripped.startswith("## "):
            elements.append(Paragraph(_escape_inline(stripped[3:]), styles["Heading2"]))
        elif stripped.startswith("# "):
            elements.append(Paragraph(_escape_inline(stripped[2:]), styles["Heading1"]))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            elements.append(Paragraph("• " + _escape_inline(stripped[2:]), styles["BodyText"]))
        elif stripped.startswith("> "):
            elements.append(Paragraph(
                f"<i>{_escape_inline(stripped[2:])}</i>", styles["BodyText"]
            ))
        elif stripped:
            elements.append(Paragraph(_escape_inline(stripped), styles["BodyText"]))
        else:
            elements.append(Spacer(1, 4 * mm))

    flush_table()
    return elements


def _add_table_styles(styles):
    if "TableHeader" not in styles.byName:
        styles.add(ParagraphStyle(
            "TableHeader", parent=styles["Normal"], fontSize=8, leading=10,
            fontName="Helvetica-Bold",
        ))
    if "TableCell" not in styles.byName:
        styles.add(ParagraphStyle(
            "TableCell", parent=styles["Normal"], fontSize=8, leading=10,
        ))


def build_pdf(work_dir: Path, out_path: Path):
    if not _HAS_REPORTLAB:
        print("ERROR: reportlab not installed. Run: pip install reportlab --break-system-packages")
        return

    layer1 = _load_text(work_dir / "layer1_extraction.md")
    layer2 = _load_text(work_dir / "layer2_screening.md")
    layer3 = _load_text(work_dir / "layer3_ranked_advice.md")
    disclaimer = _load_text(_ASSETS_DIR / "disclaimer.md")

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        "Cover", parent=styles["Title"], fontSize=22, spaceAfter=8 * mm,
    ))
    styles.add(ParagraphStyle(
        "SubCover", parent=styles["Normal"], fontSize=12, spaceAfter=4 * mm,
    ))
    _add_table_styles(styles)

    story = []

    # 1. Cover
    story += [
        Spacer(1, 30 * mm),
        Paragraph("Financial Research Report", styles["Cover"]),
        Paragraph("HKMA-Approved Fund Holdings — US Equity Watchlist", styles["SubCover"]),
        Paragraph(f"Generated: {date.today().isoformat()}", styles["Normal"]),
        Paragraph(
            "AI-generated analysis. Not investment advice. See Disclaimer.",
            styles["Normal"],
        ),
        PageBreak(),
    ]

    # 2. Disclaimer (front)
    story += [Paragraph("Disclaimer", styles["Heading1"])]
    story += _md_to_paragraphs(disclaimer, styles)
    story += [PageBreak()]

    # 3. Honest framing (sliced out of layer3)
    story += [Paragraph("What This Analysis Is and Is Not", styles["Heading1"])]
    framing_start = layer3.find("## What this analysis is and is not")
    if framing_start != -1:
        # End at the next ## heading, whatever it is — Tier A is the usual
        # next section but a small universe with only Tier B/C still works,
        # and `## Methodology disclosure` is the always-present backstop.
        next_section = layer3.find("\n## ", framing_start + 2)
        framing_end = next_section if next_section != -1 else len(layer3)
        framing_text = layer3[framing_start:framing_end]
        story += _md_to_paragraphs(framing_text, styles)
    story += [PageBreak()]

    # 4. Executive summary
    story += [Paragraph("Executive Summary", styles["Heading1"])]
    story += [Paragraph(
        "This report presents a ranked watchlist of US-listed equities held across "
        "HKMA-approved global funds distributed through Hong Kong private banking channels. "
        "Stocks are filtered to US listings only (including ADRs), screened for fundamental "
        "quality, and ranked by a composite signal combining quality and "
        "consensus-with-crowding-discount. The top 15 are organized into three tiers. "
        "All methodology limitations are disclosed below.",
        styles["BodyText"],
    )]
    story += [PageBreak()]

    # 5. Layer 1
    story += _md_to_paragraphs(layer1, styles)
    story += [PageBreak()]

    # 6–8. Layer 2
    story += _md_to_paragraphs(layer2, styles)
    story += [PageBreak()]

    # 9–10. Layer 3
    story += _md_to_paragraphs(layer3, styles)
    story += [PageBreak()]

    # 12. Disclaimer (back)
    story += [Paragraph("Disclaimer", styles["Heading1"])]
    story += _md_to_paragraphs(disclaimer, styles)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)
    print(f"PDF written to {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default=str(_WORK_DIR))
    ap.add_argument("--out", default="/mnt/user-data/outputs/financial_research_report.pdf")
    args = ap.parse_args()

    build_pdf(Path(args.work_dir), Path(args.out))


if __name__ == "__main__":
    main()
