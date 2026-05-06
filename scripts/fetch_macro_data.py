"""
Stage 2: Fetch macro variables for industry-score calculation.

Pulls (in priority order: FRED > yfinance > fail):
  - 10Y Treasury yield, current and 1y ago (rate change)
  - CPI YoY (inflation)
  - DXY level (dollar strength)
  - USD/JPY (for fx_regime determination)
  - 3M T-bill (risk-free rate, used by backtest Sharpe calc)

Required: pip install fredapi yfinance pandas pandas-datareader --break-system-packages
Optional env: FRED_API_KEY  (free key from fred.stlouisfed.org)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import date, timedelta

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed", file=sys.stderr)
    sys.exit(2)

try:
    from fredapi import Fred
    FRED_AVAILABLE = bool(os.getenv("FRED_API_KEY"))
    if FRED_AVAILABLE:
        fred = Fred(api_key=os.getenv("FRED_API_KEY"))
except ImportError:
    FRED_AVAILABLE = False
    fred = None


def fred_latest_change(series_id: str, lookback_days: int = 365) -> tuple[float | None, float | None]:
    """Return (current, change_vs_lookback_days_ago) for a FRED series."""
    if not FRED_AVAILABLE:
        return None, None
    try:
        s = fred.get_series(series_id)
        s = s.dropna()
        if len(s) < 2:
            return None, None
        latest = float(s.iloc[-1])
        # Find a value about lookback_days ago
        cutoff = s.index[-1] - timedelta(days=lookback_days)
        prior_slice = s.loc[s.index <= cutoff]
        if len(prior_slice) == 0:
            return latest, None
        prior = float(prior_slice.iloc[-1])
        return latest, latest - prior
    except Exception as e:
        print(f"  FRED {series_id} failed: {e}", file=sys.stderr)
        return None, None


def yfinance_latest_change(ticker: str, lookback_days: int = 365, divide_by: float = 1.0) -> tuple[float | None, float | None]:
    """Yahoo Finance fallback. Returns (current, change_vs_~1y_ago)."""
    try:
        h = yf.Ticker(ticker).history(period="2y")["Close"].dropna()
        if len(h) < 2:
            return None, None
        latest = float(h.iloc[-1]) / divide_by
        cutoff = h.index[-1] - timedelta(days=lookback_days)
        prior_slice = h.loc[h.index <= cutoff]
        if len(prior_slice) == 0:
            return latest, None
        prior = float(prior_slice.iloc[-1]) / divide_by
        return latest, latest - prior
    except Exception as e:
        print(f"  yfinance {ticker} failed: {e}", file=sys.stderr)
        return None, None


def fred_yoy(series_id: str) -> float | None:
    """Year-over-year change for a level series like CPI."""
    if not FRED_AVAILABLE:
        return None
    try:
        s = fred.get_series(series_id).dropna()
        if len(s) < 13:
            return None
        latest = float(s.iloc[-1])
        prior = float(s.iloc[-13])     # 12 months ago
        return (latest - prior) / prior
    except Exception:
        return None


def determine_fx_regime(usd_jpy: float | None, dxy_change: float | None) -> str:
    """Heuristic: weak_jpy if USD/JPY > 145; strong_usd if DXY rose > 5%; else normal."""
    if usd_jpy is not None and usd_jpy > 145:
        return "weak_jpy"
    if dxy_change is not None and dxy_change > 5:
        return "strong_usd"
    return "normal"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    p.add_argument("--cache-dir", default="/home/claude/work/cache")
    args = p.parse_args()

    cache_path = Path(args.cache_dir) / f"macro__{date.today().isoformat()}.json"
    if cache_path.exists():
        data = json.loads(cache_path.read_text())
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"Used cached macro data from {cache_path}")
        return

    print("Fetching macro variables...")

    macro = {
        "as_of": date.today().isoformat(),
        "fred_used": FRED_AVAILABLE,
    }

    # 10Y Treasury yield
    if FRED_AVAILABLE:
        rate, rate_change = fred_latest_change("DGS10")
    else:
        # ^TNX is reported as yield * 10
        rate, rate_change = yfinance_latest_change("^TNX", divide_by=10)
    macro["interest_rate_10y"] = rate
    macro["interest_rate_yoy_change"] = (rate_change / 100) if (rate_change is not None and FRED_AVAILABLE) else rate_change

    # 3M T-bill (risk-free)
    if FRED_AVAILABLE:
        rf, _ = fred_latest_change("DGS3MO")
        macro["risk_free_rate"] = (rf / 100) if rf is not None else None
    else:
        rf, _ = yfinance_latest_change("^IRX")
        macro["risk_free_rate"] = (rf / 100) if rf is not None else None

    # Inflation YoY
    cpi_yoy = fred_yoy("CPIAUCSL")
    if cpi_yoy is None:
        # Rough fallback: assume 3% if FRED unavailable; flag degradation
        cpi_yoy = 0.03
        macro["inflation_degraded"] = True
    macro["inflation_yoy"] = cpi_yoy

    # DXY
    dxy, dxy_change = yfinance_latest_change("DX-Y.NYB")
    macro["dxy"] = dxy
    macro["dxy_yoy_change"] = dxy_change

    # USD/JPY
    usd_jpy, _ = yfinance_latest_change("JPY=X")
    macro["usd_jpy"] = usd_jpy

    # FX regime
    macro["fx_regime"] = determine_fx_regime(usd_jpy, dxy_change)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(macro, indent=2, ensure_ascii=False, default=str))

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(macro, indent=2, ensure_ascii=False, default=str))

    print(json.dumps(macro, indent=2, default=str))


if __name__ == "__main__":
    main()