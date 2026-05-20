"""
Stage 2g: Generate layer2_screening.md from overlap, screen, and fundamental data.
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
