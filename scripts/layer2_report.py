"""
Stage 2g: Generate layer2_screening.md from overlap, screen, and fundamental data.

v0.32 additionally reproduces two input-review findings from
`crowding_signals.json`'s `input_review` block, next to the signal each one
qualifies: how many funds were excluded from the exit-liquidity aggregate for
currency reasons (G1.4), and how many accepted funds have thin US exposure
(G2). Both are disclosure only — no number in this file changes because of them.
"""

import json
import argparse
from pathlib import Path


def build_layer2_md(
    overlap: dict,
    screen_results: dict,
    fundamentals: dict,
    crowding: dict,
) -> str:
    overlap_rows = overlap.get("overlap", [])
    results = screen_results.get("results", [])
    passed = [r for r in results if r.get("passed")]
    failed = [r for r in results if not r.get("passed")]
    unscored = screen_results.get("unscored", [])
    signals = {r["ticker"]: r for r in crowding.get("signals", [])}

    n_total = overlap.get("n_tickers", 0)
    n_pass = len(passed)
    n_fail = len(failed)
    n_unscored = len(unscored)

    lines = ["# Layer 2: Overlap and Quality Screen", ""]

    lines += ["## Universe state", ""]
    lines += [f"- Entered Layer 2: {n_total} tickers"]
    lines += [f"- Passed quality screen: {n_pass} ({n_pass/max(n_total,1):.0%})"]
    lines += [f"- Failed quality screen: {n_fail}"]
    lines += [f"- Unscored (data unavailable): {n_unscored}"]
    lines += [""]

    # Overlap matrix (top 30)
    lines += ["## Overlap matrix (top 30 by funds holding)", ""]
    lines += ["| Ticker | Name | Industry | # funds | Sum weight | Avg weight | Max weight |"]
    lines += ["|---|---|---|---|---|---|---|"]
    for r in overlap_rows[:30]:
        lines += [
            f"| {r['ticker']} | {r.get('name','')} | {r.get('industry','')} "
            f"| {r['n_funds_holding']} "
            f"| {r.get('sum_of_weights',0):.1%} "
            f"| {r.get('avg_weight',0):.1%} "
            f"| {r.get('max_weight',0):.1%} |"
        ]
    lines += [""]

    # Quality screen results — passed
    lines += ["## Quality screen results", ""]
    lines += ["### Passed", ""]
    lines += ["| Ticker | ROE 5y avg | EV/EBITDA | D/E | Confidence |"]
    lines += ["|---|---|---|---|---|"]
    for r in passed:
        tkr = r["ticker"]
        rec = fundamentals.get(tkr, {})
        roe = rec.get("roe_5y_avg")
        ev = (rec.get("ev_ebitda") or {}).get("value")
        de = (rec.get("debt_equity") or {}).get("value")
        conf = rec.get("overall_confidence", "")
        lines += [
            f"| {tkr} "
            f"| {f'{roe:.1%}' if roe is not None else 'n/a'} "
            f"| {f'{ev:.1f}' if ev is not None else 'n/a'} "
            f"| {f'{de:.2f}' if de is not None else 'n/a'} "
            f"| {f'{conf:.2f}' if conf else 'n/a'} |"
        ]
    lines += [""]

    # Screened out — fully disclosed
    lines += ["### Screened out", ""]
    lines += ["| Ticker | Reason | Detail |"]
    lines += ["|---|---|---|"]
    for r in failed:
        lines += [f"| {r['ticker']} | {r.get('reason','')} | {r.get('detail','')} |"]
    lines += [""]

    # Unscored
    if unscored:
        lines += ["### Unscored (data unavailable)", ""]
        lines += ["| Ticker | Reason |"]
        lines += ["|---|---|"]
        for u in unscored:
            lines += [f"| {u['ticker']} | {u.get('reason','')} |"]
        lines += [""]

    # Data quality summary
    edgar_count = sum(1 for r in results if r.get("source") == "edgar")
    yf_count = sum(1 for r in results if r.get("source") == "yfinance")
    lines += ["## Data quality summary", ""]
    lines += [f"- EDGAR coverage: {edgar_count} tickers"]
    lines += [f"- yfinance coverage: {yf_count} tickers"]
    lines += ["- See `data_provenance.json` for conflict log"]
    lines += [""]

    # Crowding signal distribution
    sig_vals = [s["signal"] for s in signals.values() if "signal" in s]
    if sig_vals:
        lines += ["## Consensus-with-crowding-discount distribution", ""]
        lines += [f"- Range: {min(sig_vals):.3f} – {max(sig_vals):.3f}"]
        lines += [f"- Mean: {sum(sig_vals)/len(sig_vals):.3f}"]
        high_crowd = sum(1 for s in signals.values() if s.get("is_high_crowding"))
        lines += [f"- High-crowding stocks (discount >= 30%): {high_crowd}"]
        # A2: liquidity-inclusive vs NAV-only coverage (v0.3).
        liq_inc = sum(1 for s in signals.values()
                      if s.get("crowding_label") == "liquidity-inclusive")
        nav_only = sum(1 for s in signals.values()
                       if s.get("crowding_label") == "NAV-only")
        lines += [f"- Crowding figures: {liq_inc} liquidity-inclusive (days-to-liquidate "
                  f"applied), {nav_only} NAV-only (AUM/ADV missing — fell back to "
                  "pure-weight discount)"]
        lines += [""]

    # G1.4: state the currency exclusions where the crowding labels are shown —
    # a NAV-only label is otherwise indistinguishable from missing market data.
    review = crowding.get("input_review", {}) or {}
    currency = review.get("currency", {}) or {}
    lines += ["## Reporting currency and the exit-liquidity aggregate", ""]
    by_currency = currency.get("by_currency") or {}
    if by_currency:
        lines += ["- Reporting currency of accepted funds: "
                  + ", ".join(f"{k}: {v}" for k, v in by_currency.items())]
    n_excluded = currency.get("n_excluded_for_currency", 0)
    if n_excluded:
        excluded_names = ", ".join(
            f"{f.get('fund_id')} ({f.get('currency') or 'unstated'})"
            for f in currency.get("excluded_funds", [])
        )
        lines += [
            f"- ⚠ {n_excluded} fund(s) excluded from the days-to-liquidate aggregate "
            f"because their AUM is not reported in USD: {excluded_names}.",
            "- Average daily traded value is always USD, so admitting a non-USD AUM "
            "would overstate days-to-liquidate by roughly the exchange rate. Those "
            "funds are excluded rather than converted — **no FX conversion exists in "
            "this pipeline** — and their holdings still count in full toward overlap, "
            "consensus and style diversity. Stocks held only by excluded funds are "
            "labelled NAV-only above.",
        ]
    elif by_currency:
        lines += ["- No fund was excluded from the exit-liquidity aggregate for "
                  "currency reasons; every accepted fund reports AUM in USD."]
    else:
        lines += ["- Fund AUM was not supplied to this stage, so no exit-liquidity "
                  "aggregate was built; all crowding figures are NAV-only."]
    lines += [""]

    # A3: input-set style homogeneity state (v0.3).
    homo = crowding.get("homogeneity", {})
    lines += ["## Input-set style homogeneity (consensus informativeness)", ""]
    if not homo.get("labelled"):
        lines += ["- Fund styles were not labelled this run; style-diversity "
                  "weighting was not applied and consensus is reported unweighted."]
    else:
        dist = homo.get("style_distribution", {})
        dist_str = ", ".join(f"{k}: {v}" for k, v in dist.items()) or "n/a"
        lines += [f"- Style distribution of input funds: {dist_str}"]
        lines += [f"- Dominant style: {homo.get('dominant_style')} "
                  f"({homo.get('dominant_share', 0):.0%} of labelled funds)"]
        if homo.get("is_homogeneous"):
            lines += ["- ⚠ HOMOGENEOUS INPUT — the input is dominated by a single "
                      "style. Consensus in this run is largely tautological "
                      "(same-mandate funds buying the same names) and therefore "
                      "carries little independent information. See Appendix 3 for "
                      "remediation (which fund styles to add)."]
        else:
            lines += ["- Input spans multiple styles; cross-style agreement is "
                      "treated as more informative than within-style agreement."]

    # G2: the same false-consensus problem seen from the exposure angle. Reported
    # next to the style state because both qualify the SAME signal.
    thin = review.get("thin_us_exposure", {}) or {}
    n_thin = thin.get("n_thin", 0)
    if n_thin:
        thin_names = ", ".join(
            f"{f.get('fund_id')} ({(f.get('weight_kept') or 0):.0%})"
            for f in thin.get("funds", [])
        )
        lines += [
            f"- ⚠ THIN US EXPOSURE — {n_thin} of {thin.get('n_funds', 0)} accepted "
            f"fund(s) hold only 20–35% of AUM in US equity: {thin_names}. Their "
            "consensus contribution is unchanged (the signal counts funds, not "
            "exposure), so consensus in this run partly rests on marginal US sleeves.",
        ]
    elif thin:
        lines += ["- US-exposure depth: no accepted fund is thin "
                  "(all above 35% US-equity weight)."]
    lines += [""]

    lines += ["## Next layer", ""]
    lines += [f"{n_pass} tickers advance to Layer 3 for composite ranking."]

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlap", required=True)
    ap.add_argument("--screen", required=True)
    ap.add_argument("--fundamentals", required=True)
    ap.add_argument("--crowding", required=True)
    ap.add_argument("--out", default="/home/claude/work/layer2_screening.md")
    args = ap.parse_args()

    overlap = json.loads(Path(args.overlap).read_text(encoding="utf-8"))
    screen = json.loads(Path(args.screen).read_text(encoding="utf-8"))
    fundamentals = json.loads(Path(args.fundamentals).read_text(encoding="utf-8"))
    crowding = json.loads(Path(args.crowding).read_text(encoding="utf-8"))

    md = build_layer2_md(overlap, screen, fundamentals, crowding)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Layer 2 report written to {args.out}")


if __name__ == "__main__":
    main()
