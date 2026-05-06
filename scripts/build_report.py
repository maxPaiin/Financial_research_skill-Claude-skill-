"""
Stage 10: Assemble the final PDF report from all stage outputs.

Reads from /home/claude/work/:
  holdings.json
  scores_strategies.json
  fund_scores.json
  risk_report.json
  rankings.json
  backtest.json
  forward_view.md      (Stage 9 LLM output)
  macro.json

Writes to: --out path (typically /mnt/user-data/outputs/financial_research_report.pdf)

Required: pip install reportlab matplotlib --break-system-packages
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from io import BytesIO

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image, KeepTogether,
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    print("ERROR: reportlab not installed. Run: pip install reportlab --break-system-packages", file=sys.stderr)
    sys.exit(2)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError:
    plt = None


# Try to register a CJK font
CJK_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/wenquanyi/wqy-zenhei/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
CJK_FONT_NAME = "Helvetica"   # fallback
for p in CJK_PATHS:
    if Path(p).exists():
        try:
            pdfmetrics.registerFont(TTFont("CJK", p, subfontIndex=0))
            CJK_FONT_NAME = "CJK"
            break
        except Exception:
            pass


# Brand colors
COLORS = {
    "growth": colors.HexColor("#2E7D32"),
    "conservative": colors.HexColor("#1565C0"),
    "risk_avoidance": colors.HexColor("#6A1B9A"),
    "warning": colors.HexColor("#C62828"),
    "neutral": colors.HexColor("#424242"),
    "row_alt": colors.HexColor("#f5f5f5"),
}


def make_styles():
    s = getSampleStyleSheet()
    s.add(ParagraphStyle(name="CJKBody", fontName=CJK_FONT_NAME, fontSize=10, leading=14))
    s.add(ParagraphStyle(name="CJKSmall", fontName=CJK_FONT_NAME, fontSize=8, leading=11))
    s.add(ParagraphStyle(name="CJKHeader", fontName=CJK_FONT_NAME, fontSize=14, leading=18,
                         spaceBefore=8, spaceAfter=4, textColor=COLORS["neutral"]))
    s.add(ParagraphStyle(name="CJKTitle", fontName=CJK_FONT_NAME, fontSize=20, leading=26,
                         alignment=1, spaceAfter=12))
    s.add(ParagraphStyle(name="CJKDisclaimer", fontName=CJK_FONT_NAME, fontSize=9, leading=13,
                         textColor=COLORS["warning"], borderColor=COLORS["warning"],
                         borderWidth=1, borderPadding=8))
    return s


def equity_curve_image(runs_for_strategy, strategy_name, color_hex):
    """Render equity curves for one strategy across periods to a BytesIO PNG."""
    if plt is None:
        return None
    fig, ax = plt.subplots(figsize=(6, 3))
    for r in runs_for_strategy:
        if r.get("error") or not r.get("equity_curve"):
            continue
        dates = [p["date"] for p in r["equity_curve"]]
        navs = [p["nav"] for p in r["equity_curve"]]
        ax.plot(range(len(navs)), navs, label=r["period"])
    ax.set_title(f"{strategy_name.title()} strategy — equity curves")
    ax.set_xlabel("months")
    ax.set_ylabel("NAV (start = 1.0)")
    ax.legend()
    ax.grid(True, alpha=0.3)
    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def build(work_dir: Path, out_path: Path, disclaimer_text: str):
    styles = make_styles()
    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
    )
    story = []

    # --- Load all stage outputs ---
    def load(fname):
        p = work_dir / fname
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None

    holdings = load("holdings.json") or {}
    fund_scores = load("fund_scores.json") or {"funds": []}
    risk_report = load("risk_report.json") or {}
    rankings = load("rankings.json") or {}
    backtest = load("backtest.json") or {"runs": []}
    macro = load("macro.json") or {}
    forward_md = (work_dir / "forward_view.md")
    forward_text = forward_md.read_text(encoding="utf-8") if forward_md.exists() else ""

    n_funds = len(holdings.get("funds", []))
    n_stocks = holdings.get("universe_size", 0)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # --- Cover ---
    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph("Stock Fund Research Report<br/>股票型基金研究報告", styles["CJKTitle"]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        f"{n_funds} funds · {n_stocks} unique stocks · generated {timestamp}<br/>"
        f"{n_funds} 檔基金 · {n_stocks} 檔個股 · 生成時間 {timestamp}",
        styles["CJKBody"],
    ))
    story.append(Spacer(1, 30 * mm))
    story.append(Paragraph(
        "Generated by Claude — AI Analysis Only. Not investment advice.<br/>"
        "由 Claude 生成 — 僅為 AI 分析,不可作為投資建議。",
        styles["CJKSmall"],
    ))
    story.append(PageBreak())

    # --- Disclaimer (front) ---
    story.append(Paragraph("Disclaimer / 免責聲明", styles["CJKHeader"]))
    story.append(Paragraph(disclaimer_text.replace("\n", "<br/>"), styles["CJKDisclaimer"]))
    story.append(PageBreak())

    # --- Executive summary ---
    story.append(Paragraph("Executive Summary / 執行摘要", styles["CJKHeader"]))
    top_run_per_strat = {}
    for r in backtest.get("runs", []):
        if r.get("error"):
            continue
        s = r.get("strategy")
        if s not in top_run_per_strat or (r.get("cagr", -1) > top_run_per_strat[s].get("cagr", -1)):
            top_run_per_strat[s] = r

    summary_lines = [
        f"Analyzed {n_funds} stock-type funds covering {n_stocks} unique stocks.",
        f"分析 {n_funds} 檔股票型基金,共涵蓋 {n_stocks} 檔個股。",
        "",
    ]
    for strat, r in top_run_per_strat.items():
        summary_lines.append(
            f"<b>{strat.title()}</b>: best window {r.get('period')} CAGR "
            f"{r.get('cagr', 0)*100:.1f}%, Sharpe {r.get('sharpe', 0):.2f}, "
            f"Max DD {r.get('max_drawdown', 0)*100:.1f}%."
        )
    story.append(Paragraph("<br/>".join(summary_lines), styles["CJKBody"]))
    story.append(PageBreak())

    # --- Fund profiles ---
    for f in fund_scores.get("funds", []):
        story.append(Paragraph(f"Fund Profile: {f.get('fund_name')}", styles["CJKHeader"]))
        story.append(Paragraph(
            f"Type: {f.get('fund_type')} · Currency: {f.get('currency')} · "
            f"Holdings scored: {f.get('n_holdings_scored')}",
            styles["CJKSmall"],
        ))
        ss = f.get("strategy_scores") or {}
        scores_table = [
            ["Metric (指標)", "Score (分數)"],
            ["Industry score (行業分)", f"{f.get('industry_score', 'n/a')}"],
            ["Growth score (成長分)", f"{f.get('growth_score', 'n/a')}"],
            ["Quality & Value (質量價值)", f"{f.get('quality_value_score', 'n/a')}"],
            ["Growth strategy (成長策略)", f"{ss.get('growth', 'n/a')}"],
            ["Conservative strategy (穩健策略)", f"{ss.get('conservative', 'n/a')}"],
            ["Risk-avoidance (風險規避)", f"{ss.get('risk_avoidance', 'n/a')}"],
        ]
        t = Table(scores_table, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), CJK_FONT_NAME, 9),
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["neutral"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLORS["row_alt"]]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(t)
        story.append(Spacer(1, 4 * mm))

        if f.get("max_industry_breach_30pct"):
            story.append(Paragraph(
                f"⚠ Industry concentration: {f.get('max_industry')} = "
                f"{f.get('max_industry_weight', 0)*100:.1f}% (exceeds 30% threshold)",
                styles["CJKDisclaimer"],
            ))
        story.append(PageBreak())

    # --- Cross-fund overlap ---
    story.append(Paragraph("Cross-Fund Overlap / 跨基金重疊", styles["CJKHeader"]))
    overlap = risk_report.get("overlap", [])[:20]
    if overlap:
        rows = [["Ticker", "Name", "# funds", "Max weight"]]
        for o in overlap:
            rows.append([
                o["ticker"],
                (o.get("name") or "")[:30],
                str(o["n_funds_holding"]),
                f"{o['max_weight']*100:.2f}%",
            ])
        t = Table(rows, hAlign="LEFT")
        t.setStyle(TableStyle([
            ("FONT", (0, 0), (-1, -1), CJK_FONT_NAME, 8),
            ("BACKGROUND", (0, 0), (-1, 0), COLORS["neutral"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLORS["row_alt"]]),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(t)
    else:
        story.append(Paragraph("No cross-fund overlap detected. / 未偵測到跨基金重疊。", styles["CJKBody"]))
    story.append(PageBreak())

    # --- Backtest results ---
    story.append(Paragraph("Backtest Results / 回測結果", styles["CJKHeader"]))
    bt_rows = [["Strategy", "Period", "CAGR", "Sharpe", "Max DD", "Win Rate"]]
    for r in backtest.get("runs", []):
        if r.get("error"):
            continue
        bt_rows.append([
            r["strategy"], r["period"],
            f"{r.get('cagr', 0)*100:.2f}%",
            f"{r.get('sharpe', 0):.2f}",
            f"{r.get('max_drawdown', 0)*100:.2f}%",
            f"{r.get('win_rate', 0)*100:.1f}%",
        ])
    t = Table(bt_rows, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), CJK_FONT_NAME, 9),
        ("BACKGROUND", (0, 0), (-1, 0), COLORS["neutral"]),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLORS["row_alt"]]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    # Equity curve charts (one per strategy)
    by_strat = {}
    for r in backtest.get("runs", []):
        by_strat.setdefault(r.get("strategy"), []).append(r)
    for strat, runs in by_strat.items():
        img_buf = equity_curve_image(runs, strat, COLORS.get(strat, COLORS["neutral"]).hexval())
        if img_buf:
            story.append(Image(img_buf, width=160 * mm, height=70 * mm))
            story.append(Spacer(1, 2 * mm))

    story.append(PageBreak())

    # --- Forward view ---
    story.append(Paragraph("Forward Investment View / 前瞻投資觀點", styles["CJKHeader"]))
    if forward_text:
        # ReportLab doesn't natively render markdown; do simple substitutions
        for para in forward_text.split("\n\n"):
            para_clean = para.replace("**", "<b>").replace("**", "</b>").replace("\n", "<br/>")
            story.append(Paragraph(para_clean, styles["CJKBody"]))
            story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph("(Stage 9 forward view not generated.)", styles["CJKSmall"]))
    story.append(PageBreak())

    # --- Methodology notes ---
    story.append(Paragraph("Methodology Notes / 方法論說明", styles["CJKHeader"]))
    method = (
        "Strategy weights — Growth: 0.20·industry + 0.60·growth + 0.20·quality_value + 0.10·momentum. "
        "Conservative: 0.30·industry + 0.20·growth + 0.50·quality_value. "
        "Risk-avoidance: 0.40·industry + 0.10·growth + 0.50·quality_value − concentration penalty (max 20).<br/><br/>"
        "Backtest uses monthly rebalancing, equal-weight top-20% selection, "
        "−10% per-stock stop-loss, 30% industry cap, 0.10% transaction cost per rebalance.<br/><br/>"
        "Limitations: current fundamentals used as proxy throughout the backtest window (lookahead bias); "
        "yfinance is survivorship-biased; stop-loss applied at month-end resolution; "
        "FX not modeled for cross-market holdings. See full methodology in the skill's "
        "<i>references/backtest_methodology.md</i>."
    )
    story.append(Paragraph(method, styles["CJKBody"]))
    story.append(PageBreak())

    # --- Disclaimer (back) ---
    story.append(Paragraph("Disclaimer / 免責聲明", styles["CJKHeader"]))
    story.append(Paragraph(disclaimer_text.replace("\n", "<br/>"), styles["CJKDisclaimer"]))

    doc.build(story)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--disclaimer", default=None,
                    help="Path to disclaimer.md (defaults to skill's assets/disclaimer.md)")
    args = ap.parse_args()

    work_dir = Path(args.work_dir)
    if args.disclaimer:
        disclaimer_text = Path(args.disclaimer).read_text(encoding="utf-8")
    else:
        # Try the standard location
        skill_dir = Path(__file__).parent.parent
        disclaimer_path = skill_dir / "assets" / "disclaimer.md"
        if disclaimer_path.exists():
            disclaimer_text = disclaimer_path.read_text(encoding="utf-8")
        else:
            disclaimer_text = (
                "This is an AI-generated analysis and should NOT be used as investment advice. "
            )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    build(work_dir, out_path, disclaimer_text)
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()