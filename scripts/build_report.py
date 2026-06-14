"""
Stage 4: Assemble the final English-only PDF from the layer .md files plus the
v0.3 macro/expectations appendix checkpoints, and copy all checkpoint .md files
to the user-visible outputs directory (D5).

Reads (from <work-dir>):
  layer1_extraction.md
  layer2_screening.md
  layer3_ranked_advice.md            (framing + ranked cards + methodology)
  macro_checkpoint.md                (M1 — optional; Appendix 2 macro/sector view)
  expectations_checkpoint.md         (M2 — optional; Appendix 1+2 per-stock scenarios)
  appendix3_consensus_warning.md     (C4 — optional; over-consensus + style remediation)

Outputs:
  /mnt/user-data/outputs/financial_research_report.pdf (default)
  /mnt/user-data/outputs/<each checkpoint>.md          (D5 copy)

PDF section order (v0.3, §3.4):
  1.  Cover
  2.  Disclaimer (front)
  3.  Honest framing (incl. single HK-bias statement, homogeneity warning,
      stratification-abandoned note, source-selection-method disclosure)
  4.  Executive summary
  5.  Layer 1: Extraction summary (per-fund style labels)
  6.  Layer 2: Overlap matrix
  7.  Layer 2: Quality screen results
  8.  Layer 2: Data quality summary + homogeneity state
  9.  Layer 3: Ranked watchlist (bias note NOT repeated; high-crowding warning
      kept; crowding labelled liquidity-inclusive / NAV-only)
  10. Layer 3: Tier groupings
  11. Appendix 1+2: per-stock best/avg/worst scenarios + macro/sector drivers
  12. Appendix 3: over-consensus & false-theme warning + fund-style remediation
  13. Methodology disclosure (confidence-shrinkage, days-to-liquidate, gate)
  14. Disclaimer (back)

v0.3 layout (D2): hard page breaks are reserved for major boundaries (cover,
front disclaimer, the analysis body, the appendices, the back disclaimer).
Section titles are kept with their following content via KeepTogether instead
of one-section-per-page breaks. Target 18–26pp is a ceiling, not a floor.

English-only — no CJK font required.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
from datetime import date
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
        KeepTogether,
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
_OUTPUTS_DIR = Path("/mnt/user-data/outputs")

# Checkpoint .md files copied to the user-visible outputs dir (D5). The work dir
# is ephemeral (resets between sessions), so these must be surfaced where the
# user can actually download them.
_CHECKPOINT_FILES = [
    "layer1_extraction.md",
    "layer2_screening.md",
    "layer3_ranked_advice.md",
    "macro_checkpoint.md",
    "expectations_checkpoint.md",
    "appendix3_consensus_warning.md",
]

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


_HEADING_STYLES = {"Heading1", "Heading2", "Heading3"}


def _group_headings(elements: list) -> list:
    """D2: keep each heading with its immediately following content so titles
    don't get orphaned at the bottom of a page, WITHOUT inserting a hard page
    break after every section. A heading is wrapped together with the next few
    flowables (up to the next heading) via KeepTogether. We cap the group so an
    over-long section still splits across pages rather than overflowing.
    """
    if not _HAS_REPORTLAB:
        return elements

    def is_heading(el) -> bool:
        return isinstance(el, Paragraph) and getattr(el.style, "name", "") in _HEADING_STYLES

    grouped: list = []
    i = 0
    n = len(elements)
    while i < n:
        el = elements[i]
        if is_heading(el):
            group = [el]
            j = i + 1
            # Pull in following flowables until the next heading, capped at 3
            # so KeepTogether never tries to hold a whole long section.
            while j < n and not is_heading(elements[j]) and len(group) < 4:
                group.append(elements[j])
                j += 1
            grouped.append(KeepTogether(group))
            i = j
        else:
            grouped.append(el)
            i += 1
    return grouped


def _md_to_paragraphs(text: str, styles, group: bool = True) -> list:
    """Lightweight markdown → ReportLab flowables.

    Recognizes ATX headings, bullet lists, blockquotes, pipe tables, inline
    bold, and plain paragraphs. When `group` is True (default), headings are
    kept with their following content (D2 — denser, no orphaned titles).
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

        if stripped.lstrip().startswith("|"):
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
            elements.append(Spacer(1, 2.5 * mm))

    flush_table()
    return _group_headings(elements) if group else elements


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


# --- Layer 3 slicing: split into framing / cards+tiers / methodology --------

def _slice_layer3(layer3: str) -> tuple[str, str, str]:
    """Return (framing, cards_and_tiers, methodology) sliced from layer3 md.

    layer3_report.py emits, in order:
      ## What this analysis is and is not   (framing)
      ## Tier A / B / C                      (ranked cards)
      ## Methodology disclosure ... ## Important caveats  (methodology)
      ## Disclaimer                          (dropped here — build_report adds
                                              the verbatim front/back disclaimer)
    Slicing keeps the section order explicit and avoids duplicating the
    disclaimer three times.
    """
    framing_start = layer3.find("## What this analysis is and is not")
    meth_start = layer3.find("## Methodology disclosure")
    disc_start = layer3.find("## Disclaimer")

    if framing_start == -1:
        # Unexpected shape — return the whole thing as the cards block.
        return "", layer3, ""

    framing_end = layer3.find("\n## ", framing_start + 2)
    framing = layer3[framing_start:framing_end] if framing_end != -1 else layer3[framing_start:]

    cards_start = framing_end if framing_end != -1 else len(layer3)
    cards_end = meth_start if meth_start != -1 else (disc_start if disc_start != -1 else len(layer3))
    cards = layer3[cards_start:cards_end].strip()

    if meth_start != -1:
        meth_end = disc_start if disc_start != -1 else len(layer3)
        methodology = layer3[meth_start:meth_end].strip()
    else:
        methodology = ""

    return framing, cards, methodology


