"""
Stage 2e: Fundamental quality percentile scoring for PASSED stocks only.

Computes fundamental_quality_score (0–100) as the percentile rank of
5-year average ROE within the passed universe.

Why ROE 5y avg as single quality metric (per §3.2.5):
- Most discriminating single number for "is this a quality business"
- 5y average dampens single-year noise
- More universally available than EV/EBITDA across ADRs
- Quality screen already filtered persistent-negative-ROE stocks

v0.34 (A5):
- `quality_confidence`, `roe_years` and `roe_source` are carried into
  scores_per_stock.json; ranking reads confidence from this file only, and
  shrinks quality by `quality_confidence` (the confidence of the ROE points
  themselves), not by `data_confidence` (= overall_confidence, display only).
- A stock that passed the screen but has no quality score — fewer than two
  defined ROE years, e.g. a trailing-only yfinance record or equity <= 0 in
  most years — gets `status: "unscored_no_roe"` and an `unscored_reason`, so
  it is disclosed in Layer 2 instead of vanishing from the ranking unseen (F7).
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path
from typing import Optional

_MIN_ROE_YEARS = 2


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
    if len(valid) < _MIN_ROE_YEARS:
        return None
    return round(sum(valid) / len(valid), 4)


def unscored_reason(rec: dict) -> str:
    """Why a screened stock has no quality score (A5)."""
    roe_years = rec.get("roe_years")
    if roe_years is None:
        roe_years = sum(1 for p in rec.get("roe_5y") or [] if p and p.get("value") is not None)
    source = rec.get("roe_source") or rec.get("source") or "no source"
    parts = [f"{roe_years} defined ROE year{'s' if roe_years != 1 else ''} "
             f"(needs {_MIN_ROE_YEARS}; {source})"]
    undefined = rec.get("roe_undefined_years") or []
    if undefined:
        parts.append("ROE undefined in " + ", ".join(str(y) for y in undefined)
                     + " (equity <= 0)")
    if any(isinstance(p, dict) and str(p.get("source", "")).startswith("yfinance:ttm")
           for p in rec.get("roe_5y") or []):
        parts.append("only a trailing-twelve-month figure was available")
    return "; ".join(parts)


def build_scores(fundamentals: dict, screen_results: dict) -> dict:
    """scores_per_stock.json content for the screened universe."""
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
    for ticker in sorted(passed_tickers):
        roe_avg = roe_avgs.get(ticker)
        fq_score = percentile_rank(roe_avg, valid_roe) if roe_avg is not None else None

        rec = fundamentals.get(ticker, {})
        scores[ticker] = {
            "ticker": ticker,
            "status": "ok" if fq_score is not None else "unscored_no_roe",
            "unscored_reason": None if fq_score is not None else unscored_reason(rec),
            "roe_5y_avg": roe_avg,
            "fundamental_quality_score": fq_score,
            # v0.34 A5: the confidence ranking shrinks by, and its provenance.
            "quality_confidence": rec.get("quality_confidence"),
            "roe_years": rec.get("roe_years"),
            "roe_source": rec.get("roe_source"),
            "ev_ebitda": (rec.get("ev_ebitda") or {}).get("value"),
            "debt_equity": (rec.get("debt_equity") or {}).get("value"),
            "industry": rec.get("industry"),
            "is_adr": rec.get("is_adr", False),
            "data_confidence": rec.get("overall_confidence"),   # display only
            "data_asof": rec.get("data_asof"),
            "source": rec.get("source"),
            # A1 (v0.3): carry liquidity/size signals through to ranking & A2.
            # yfinance fetches both, fetch_fundamentals serialises them, but
            # v0.2 dropped them here — reviving them so crowding_signal.py
            # (days-to-liquidate) and the reports can use them.
            "market_cap": (rec.get("market_cap") or {}).get("value"),
            "adv": (rec.get("adv") or {}).get("value"),
        }

    n_unscored = sum(1 for s in scores.values() if s["status"] != "ok")
    return {"stocks": scores, "n_scored": len(scores) - n_unscored,
            "n_unscored_no_roe": n_unscored}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", required=True, help="fundamentals.json from provider fetch")
    ap.add_argument("--screen", required=True, help="screen_results.json from quality_screen step")
    ap.add_argument("--out", required=True, help="Output scores_per_stock.json")
    args = ap.parse_args()

    fundamentals = json.loads(Path(args.fundamentals).read_text(encoding="utf-8"))
    screen_results = json.loads(Path(args.screen).read_text(encoding="utf-8"))
    out = build_scores(fundamentals, screen_results)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"Scored {out['n_scored']} passed stocks "
          f"({out['n_unscored_no_roe']} passed but unscored: no ROE) -> {args.out}")


if __name__ == "__main__":
    main()
