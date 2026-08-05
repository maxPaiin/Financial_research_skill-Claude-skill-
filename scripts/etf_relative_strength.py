"""
Stage 3a-bis input: sector-ETF relative strength (v0.31, E2.3).

DIVERGENCE DETECTION, NOT CONFIRMATION. The overlay never rewards a stock for
price agreeing with the thesis — momentum confirmation is pro-cyclical, and
consensus is already pro-cyclical by construction (v0.3 §0 premise 3). Stacking
the two would point both signals the wrong way together in a de-rating. What is
measured here is only whether the price action *contradicts* the macro read and
the sector logic.

Two measurements, both versus a fixed benchmark over fixed windows:

  sector RS      = return(sector_ETF, w) - return(SPY, w)      for w in 3M/6M/12M
  stock excess   = return(stock, w)      - return(sector_ETF, w)

Design rules carried from the spec:
  * Relative strength versus SPY, never absolute return — absolute return
    mostly measures beta.
  * Fixed 3M / 6M / 12M windows, so no window can be picked after the fact.
  * A missing sector-ETF mapping or a short price history yields
    status="insufficient_data" — never a substituted proxy, because that would
    turn a data gap into a coherence verdict (E3.2).

Inputs:
  --rankings   rankings.json (READ-ONLY — ticker + industry only)
  --prices     optional prices.json {"SYMBOL": [close, ...]} to bypass the
               network (offline reruns, fixtures); absent -> yfinance fetch
  --out        etf_relative_strength.json

Output schema — etf_relative_strength.json:
{
  "benchmark": "SPY",
  "windows": {"3M": 63, "6M": 126, "12M": 252},
  "asof": "2026-08-06",
  "sectors": {
    "technology": {"etf": "XLK", "status": "ok",
                   "rs_vs_spy": {"3M": 0.041, "6M": 0.06, "12M": 0.11},
                   "rs_mean": 0.07, "rs_state": "outperforming"}
  },
  "stocks": {
    "AAPL": {"industry": "technology", "etf": "XLK", "status": "ok",
             "excess_vs_etf": {"3M": -0.22, "6M": -0.19, "12M": -0.05},
             "excess_mean": -0.153, "divergence": "negative"}
  }
}
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from providers.industry_map import BENCHMARK_ETF, sector_etf  # noqa: E402

# Canonical constants for the overlay's price inputs — do not duplicate.
# Windows are in trading days (~21/month); fixed by spec so they cannot be
# selected post hoc.
WINDOWS: dict[str, int] = {"3M": 63, "6M": 126, "12M": 252}

# Classification bands. These are DELIBERATELY COARSE, UNCALIBRATED defaults:
# there is no backtest in this tool (removed in v0.2), so a precise threshold
# would be false precision. They exist only to separate "decisively different"
# from "noise", and the overlay they feed can only ever demote (E0.1).
RS_BAND = 0.05           # |sector RS vs SPY| below 5pp -> "inline"
DIVERGENCE_BAND = 0.20   # |stock excess vs sector ETF| at/above 20pp -> sharp


def window_return(series: list[float], n_days: int) -> Optional[float]:
    """Total return over the last `n_days` trading days, or None if too short."""
    if not series or len(series) < n_days + 1:
        return None
    start, end = series[-1 - n_days], series[-1]
    if not start:
        return None
    return round(end / start - 1.0, 6)


def relative_strength(
    series: list[float],
    benchmark: list[float],
    n_days: int,
) -> Optional[float]:
    """`series` return minus `benchmark` return over the same fixed window."""
    a = window_return(series, n_days)
    b = window_return(benchmark, n_days)
    if a is None or b is None:
        return None
    return round(a - b, 6)


def _mean(values: list[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 6)


def rs_by_window(
    series: list[float],
    benchmark: list[float],
) -> dict[str, Optional[float]]:
    return {label: relative_strength(series, benchmark, n) for label, n in WINDOWS.items()}


def classify_rs(rs: dict[str, Optional[float]]) -> tuple[Optional[float], str]:
    """(mean RS across available windows, state).

    States: outperforming / inline / lagging / insufficient_data. Averaging the
    fixed windows rather than picking one keeps a single strong quarter from
    deciding the verdict on its own.
    """
    m = _mean(list(rs.values()))
    if m is None:
        return None, "insufficient_data"
    if m >= RS_BAND:
        return m, "outperforming"
    if m <= -RS_BAND:
        return m, "lagging"
    return m, "inline"


def classify_divergence(excess: dict[str, Optional[float]]) -> tuple[Optional[float], str]:
    """(mean excess vs sector ETF, divergence label).

    Labels: positive / negative / none / insufficient_data. A divergence is NOT
    a penalty — it is a flag that obliges the card to explain it (E2.3).
    """
    m = _mean(list(excess.values()))
    if m is None:
        return None, "insufficient_data"
    if m >= DIVERGENCE_BAND:
        return m, "positive"
    if m <= -DIVERGENCE_BAND:
        return m, "negative"
    return m, "none"


def build(
    ranked: list[dict],
    closes: dict[str, list[float]],
    benchmark: str = BENCHMARK_ETF,
) -> dict:
    """Assemble the relative-strength side-car from ranked rows + close series."""
    bench_series = closes.get(benchmark) or []

    sectors: dict[str, dict] = {}
    stocks: dict[str, dict] = {}

    for row in ranked:
        ticker = row.get("ticker")
        if not ticker:
            continue
        industry = row.get("industry")
        etf = sector_etf(industry)

        if etf and etf not in sectors:
            etf_series = closes.get(etf) or []
            if etf_series and bench_series:
                rs = rs_by_window(etf_series, bench_series)
                mean_rs, state = classify_rs(rs)
                sectors[industry] = {
                    "etf": etf,
                    "status": "ok" if state != "insufficient_data" else "insufficient_data",
                    "rs_vs_spy": rs,
                    "rs_mean": mean_rs,
                    "rs_state": state,
                }
            else:
                sectors[industry] = {
                    "etf": etf,
                    "status": "insufficient_data",
                    "rs_vs_spy": {w: None for w in WINDOWS},
                    "rs_mean": None,
                    "rs_state": "insufficient_data",
                    "note": "no price history for the sector ETF or the benchmark",
                }
        elif not etf:
            sectors.setdefault(industry or "other", {
                "etf": None,
                "status": "insufficient_data",
                "rs_vs_spy": {w: None for w in WINDOWS},
                "rs_mean": None,
                "rs_state": "insufficient_data",
                "note": f"no sector-ETF mapping for industry '{industry}'",
            })

        stock_series = closes.get(ticker) or []
        etf_series = closes.get(etf) if etf else None
        if stock_series and etf_series:
            excess = {
                label: relative_strength(stock_series, etf_series, n)
                for label, n in WINDOWS.items()
            }
            mean_excess, divergence = classify_divergence(excess)
            stocks[ticker] = {
                "industry": industry,
                "etf": etf,
                "status": "ok" if divergence != "insufficient_data" else "insufficient_data",
                "excess_vs_etf": excess,
                "excess_mean": mean_excess,
                "divergence": divergence,
            }
        else:
            stocks[ticker] = {
                "industry": industry,
                "etf": etf,
                "status": "insufficient_data",
                "excess_vs_etf": {w: None for w in WINDOWS},
                "excess_mean": None,
                "divergence": "insufficient_data",
                "note": "no sector-ETF mapping" if not etf else "price history unavailable",
            }

    return {
        "benchmark": benchmark,
        "windows": dict(WINDOWS),
        "asof": date.today().isoformat(),
        "n_sectors": len(sectors),
        "n_stocks": len(stocks),
        "sectors": sectors,
        "stocks": stocks,
        "caveat": (
            "Sector ETFs carry their own crowding dynamics. Relative strength is "
            "context, not truth, and never confirmation of a thesis."
        ),
    }


def _symbols_needed(ranked: list[dict], benchmark: str) -> list[str]:
    symbols = [benchmark]
    for row in ranked:
        if row.get("ticker"):
            symbols.append(row["ticker"])
        etf = sector_etf(row.get("industry"))
        if etf:
            symbols.append(etf)
    return list(dict.fromkeys(symbols))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rankings", required=True, help="rankings.json (read-only)")
    ap.add_argument("--prices", help="Optional prices.json {symbol: [close,...]} — "
                                     "bypasses the network when supplied.")
    ap.add_argument("--out", required=True, help="Output etf_relative_strength.json")
    args = ap.parse_args()

    rankings = json.loads(Path(args.rankings).read_text(encoding="utf-8"))
    ranked = rankings.get("ranked", [])

    if args.prices:
        closes = json.loads(Path(args.prices).read_text(encoding="utf-8"))
    else:
        # Imported lazily so the module (and its tests) stay importable without
        # yfinance installed.
        from providers.yfinance_provider import fetch_close_series
        closes = fetch_close_series(_symbols_needed(ranked, BENCHMARK_ETF))

    out = build(ranked, closes)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    n_ok = sum(1 for s in out["stocks"].values() if s["status"] == "ok")
    print(f"ETF relative strength: {n_ok}/{out['n_stocks']} stocks measured, "
          f"{out['n_sectors']} sectors -> {out_path}")


if __name__ == "__main__":
    main()