def build_pdf(work_dir: Path, out_path: Path):
    if not _HAS_REPORTLAB:
        print("ERROR: reportlab not installed. Run: pip install reportlab --break-system-packages")
        return

    layer1 = _load_text(work_dir / "layer1_extraction.md")
    layer2 = _load_text(work_dir / "layer2_screening.md")
    layer3 = _load_text(work_dir / "layer3_ranked_advice.md")
    disclaimer = _load_text(_ASSETS_DIR / "disclaimer.md")

    # v0.3 appendix checkpoints — optional. Absent files are skipped cleanly so
    # the PDF still builds when the macro stage was not run.
    macro_md = work_dir / "macro_checkpoint.md"
    expectations_md = work_dir / "expectations_checkpoint.md"
    appendix3_md = work_dir / "appendix3_consensus_warning.md"

    framing, cards, methodology = _slice_layer3(layer3)

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

    # 1. Cover  (major boundary → page break)
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

    # 2. Disclaimer (front)  (major boundary → page break after)
    story += [Paragraph("Disclaimer", styles["Heading1"])]
    story += _md_to_paragraphs(disclaimer, styles)
    story += [PageBreak()]

    # 3. Honest framing — single HK-bias statement, homogeneity warning,
    #    stratification-abandoned note, source-selection-method disclosure.
    story += [Paragraph("What This Analysis Is and Is Not", styles["Heading1"])]
    if framing:
        story += _md_to_paragraphs(framing, styles)
    story += [Spacer(1, 5 * mm)]

    # 4. Executive summary
    story += [Paragraph("Executive Summary", styles["Heading1"])]
    story += [Paragraph(
        "This report presents a ranked watchlist of US-listed equities held across "
        "HKMA-approved global funds distributed through Hong Kong private banking channels. "
        "Stocks are filtered to US listings only (including ADRs), screened for fundamental "
        "quality, and ranked by a composite signal combining low-anchor confidence-shrunk "
        "quality and a style-diversity-weighted, exit-liquidity-aware "
        "consensus-with-crowding-discount. The top 15 are organized into three tiers. "
        "All methodology limitations are disclosed below.",
        styles["BodyText"],
    )]
    story += [PageBreak()]

    # 5–8. Layer 1 + Layer 2 (dense; KeepTogether handles orphan titles)
    story += _md_to_paragraphs(layer1, styles)
    story += [Spacer(1, 5 * mm)]
    story += _md_to_paragraphs(layer2, styles)
    story += [Spacer(1, 5 * mm)]

    # 9–10. Layer 3 ranked watchlist + tiers
    story += [Paragraph("Layer 3: Ranked Watchlist", styles["Heading1"])]
    if cards:
        story += _md_to_paragraphs(cards, styles)

    # 11. Appendix 1+2 — per-stock scenarios + macro/sector drivers (major → break)
    if expectations_md.exists() or macro_md.exists():
        story += [PageBreak()]
        story += [Paragraph(
            "Appendix 1+2: Per-Stock Scenarios and Macro/Sector Drivers",
            styles["Heading1"])]
        if macro_md.exists():
            story += _md_to_paragraphs(_load_text(macro_md), styles)
            story += [Spacer(1, 4 * mm)]
        if expectations_md.exists():
            story += _md_to_paragraphs(_load_text(expectations_md), styles)

    # 12. Appendix 3 — over-consensus & false-theme warning + style remediation
    if appendix3_md.exists():
        story += [Spacer(1, 5 * mm)]
        story += [Paragraph(
            "Appendix 3: Over-Consensus, False-Theme Warning and Fund-Style Remediation",
            styles["Heading1"])]
        story += _md_to_paragraphs(_load_text(appendix3_md), styles)

    # 13. Methodology disclosure (major boundary → break)
    if methodology:
        story += [PageBreak()]
        story += _md_to_paragraphs(methodology, styles)

    # 14. Disclaimer (back)  (major boundary → break)
    story += [PageBreak()]
    story += [Paragraph("Disclaimer", styles["Heading1"])]
    story += _md_to_paragraphs(disclaimer, styles)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.build(story)
    print(f"PDF written to {out_path}")


def copy_checkpoints(work_dir: Path, outputs_dir: Path) -> list[str]:
    """D5: copy every present checkpoint .md to the user-visible outputs dir.

    The container work dir is ephemeral; the user can only download what lands
    in outputs_dir. Returns the list of filenames copied.
    """
    outputs_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for name in _CHECKPOINT_FILES:
        src = work_dir / name
        if src.exists():
            shutil.copy2(src, outputs_dir / name)
            copied.append(name)
    if copied:
        print(f"Copied {len(copied)} checkpoint .md file(s) to {outputs_dir}: "
              f"{', '.join(copied)}")
    return copied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default=str(_WORK_DIR))
    ap.add_argument("--out", default=str(_OUTPUTS_DIR / "financial_research_report.pdf"))
    ap.add_argument("--outputs-dir", default=str(_OUTPUTS_DIR),
                    help="User-visible download dir; checkpoint .md files are copied here (D5).")
    ap.add_argument("--no-copy-checkpoints", action="store_true",
                    help="Skip copying checkpoint .md files to the outputs dir.")
    args = ap.parse_args()

    work_dir = Path(args.work_dir)
    build_pdf(work_dir, Path(args.out))
    if not args.no_copy_checkpoints:
        copy_checkpoints(work_dir, Path(args.outputs_dir))


if __name__ == "__main__":
    main()
