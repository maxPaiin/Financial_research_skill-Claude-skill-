"""
Stage 1d: Generate layer1_extraction.md from holdings.json.

Writes a structured markdown summary of what was extracted in Layer 1.

v0.32 (G4): the report opens with a single consolidated **input review** block
carrying every finding about what the user submitted — accepted/rejected funds
and their reasons, reporting currency per fund and how many funds that excludes
from the exit-liquidity aggregate (G1), thin-US-exposure flags (G2), Stage 0
regional advisories (G3), and the input set's style distribution (A3). One block
rather than warnings scattered across sections: the user reviews their input
once, and the consensus caveat sits next to the evidence for it.
"""

import json
import argparse
from pathlib import Path

# The homogeneity definition is canonical in crowding_signal.py (A3). Layer 1
# runs before Stage 2f, so it recomputes the state from holdings.json rather
# than reading crowding_signals.json — but it must use the same definition, so
# the functions are imported instead of reimplemented.
from crowding_signal import fund_style_map, homogeneity_report


def _currency_label(fund: dict) -> str:
    """Display form of a fund's reporting currency (G1.4)."""
    currency = fund.get("currency")
    if isinstance(currency, str) and currency:
        return currency
    raw = fund.get("currency_raw")
    if raw:
        return f"unstated (factsheet said '{raw}')"
    return "unstated"


def _input_review(data: dict, stage0: dict | None) -> list[str]:
    """G4: the single input-review block. Every finding lands here."""
    funds = data.get("funds", [])
    valid_funds = [f for f in funds if not f.get("rejected")]
    rejected_funds = [f for f in funds if f.get("rejected")]

    lines = ["## Input review", ""]
    lines += ["A single review of the funds you submitted. Everything below is a "
              "property of the *input set*, not of any individual stock."]
    lines += [""]

    # --- Funds accepted / rejected (existing behaviour) ---
    lines += ["### Funds", ""]
    lines += [f"- Funds uploaded: {len(funds)}"]
    lines += [f"- Funds successfully parsed: {len(valid_funds)}"]
    if rejected_funds:
        lines += [f"- Funds rejected (insufficient holdings data): {len(rejected_funds)}"]
        for f in rejected_funds:
            lines += [f"  - {f['fund_id']} ({f.get('fund_name', 'unknown')}): "
                      f"{f.get('rejection_reason')}"]
    else:
        lines += ["- Funds rejected: 0"]
    lines += [""]

    # --- G1: reporting currency + exit-liquidity exclusions ---
    census: dict[str, int] = {}
    for f in valid_funds:
        code = f.get("currency") if isinstance(f.get("currency"), str) else None
        census[code or "unstated"] = census.get(code or "unstated", 0) + 1
    excluded = [f for f in valid_funds if f.get("currency") != "USD"]

    lines += ["### Reporting currency", ""]
    census_str = ", ".join(f"{k}: {v}" for k, v in
                           sorted(census.items(), key=lambda kv: (-kv[1], kv[0])))
    lines += [f"- Reporting currency of accepted funds: {census_str or 'n/a'}"]
    if excluded:
        names = ", ".join(
            f"{f['fund_id']} ({_currency_label(f)})" for f in excluded
        )
        lines += [
            f"- ⚠ {len(excluded)} of {len(valid_funds)} accepted fund(s) do not report "
            f"AUM in USD: {names}.",
            "- Those funds are **excluded from the days-to-liquidate (exit-liquidity) "
            "aggregate**, because average daily traded value is always USD and mixing "
            "units would overstate days-to-liquidate by roughly the exchange rate. "
            "**No FX conversion is performed anywhere in this pipeline.** Their "
            "holdings still count in full toward overlap, consensus and style "
            "diversity — only their AUM is set aside. A stock held solely by such "
            "funds is reported with NAV-only crowding.",
        ]
    else:
        lines += ["- All accepted funds report AUM in USD; none excluded from the "
                  "exit-liquidity aggregate."]
    lines += [""]

    # --- G2: thin US exposure ---
    thin = [f for f in valid_funds if f.get("thin_us_exposure")]
    lines += ["### US-exposure depth", ""]
    if thin:
        lines += [
            f"- ⚠ {len(thin)} of {len(valid_funds)} accepted fund(s) hold only "
            "20–35% of AUM in US equity after filtering:",
        ]
        for f in thin:
            weight = (f.get("scope_summary") or {}).get("weight_kept", 0)
            lines += [f"  - {f['fund_id']} ({f.get('fund_name', 'unknown')}): "
                      f"{weight:.1%} of AUM"]
        lines += [
            "- These funds are **accepted in full and their consensus contribution is "
            "unchanged** — the consensus signal counts funds, not exposure, so a fund "
            "with a marginal US sleeve votes exactly as loudly as a 95%-US fund. This "
            "is a warning, not a re-weighting: exposure-weighting the consensus would "
            "alter the locked composite. Read the consensus signal as correspondingly "
            "weaker where a material share of the input set is thin.",
        ]
    else:
        lines += ["- No accepted fund is thin (all sit above 35% US-equity weight, or "
                  "the band does not apply)."]
    lines += [""]

    # --- G3: Stage 0 regional advisories ---
    if stage0 is not None:
        advisories = stage0.get("advisories", []) or []
        lines += ["### Stage 0 regional advisories", ""]
        if advisories:
            for a in advisories:
                lines += [f"- {a}"]
        else:
            lines += ["- None raised; no upload title matched a regional marker."]
        lines += [""]

    # --- A3: style distribution / homogeneity, carried here so the input review
    # and the consensus caveat sit together (G4). ---
    style_by_fund = fund_style_map(data)
    homo = homogeneity_report(style_by_fund, len(valid_funds))
    lines += ["### Input-set style distribution", ""]
    if not homo.get("labelled"):
        lines += ["- Fund styles were not labelled this run; style-diversity weighting "
                  "will not be applied and consensus is reported unweighted."]
    else:
        dist = homo.get("style_distribution", {})
        dist_str = ", ".join(f"{k}: {v}" for k, v in dist.items()) or "n/a"
        lines += [f"- Style distribution: {dist_str}"]
        lines += [f"- Dominant style: {homo.get('dominant_style')} "
                  f"({homo.get('dominant_share', 0):.0%} of labelled funds)"]
        if homo.get("is_homogeneous"):
            lines += ["- ⚠ HOMOGENEOUS INPUT — consensus in this run is largely "
                      "tautological (same-mandate funds buying the same names). "
                      "See Appendix 3 for which fund styles to add."]
        else:
            lines += ["- Input spans multiple styles; cross-style agreement is treated "
                      "as more informative than within-style agreement."]
    lines += [""]

    return lines


