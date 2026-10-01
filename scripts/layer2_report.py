"""
Stage 2g: Generate layer2_screening.md from overlap, screen, and fundamental data.

v0.32 additionally reproduces two input-review findings from
`crowding_signals.json`'s `input_review` block, next to the signal each one
qualifies: how many funds were excluded from the exit-liquidity aggregate for
currency reasons (G1.4), and how many accepted funds have thin US exposure
(G2). Both are disclosure only — no number in this file changes because of them.

v0.34 (A5) adds "Passed the screen but could not be scored": stocks that cleared
the screen but have no quality score (fewer than two defined ROE years), read
from `scores_per_stock.json` via --scores. Before v0.34 such a stock simply
never appeared in the ranking, with no word as to why (F7).

v0.4 (B8): "Consensus structure" replaces the style-homogeneity section — how
many independent opinions the run holds (N_eff_run), each fund's weight and
marginal contribution, the common vote floor and the vote-basis coverage, from
`consensus.json` via --consensus; the style distribution remains as a
display-only subsection. "Exit liquidity" replaces the consensus-with-crowding
distribution: days-to-liquidate per ticker, USD-reporting holders only.
"""

import json
import argparse
from pathlib import Path

from paths import work_dir


def _unscored_after_screen(scores: dict | None) -> list[dict]:
    if not isinstance(scores, dict):
        return []
    rows = [s for s in (scores.get("stocks") or {}).values()
            if s.get("status") == "unscored_no_roe"]
    return sorted(rows, key=lambda s: s.get("ticker") or "")


_DTL_ROWS = 15


