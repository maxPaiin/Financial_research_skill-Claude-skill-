"""
Generated fund factsheets for the intake and runner tests (v0.4 C2/C3/C6).

Tests never open a real fund PDF (spec rule 5). These helpers draw small,
realistic factsheets with reportlab — a title, key facts, and a holdings table
under a "Top 10 Holdings" heading — so extraction can be asserted exactly.
"""

from __future__ import annotations

from pathlib import Path

DEFAULT_HOLDINGS = [
    ("Apple Inc", "AAPL", 7.1), ("Microsoft Corp", "MSFT", 6.4), ("NVIDIA Corp", "NVDA", 5.9),
    ("Broadcom Inc", "AVGO", 4.2), ("Alphabet Inc Class A", "GOOGL", 3.8),
    ("Taiwan Semiconductor Manufacturing", "2330 TT", 3.5), ("Oracle Corp", "ORCL", 3.1),
    ("ASML Holding NV", "ASML", 2.9), ("Salesforce Inc", "CRM", 2.6), ("Adobe Inc", "ADBE", 2.4),
]


def have_reportlab() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


def make_factsheet(path: Path, *, fund_name: str = "Global Technology Equity Fund",
                   asof: str = "Data as of 31 March 2026",
                   facts: list[str] | None = None,
                   holdings: list[tuple] | None = None,
                   heading: str = "Top 10 Holdings",
                   columns: tuple[str, ...] = ("Holding", "Ticker", "Weight (%)"),
                   filler_pages: int = 0) -> Path:
    """An English factsheet PDF with a gridded holdings table."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    facts = facts if facts is not None else [
        "Base currency: USD",
        "Fund size: USD 4,200 million",
        "Benchmark: MSCI AC World Information Technology Index",
        "ISIN: LU0000000001",
        "NAV per share: USD 87.31",
    ]
    rows = holdings if holdings is not None else DEFAULT_HOLDINGS
    styles = getSampleStyleSheet()
    story = [Paragraph(fund_name, styles["Title"]), Paragraph(asof, styles["Normal"]),
             Spacer(1, 8)]
    story += [Paragraph(line, styles["Normal"]) for line in facts]
    for _ in range(filler_pages):
        story += [PageBreak(), Paragraph("Market commentary", styles["Heading2"]),
                  Paragraph("The portfolio manager comments on the quarter. " * 20,
                            styles["Normal"])]
    story += [Spacer(1, 12), Paragraph(heading, styles["Heading2"])]
    data = [list(columns)] + [[str(c) for c in r] for r in rows]
    table = Table(data)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    story.append(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(path), pagesize=A4).build(story)
    return path


# TrueType CJK fonts embed a Unicode map, as real HK factsheets do; reportlab's
# built-in CID fonts do not, and their text comes back garbled.
_CJK_TTF_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def _cjk_font() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont
    for candidate in _CJK_TTF_CANDIDATES:
        if Path(candidate).exists():
            try:
                pdfmetrics.registerFont(TTFont("CJKTest", candidate))
                return "CJKTest"
            except Exception:  # noqa: BLE001 — try the next one
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("MSung-Light"))
    return "MSung-Light"


def make_cjk_factsheet(path: Path) -> Path:
    """A Traditional Chinese factsheet (best effort: a TrueType CJK font when the
    machine has one, else a CID font whose text may not extract)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    font = _cjk_font()
    style = ParagraphStyle("zh", fontName=font, fontSize=11, leading=15)
    story = [Paragraph("環球科技股票基金", style),
             Paragraph("資料截至 2026年3月31日", style),
             Paragraph("基本貨幣：美元", style),
             Paragraph("基金規模：美元 42.0 億", style),
             Paragraph("基準指數：MSCI AC World Information Technology Index", style),
             Spacer(1, 12), Paragraph("十大持倉", style)]
    data = [["名稱", "比重 (%)"], ["蘋果", "7.1"], ["微軟", "6.4"], ["輝達", "5.9"],
            ["台積電", "3.5"], ["博通", "4.2"]]
    table = Table(data)
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), font),
                               ("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    story.append(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(path), pagesize=A4).build(story)
    return path


def make_upload_set(folder: Path, n: int = 7) -> list[Path]:
    """n distinct factsheets, ready to zip or validate."""
    out = []
    for i in range(1, n + 1):
        out.append(make_factsheet(folder / f"fund_{i:02d}.pdf",
                                  fund_name=f"Global Equity Fund {i}"))
    return out
