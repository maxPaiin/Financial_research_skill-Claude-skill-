"""
Stage 2e: Fundamental quality percentile scoring for PASSED stocks only.

Computes fundamental_quality_score (0–100) as the percentile rank of
5-year average ROE within the passed universe.

Why ROE 5y avg as single quality metric (per §3.2.5):
- Most discriminating single number for "is this a quality business"
- 5y average dampens single-year noise
- More universally available than EV/EBITDA across ADRs
- Quality screen already filtered persistent-negative-ROE stocks
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Optional


def percentile_rank(value: float, distribution: list[float]) -> float:
    """Percentile rank of value in distribution: 0 (lowest) to 100 (highest)."""
    if not distribution:
        return 50.0
    n_below = sum(1 for v in distribution if v < value)
    n_equal = sum(1 for v in distribution if v == value)
    return round(100.0 * (n_below + 0.5 * n_equal) / len(distribution), 2)


def roe_5y_average(roe_values: list[Optional[float]]) -> Optional[float]:
    """Mean of non-None ROE values. Returns None if fewer than 2 available."""
    valid = [v for v in roe_values if v is not None]
    if len(valid) < 2:
        return None
    return round(sum(valid) / len(valid), 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", required=True, help="fundamentals.json from provider fetch")
    ap.add_argument("--screen", required=True, help="screen_results.json from quality_screen step")
    ap.add_argument("--out", required=True, help="Output scores_per_stock.json")
    args = ap.parse_args()

    fundamentals = json.loads(Path(args.fundamentals).read_text(encoding="utf-8"))
    screen_results = json.loads(Path(args.screen).read_text(encoding="utf-8"))

    passed_tickers = {
        r["ticker"] for r in screen_results.get("results", []) if r.get("passed")
    }

    # Compute ROE 5y avg for all passed tickers
    roe_avgs: dict[str, Optional[float]] = {}
    for ticker, rec in fundamentals.items():
        if ticker not in passed_tickers:
            continue
        roe_vals = [year.get("value") for year in rec.get("roe_5y", []) if year]
        roe_avgs[ticker] = roe_5y_average(roe_vals)

    valid_roe = [v for v in roe_avgs.values() if v is not None]

    scores: dict[str, dict] = {}
    for ticker in passed_tickers:
        roe_avg = roe_avgs.get(ticker)
        if roe_avg is not None:
            fq_score = percentile_rank(roe_avg, valid_roe)
        else:
            fq_score = None

        rec = fundamentals.get(ticker, {})
        scores[ticker] = {
            "ticker": ticker,
            "status": "ok",
            "roe_5y_avg": roe_avg,
            "fundamental_quality_score": fq_score,
            "ev_ebitda": (rec.get("ev_ebitda") or {}).get("value"),
            "debt_equity": (rec.get("debt_equity") or {}).get("value"),
            "industry": rec.get("industry"),
            "is_adr": rec.get("is_adr", False),
            "data_confidence": rec.get("overall_confidence"),
        }

    out = {"stocks": scores, "n_scored": len(scores)}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"Scored {len(scores)} passed stocks -> {args.out}")


if __name__ == "__main__":
    main()
