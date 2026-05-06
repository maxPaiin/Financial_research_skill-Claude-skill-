"""
Stage 2: Fetch market & fundamental data for each stock in the universe via yfinance.

Reads holdings.json (must already have unique_universe), writes market.json
keyed by ticker. Caches per-ticker per-day to /home/claude/work/cache/.

Required: pip install yfinance pandas --break-system-packages
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import date

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip install yfinance --break-system-packages", file=sys.stderr)
    sys.exit(2)


# Industry bucket mapping (see references/data_sources.md §3)
INDUSTRY_MAP = {
    "Banks—Diversified": "financial",
    "Banks—Regional": "financial",
    "Insurance—Life": "financial",
    "Insurance—Property & Casualty": "financial",
    "Insurance—Diversified": "financial",
    "Capital Markets": "financial",
    "Asset Management": "financial",
    "Credit Services": "financial",

    "Oil & Gas E&P": "commodity",
    "Oil & Gas Integrated": "commodity",
    "Oil & Gas Midstream": "commodity",
    "Oil & Gas Refining & Marketing": "commodity",
    "Steel": "commodity",
    "Copper": "commodity",
    "Gold": "commodity",
    "Silver": "commodity",
    "Aluminum": "commodity",
    "Other Industrial Metals & Mining": "commodity",
    "Agricultural Inputs": "commodity",

    "Semiconductors": "technology",
    "Semiconductor Equipment & Materials": "technology",
    "Software—Application": "technology",
    "Software—Infrastructure": "technology",
    "Computer Hardware": "technology",
    "Consumer Electronics": "technology",
    "Information Technology Services": "technology",
    "Electronic Components": "technology",

    "Auto Manufacturers": "auto",
    "Auto Parts": "auto",
}


def map_industry(yahoo_industry: str | None, market: str) -> str:
    if not yahoo_industry:
        return "other"
    if yahoo_industry in {"Auto Manufacturers", "Auto Parts"}:
        return "export" if market == "JP" else "consumer_cyclical"
    return INDUSTRY_MAP.get(yahoo_industry, "other")


def fetch_one(ticker: str, market: str, cache_dir: Path) -> dict:
    cache_path = cache_dir / f"{ticker.replace('/', '_')}__{date.today().isoformat()}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    result = {
        "ticker": ticker,
        "market": market,
        "status": "ok",
    }

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        result["price"] = info.get("currentPrice") or info.get("regularMarketPrice")
        result["market_cap"] = info.get("marketCap")
        result["industry_raw"] = info.get("industry")
        result["industry"] = map_industry(info.get("industry"), market)
        result["sector"] = info.get("sector")
        result["pe"] = info.get("trailingPE")
        result["pbr"] = info.get("priceToBook")
        result["ev_ebitda"] = info.get("enterpriseToEbitda")
        result["roe"] = info.get("returnOnEquity")
        result["beta"] = info.get("beta")

        # 6-month return
        try:
            hist = t.history(period="6mo")
            if len(hist) >= 2:
                result["past_6m_return"] = float(hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1)
            else:
                result["past_6m_return"] = None
        except Exception:
            result["past_6m_return"] = None

        # 12-month return for the ticker (used as a fallback if industry ETF unavailable)
        try:
            hist12 = t.history(period="1y")
            if len(hist12) >= 2:
                result["past_12m_return"] = float(hist12["Close"].iloc[-1] / hist12["Close"].iloc[0] - 1)
            else:
                result["past_12m_return"] = None
        except Exception:
            result["past_12m_return"] = None

        # EPS estimate revision: yfinance v0.2.x exposes earnings_estimate as a DataFrame
        result["eps_estimate_t"] = None
        result["eps_estimate_t_minus_1"] = None
        try:
            est = t.earnings_estimate    # may be a DataFrame
            if est is not None and len(est) >= 2:
                # Use 'avg' column for current and prior period
                result["eps_estimate_t"] = float(est.iloc[0].get("avg") or 0) or None
                result["eps_estimate_t_minus_1"] = float(est.iloc[1].get("avg") or 0) or None
        except Exception:
            # Older yfinance versions or missing data
            pass

    except Exception as e:
        result["status"] = "missing"
        result["reason"] = str(e)[:120]

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, default=str))
    return result


# Industry ETF map for the relative-strength signal
INDUSTRY_ETF = {
    "financial": "XLF",
    "technology": "XLK",
    "commodity": "XLE",     # blended; energy used as proxy
    "export": "EWJ",         # Japan ETF
    "auto": "CARZ",
    "healthcare": "XLV",
    "consumer_staples": "XLP",
    "consumer_cyclical": "XLY",
    "industrials": "XLI",
    "utilities": "XLU",
    "real_estate": "XLRE",
    "communications": "XLC",
}


def fetch_industry_etf_returns(cache_dir: Path) -> dict:
    """Fetch 12-month returns for each industry ETF, plus the broad index."""
    cache_path = cache_dir / f"industry_etfs__{date.today().isoformat()}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text())

    result = {"index_return_12m": None, "etfs": {}}

    try:
        spy = yf.Ticker("SPY").history(period="1y")
        if len(spy) >= 2:
            result["index_return_12m"] = float(spy["Close"].iloc[-1] / spy["Close"].iloc[0] - 1)
    except Exception as e:
        result["index_error"] = str(e)[:80]

    for bucket, etf in INDUSTRY_ETF.items():
        try:
            h = yf.Ticker(etf).history(period="1y")
            if len(h) >= 2:
                result["etfs"][bucket] = float(h["Close"].iloc[-1] / h["Close"].iloc[0] - 1)
            else:
                result["etfs"][bucket] = None
        except Exception:
            result["etfs"][bucket] = None
        time.sleep(0.1)   # be gentle with yfinance

    cache_path.write_text(json.dumps(result))
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--universe", required=True, help="Path to holdings.json (with unique_universe)")
    p.add_argument("--out", required=True, help="Output market.json path")
    p.add_argument("--cache-dir", default="/home/claude/work/cache")
    p.add_argument("--max-tickers", type=int, default=None, help="Optional cap for cost control")
    args = p.parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    holdings = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    universe = holdings.get("unique_universe", [])
    if args.max_tickers:
        universe = universe[:args.max_tickers]

    print(f"Fetching data for {len(universe)} tickers...")

    # Industry ETF returns (one fetch for all)
    etf_data = fetch_industry_etf_returns(cache_dir)
    index_return = etf_data.get("index_return_12m")

    market = {"index_return_12m": index_return, "etf_returns": etf_data["etfs"], "stocks": {}}

    for i, u in enumerate(universe, 1):
        tkr = u["ticker"]
        mkt = u.get("market", "US")
        record = fetch_one(tkr, mkt, cache_dir)

        # Attach industry ETF return for this stock's industry
        ind = record.get("industry", "other")
        record["industry_etf_return_12m"] = etf_data["etfs"].get(ind)
        record["index_return_12m"] = index_return

        market["stocks"][tkr] = record
        if i % 20 == 0:
            print(f"  ...{i}/{len(universe)}")
        time.sleep(0.05)   # be gentle

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(market, indent=2, ensure_ascii=False, default=str))

    n_ok = sum(1 for s in market["stocks"].values() if s.get("status") == "ok")
    n_missing = len(market["stocks"]) - n_ok
    print(f"Done. {n_ok} ok, {n_missing} missing/failed.")


if __name__ == "__main__":
    main()