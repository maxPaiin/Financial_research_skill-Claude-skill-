"""
Stage 3a: Composite ranking — one ranking, top 15, three display tiers.

Ranking formula (canonical per §5.3):
  composite_score = 0.50 * fundamental_quality_score   (0-100, percentile rank)
                  + 0.50 * crowding_signal_normalized  (0-100, percentile rank)

Both halves of the composite use percentile rank within the passed universe
so they're on a comparable scale. Earlier versions min-max'd the crowding
signal, which exploded noise: `consensus_raw = log(1 + n_funds_holding)` has
a narrow range (~0.7-2.5) and a single outlier dragged everyone else to the
extremes.

Tier grouping (display only, does not affect rationale generation):
  Tier A: rank 1-5
  Tier B: rank 6-10
  Tier C: rank 11-15

Ranking weights are the canonical location per §5.3.
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Optional

# Canonical ranking weights — do not duplicate elsewhere.
_QUALITY_WEIGHT = 0.50
_CONSENSUS_WEIGHT = 0.50
_TOP_N = 15
_TIER_BREAKS = [5, 10, 15]   # A: ≤5, B: ≤10, C: ≤15


def percentile_rank(value: float, distribution: list[float]) -> float:
    """Percentile rank of value in distribution: 0 (lowest) to 100 (highest).

    Duplicated from compute_scores.py rather than imported so the two stage
    scripts stay independently runnable.
    """
    if not distribution:
        return 50.0
    n_below = sum(1 for v in distribution if v < value)
    n_equal = sum(1 for v in distribution if v == value)
    return round(100.0 * (n_below + 0.5 * n_equal) / len(distribution), 2)


def tier(rank: int) -> str:
    if rank <= _TIER_BREAKS[0]:
        return "A"
    if rank <= _TIER_BREAKS[1]:
        return "B"
    return "C"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True, help="scores_per_stock.json from compute_scores")
    ap.add_argument("--crowding", required=True, help="crowding_signals.json")
    ap.add_argument("--overlap", required=True, help="overlap.json")
    ap.add_argument("--out", required=True, help="Output rankings.json")
    args = ap.parse_args()

    scores_data = json.loads(Path(args.scores).read_text(encoding="utf-8"))
    crowding_data = json.loads(Path(args.crowding).read_text(encoding="utf-8"))
    overlap_data = json.loads(Path(args.overlap).read_text(encoding="utf-8"))

    stocks = scores_data.get("stocks", {})
    crowding_by_ticker = {r["ticker"]: r for r in crowding_data.get("signals", [])}
    overlap_by_ticker = {r["ticker"]: r for r in overlap_data.get("overlap", [])}

    # Gather candidates: only passed stocks with a quality score
    candidates = []
    for ticker, s in stocks.items():
        if s.get("status") != "ok":
            continue
        fq = s.get("fundamental_quality_score")
        c = crowding_by_ticker.get(ticker, {})
        crowding_signal = c.get("signal")
        if fq is None or crowding_signal is None:
            continue
        candidates.append({
            "ticker": ticker,
            "name": overlap_by_ticker.get(ticker, {}).get("name"),
            "fundamental_quality_score": fq,
            "crowding_signal_raw": crowding_signal,
            "crowding_discount": c.get("crowding_discount", 0.0),
            "is_high_crowding": c.get("is_high_crowding", False),
            "industry": s.get("industry"),
            "roe_5y_avg": s.get("roe_5y_avg"),
            "ev_ebitda": s.get("ev_ebitda"),
            "debt_equity": s.get("debt_equity"),
            "is_adr": s.get("is_adr", False),
            "data_confidence": s.get("data_confidence"),
            "data_asof": s.get("data_asof"),
            **{k: overlap_by_ticker.get(ticker, {}).get(k)
               for k in ("n_funds_holding", "held_by", "avg_weight", "max_weight",
                         "sum_of_weights", "weights_by_fund")},
        })

    if not candidates:
        print("WARNING: No candidates qualify for ranking (no passed stocks with both scores).")
        out = {"ranked": [], "n_ranked": 0}
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=2))
        return

    # Percentile-rank the crowding signal within the passed universe so it
    # shares a scale with fundamental_quality_score (already a percentile).
    raw_signals = [c["crowding_signal_raw"] for c in candidates]
    for c in candidates:
        c["crowding_signal_normalized"] = percentile_rank(
            c["crowding_signal_raw"], raw_signals
        )

    # Composite score
    for c in candidates:
        c["composite_score"] = round(
            _QUALITY_WEIGHT * c["fundamental_quality_score"]
            + _CONSENSUS_WEIGHT * c["crowding_signal_normalized"],
            2,
        )

    # Sort descending, take top 15
    candidates.sort(key=lambda x: -x["composite_score"])
    top15 = candidates[:_TOP_N]

    for i, c in enumerate(top15, start=1):
        c["rank"] = i
        c["tier"] = tier(i)

    out = {
        "n_passed_universe": len(candidates),
        "n_ranked": len(top15),
        "ranked": top15,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"Top {len(top15)} ranked from {len(candidates)} passed candidates -> {args.out}")


if __name__ == "__main__":
    main()
