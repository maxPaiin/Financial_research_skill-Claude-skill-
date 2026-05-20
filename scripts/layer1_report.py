"""
Stage 1d: Generate layer1_extraction.md from holdings.json.

Writes a structured markdown summary of what was extracted in Layer 1.
"""

import json
import argparse
from pathlib import Path
from datetime import date


def build_layer1_md(data: dict) -> str:
    funds = data.get("funds", [])
    valid_funds = [f for f in funds if not f.get("rejected")]
    rejected_funds = [f for f in funds if f.get("rejected")]
    universe = data.get("unique_universe", [])
    pit = data.get("pit_snapshot_info", [])

    lines = ["# Layer 1: Extraction Summary", ""]

    # Input section
    lines += ["## Input", ""]
    lines += [f"- Funds uploaded: {len(funds)}"]
    lines += [f"- Funds successfully parsed: {len(valid_funds)}"]
    if rejected_funds:
        lines += [f"- Funds rejected (insufficient holdings data): {len(rejected_funds)}"]
        for f in rejected_funds:
            lines += [f"  - {f['fund_id']} ({f.get('fund_name', 'unknown')}): {f.get('rejection_reason')}"]
    lines += [""]

    # Per-fund extraction table
    lines += ["## Per-fund extraction", ""]
    lines += ["| Fund ID | Name | Issuer | asof | Holdings kept | % AUM kept |"]
    lines += ["|---|---|---|---|---|---|"]
    for f in valid_funds:
        scope = f.get("scope_summary", {})
        lines += [
            f"| {f['fund_id']} | {f.get('fund_name', '')} | {f.get('issuer', '')} "
            f"| {f.get('asof', '')} "
            f"| {scope.get('n_holdings_kept_us_equity', 0)} "
            f"| {scope.get('weight_kept', 0):.0%} |"
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
    ap.add_argument("--out", default="/home/claude/work/layer1_extraction.md")
    args = ap.parse_args()

    data = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    md = build_layer1_md(data)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"Layer 1 report written to {args.out}")


if __name__ == "__main__":
    main()