def build_layer2_md(
    overlap: dict,
    screen_results: dict,
    fundamentals: dict,
    crowding: dict,
    scores: dict | None = None,
    consensus: dict | None = None,
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
    unscored_after = _unscored_after_screen(scores)
    if unscored_after:
        lines += [f"  - of which passed but could not be scored (no ROE score): "
                  f"{len(unscored_after)}"]
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
    lines += ["| Ticker | ROE avg (years; source) | EV/EBITDA | D/E | Quality confidence |"]
    lines += ["|---|---|---|---|---|"]
    for r in passed:
        tkr = r["ticker"]
        rec = fundamentals.get(tkr, {})
        roe = rec.get("roe_5y_avg")
        ev = (rec.get("ev_ebitda") or {}).get("value")
        de = (rec.get("debt_equity") or {}).get("value")
        # v0.34 A5: the confidence the ranking shrinks quality by.
        conf = rec.get("quality_confidence")
        years = rec.get("roe_years")
        provenance = (f" ({years}y; {rec.get('roe_source') or 'n/a'})"
                      if years is not None else "")
        lines += [
            f"| {tkr} "
            f"| {f'{roe:.1%}' if roe is not None else 'n/a'}{provenance} "
            f"| {f'{ev:.1f}' if ev is not None else 'n/a'} "
            f"| {f'{de:.2f}' if de is not None else 'n/a'} "
            f"| {f'{conf:.2f}' if isinstance(conf, (int, float)) else 'n/a'} |"
        ]
    lines += [""]

    # Screened out — fully disclosed
    lines += ["### Screened out", ""]
    lines += ["| Ticker | Reason | Detail |"]
    lines += ["|---|---|---|"]
    for r in failed:
        lines += [f"| {r['ticker']} | {r.get('reason','')} | {r.get('detail','')} |"]
    lines += [""]

    # v0.34 A5: passed the screen, but no quality score — disclosed, not dropped.
    if unscored_after:
        lines += ["### Passed the screen but could not be scored", ""]
        lines += ["These stocks cleared every screen rule but have fewer than two "
                  "defined ROE years, so they have no quality percentile and are not "
                  "ranked. Nothing about them is estimated.", ""]
        lines += ["| Ticker | Reason | Source |"]
        lines += ["|---|---|---|"]
        for u in unscored_after:
            lines += [f"| {u['ticker']} | {u.get('unscored_reason') or 'no ROE score'} "
                      f"| {u.get('roe_source') or u.get('source') or 'n/a'} |"]
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

    # v0.4 B8: how many independent opinions the run holds, and what counts
    # as a vote. Read from consensus.json; nothing here changes a number.
    review = crowding.get("input_review", {}) or {}
    lines += ["## Consensus structure", ""]
    if isinstance(consensus, dict) and consensus.get("funds") is not None:
        tau = consensus.get("vote_floor")
        cov = consensus.get("vote_basis_coverage") or {}
        bands = {}
        for r in consensus.get("stocks", []):
            bands[r.get("band")] = bands.get(r.get("band"), 0) + 1
        lines += [
            f"- Independent opinions in this run: **N_eff = {consensus.get('n_eff_run', 0):.2f}** "
            f"from {consensus.get('n_funds', 0)} funds. Funds that hold the same names share "
            "one opinion's weight; a fund unlike the others keeps a whole one.",
            f"- Vote basis: {consensus.get('vote_basis')} — "
            + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in cov.items())
            + " (fund-stock positions).",
            "- Common vote floor: "
            + (f"{tau:.2%} (set by {', '.join(consensus.get('vote_floor_set_by') or [])})"
               if isinstance(tau, (int, float)) else "off (sensitivity run)"),
            "- Consensus bands: " + ", ".join(
                f"{b} {bands.get(b, 0)}" for b in ("majority", "plural", "single", "none")),
        ]
        anchored = consensus.get("anchored_core") or []
        if anchored:
            lines += [f"- Benchmark-anchored core (held by most funds, at or below benchmark "
                      f"weight; not ranked): {', '.join(anchored)}"]
        lines += ["", "| Fund | Weight ω | Marginal contribution | Benchmark proxy |",
                  "|---|---|---|---|"]
        for f in consensus.get("funds", []):
            lines += [f"| {f.get('fund_id')} | {f.get('omega', 0):.3f} "
                      f"| {f.get('marginal_contribution', 0):.3f} "
                      f"| {f.get('benchmark_proxy') or '— (presence votes)'} |"]
        lowest = min(consensus.get("funds", []) or [{}],
                     key=lambda f: f.get("marginal_contribution", 0.0))
        if lowest.get("fund_id"):
            lines += ["", f"- Lowest marginal contribution: {lowest['fund_id']} "
                      f"({lowest.get('marginal_contribution', 0):.3f} of an opinion) — the "
                      "upload that adds least; Appendix 3 suggests replacing it with a "
                      "dissimilar fund."]
    else:
        lines += ["- consensus.json was not supplied to this stage; the consensus structure "
                  "is not reported."]
    lines += [""]

    # A3 (display only since v0.4): the style distribution, kept next to the
    # consensus it describes. It enters no number.
    homo = crowding.get("homogeneity", {})
    lines += ["### Fund-style distribution (display only)", ""]
    if not homo.get("labelled"):
        lines += ["- Fund styles were not labelled this run."]
    else:
        dist = homo.get("style_distribution", {})
        dist_str = ", ".join(f"{k}: {v}" for k, v in dist.items()) or "n/a"
        lines += [f"- Style distribution of input funds: {dist_str}"]
        lines += [f"- Dominant style: {homo.get('dominant_style')} "
                  f"({homo.get('dominant_share', 0):.0%} of labelled funds)"]
        if homo.get("is_homogeneous"):
            lines += ["- ⚠ HOMOGENEOUS INPUT — most funds share one style. The independence "
                      "weighting above already counts such funds as fewer opinions; see "
                      "Appendix 3 for which kind of fund to add."]

    # G2: the same false-consensus problem seen from the exposure angle.
    thin = review.get("thin_us_exposure", {}) or {}
    n_thin = thin.get("n_thin", 0)
    if n_thin:
        thin_names = ", ".join(
            f"{f.get('fund_id')} ({(f.get('weight_kept') or 0):.0%})"
            for f in thin.get("funds", [])
        )
        lines += [
            f"- ⚠ THIN US EXPOSURE — {n_thin} of {thin.get('n_funds', 0)} accepted "
            f"fund(s) hold only 20–35% of AUM in US equity: {thin_names}. Their votes "
            "count in full (a vote is about a position, not about exposure), so "
            "consensus in this run partly rests on marginal US sleeves.",
        ]
    elif thin:
        lines += ["- US-exposure depth: no accepted fund is thin "
                  "(all above 35% US-equity weight)."]
    lines += [""]

    # v0.4 B8: exit liquidity — the one crowding question factsheets can answer.
    lines += ["## Exit liquidity", ""]
    with_dtl = sorted((x for x in signals.values()
                       if isinstance(x.get("days_to_liquidate"), (int, float))),
                      key=lambda x: (-x["days_to_liquidate"], x["ticker"]))
    no_data = sum(1 for x in signals.values()
                  if not isinstance(x.get("days_to_liquidate"), (int, float)))
    threshold = crowding.get("dtl_threshold", 10.0)
    crowded = [x for x in with_dtl if x.get("is_exit_crowded")]
    lines += [
        f"- Days-to-liquidate: the trading days of average volume the holders that report "
        f"AUM in USD would need to sell together. {len(with_dtl)} ticker(s) have a figure; "
        f"{no_data} have no liquidity data (no USD-reported AUM among their holders, or "
        "no ADV).",
        f"- Exit-crowded (≥ {threshold:g} days, an uncalibrated line): "
        + (", ".join(x["ticker"] for x in crowded) if crowded else "none")
        + ". The coherence overlay demotes an exit-crowded stock one display tier; "
        "it never changes a rank.",
    ]
    if with_dtl:
        lines += ["", "| Ticker | Days to liquidate | USD-reporting holders | Exit-crowded |",
                  "|---|---|---|---|"]
        for x in with_dtl[:_DTL_ROWS]:
            lines += [f"| {x['ticker']} | {x['days_to_liquidate']:.1f} "
                      f"| {x.get('n_usd_aum_holders', 'n/a')} of {x.get('n_holders', 'n/a')} "
                      f"| {'yes' if x.get('is_exit_crowded') else '—'} |"]
        if len(with_dtl) > _DTL_ROWS:
            lines += [f"", f"_{len(with_dtl) - _DTL_ROWS} more with lower figures in "
                           "crowding_signals.json._"]
    lines += [""]

    # G1.4: state the currency exclusions where the liquidity figures are shown —
    # a missing figure is otherwise indistinguishable from missing market data.
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
            "this pipeline** — and their holdings still count in full toward overlap "
            "and consensus. Stocks held only by excluded funds have no liquidity data "
            "above.",
        ]
    elif by_currency:
        lines += ["- No fund was excluded from the exit-liquidity aggregate for "
                  "currency reasons; every accepted fund reports AUM in USD."]
    else:
        lines += ["- Fund AUM was not supplied to this stage, so no exit-liquidity "
                  "aggregate was built; no ticker has a days-to-liquidate figure."]
    lines += [""]

    lines += ["## Next layer", ""]
    lines += [f"{n_pass} tickers passed the screen; those with a quality score and at least "
              "one qualifying vote are ranked in Layer 3."]

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlap", required=True)
    ap.add_argument("--screen", required=True)
    ap.add_argument("--fundamentals", required=True)
    ap.add_argument("--crowding", required=True)
    ap.add_argument("--scores", help="scores_per_stock.json (v0.34 A5): lists stocks that "
                                     "passed the screen but could not be scored.")
    ap.add_argument("--consensus", help="consensus.json (v0.4 B8): the consensus structure.")
    ap.add_argument("--out", default=str(work_dir() / "layer2_screening.md"),
                    help="Default: the work directory (paths.py).")
    args = ap.parse_args()

    overlap = json.loads(Path(args.overlap).read_text(encoding="utf-8"))
    screen = json.loads(Path(args.screen).read_text(encoding="utf-8"))
    fundamentals = json.loads(Path(args.fundamentals).read_text(encoding="utf-8"))
    crowding = json.loads(Path(args.crowding).read_text(encoding="utf-8"))
    scores = (json.loads(Path(args.scores).read_text(encoding="utf-8"))
              if args.scores and Path(args.scores).exists() else None)

    consensus = (json.loads(Path(args.consensus).read_text(encoding="utf-8"))
                 if args.consensus and Path(args.consensus).exists() else None)

    md = build_layer2_md(overlap, screen, fundamentals, crowding, scores, consensus)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Layer 2 report written to {args.out}")


if __name__ == "__main__":
    main()
