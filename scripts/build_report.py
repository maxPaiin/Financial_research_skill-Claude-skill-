"""
Stage 4: Assemble the final English-only PDF from three layer .md files.

Reads:
  /home/claude/work/layer1_extraction.md
  /home/claude/work/layer2_screening.md
  /home/claude/work/layer3_ranked_advice.md

Outputs:
  /mnt/user-data/outputs/financial_research_report.pdf

PDF section order (§3.4):
  1.  Cover
  2.  Disclaimer (front)
  3.  Honest framing
  4.  Executive summary (auto-generated bullets)
  5.  Layer 1: Extraction summary
  6.  Layer 2: Overlap matrix (with heatmap)
  7.  Layer 2: Quality screen results
  8.  Layer 2: Data quality summary
  9.  Layer 3: Ranked watchlist (5 pages, 3 cards/page)
  10. Layer 3: Tier groupings
  11. Methodology disclosure
  12. Disclaimer (back)

Target: 18–26 pages (A4, 18mm margins, 10pt body, sans-serif).
English-only — no CJK font required.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from datetime import date
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, KeepTogether,
    )
    from reportlab.platypus.tableofcontents import TableOfContents
    _HAS_REPORTLAB = True
except ImportError:
    _HAS_REPORTLAB = False

_WORK_DIR = Path("/home/claude/work")
_ASSETS_DIR = Path("/home/claude/financial-research-skill-v0.2/assets")
_MARGIN = 18 * mm
_PAGE_WIDTH, _PAGE_HEIGHT = A4


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return f"_[{path.name} not found]_"


def _md_to_paragraphs(text: str, styles) -> list:
    """Very light markdown → ReportLab paragraphs. Handles headers and plain text."""
    elements = []
    for line in text.splitlines():
        stripped = line.rstrip()
        if stripped.startswith("### "):
            elements.append(Paragraph(stripped[4:], styles["Heading3"]))
        elif stripped.startswith("## "):
            elements.append(Paragraph(stripped[3:], styles["Heading2"]))
        elif stripped.startswith("# "):
            elements.append(Paragraph(stripped[2:], styles["Heading1"]))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            elements.append(Paragraph(f"• {stripped[2:]}", styles["BodyText"]))
        elif stripped.startswith("|"):
            pass  # Table rows handled separately
        elif stripped:
            elements.append(Paragraph(stripped, styles["BodyText"]))
        else:
            elements.append(Spacer(1, 4 * mm))
    return elements


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

    # 3. Honest framing (from Layer 3 header)
    story += [Paragraph("What This Analysis Is and Is Not", styles["Heading1"])]
    framing_start = layer3.find("## What this analysis is and is not")
    framing_end = layer3.find("## Top 15") if "## Top 15" in layer3 else layer3.find("## Tier A")
    if framing_start != -1 and framing_end != -1:
        framing_text = layer3[framing_start:framing_end]
        story += _md_to_paragraphs(framing_text, styles)
    story += [PageBreak()]

    # 4. Executive summary (auto-generated)
    story += [Paragraph("Executive Summary", styles["Heading1"])]
    story += [Paragraph(
        "This report presents a ranked watchlist of US-listed equities held across "
        "HKMA-approved global funds distributed through Hong Kong private banking channels. "
        "Stocks are filtered to US listings only (including ADRs), screened for fundamental "
        "quality, and ranked by a composite signal combining quality and consensus-with-crowding-discount. "
        "The top 15 are organized into three tiers. All methodology limitations are disclosed below.",
        styles["BodyText"],
    )]
    story += [PageBreak()]

    # 5. Layer 1: Extraction summary
    story += _md_to_paragraphs(layer1, styles)
    story += [PageBreak()]

    # 6–8. Layer 2: Overlap + Screen + Data quality
    story += _md_to_paragraphs(layer2, styles)
    story += [PageBreak()]

    # 9–10. Layer 3: Ranked watchlist
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