def build_layer1_md(data: dict, stage0: dict | None = None) -> str:
    funds = data.get("funds", [])
    valid_funds = [f for f in funds if not f.get("rejected")]
    universe = data.get("unique_universe", [])
    pit = data.get("pit_snapshot_info", [])

    lines = ["# Layer 1: Extraction Summary", ""]

    # G4: consolidated input review, at the top.
    lines += _input_review(data, stage0)

    # Per-fund extraction table
    lines += ["## Per-fund extraction", ""]
    lines += ["| Fund ID | Name | Issuer | asof | Currency | Holdings kept "
              "| % AUM kept | Flags |"]
    lines += ["|---|---|---|---|---|---|---|---|"]
    for f in valid_funds:
        scope = f.get("scope_summary", {})
        flags = []
        if f.get("thin_us_exposure"):
            flags.append("thin US exposure")
        if f.get("currency") != "USD":
            flags.append("AUM excluded from exit-liquidity (non-USD)")
        lines += [
            f"| {f['fund_id']} | {f.get('fund_name', '')} | {f.get('issuer', '')} "
            f"| {f.get('asof', '')} "
            f"| {_currency_label(f)} "
            f"| {scope.get('n_holdings_kept_us_equity', 0)} "
            f"| {scope.get('weight_kept', 0):.0%} "
            f"| {'; '.join(flags) if flags else '—'} |"
        ]
    lines += [""]

    # Universe summary
    n_2plus = sum(1 for u in universe if u.get("n_funds_holding", 0) >= 2)
    n_5plus = sum(1 for u in universe if u.get("n_funds_holding", 0) >= 5)
    p = len(universe)

    lines += ["## Universe summary", ""]
    lines += [f"- Unique US-listed tickers: {p}"]
    if p > 0:
        lines += [f"- Stocks held by >= 2 funds: {n_2plus} ({n_2plus/p:.0%})"]
        lines += [f"- Stocks held by >= 5 funds: {n_5plus}"]
    lines += [""]

    # Out-of-scope summary
    lines += ["## Out-of-scope summary", ""]
    total_dropped_non_us = 0
    total_dropped_non_equity = 0
    for f in valid_funds:
        scope = f.get("scope_summary", {})
        total_dropped_non_us += scope.get("n_dropped_non_us", 0)
        total_dropped_non_equity += scope.get("n_dropped_non_equity", 0)
    lines += [f"- Non-US listings dropped: {total_dropped_non_us} tickers across all funds"]
    lines += [f"- Non-equity dropped: {total_dropped_non_equity} tickers"]
    lines += [""]

    # PIT snapshot availability
    lines += ["## PIT snapshot availability", ""]
    lines += ["| Fund | Snapshots available | Date range | Mode |"]
    lines += ["|---|---|---|---|"]
    for p_entry in pit:
        lines += [
            f"| {p_entry['fund_id']} | {p_entry['snapshots_available']} "
            f"| {p_entry['date_range']} | {p_entry['mode']} |"
        ]
    lines += [""]

    # Next layer pointer
    lines += ["## Next layer", ""]
    lines += [f"The unique universe ({len(universe)} tickers) advances to Layer 2 "
              "for fundamental fetch and quality screening."]

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True)
    ap.add_argument("--stage0", help="Optional validate_uploads.py --out JSON. "
                                     "Supplies the Stage 0 regional advisories to "
                                     "the consolidated input review (v0.32 G4).")
    ap.add_argument("--out", default="/home/claude/work/layer1_extraction.md")
    args = ap.parse_args()

    data = json.loads(Path(args.holdings).read_text(encoding="utf-8"))

    stage0 = None
    if args.stage0:
        stage0_path = Path(args.stage0)
        if stage0_path.exists():
            stage0 = json.loads(stage0_path.read_text(encoding="utf-8"))

    md = build_layer1_md(data, stage0)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Layer 1 report written to {args.out}")


if __name__ == "__main__":
    main()
