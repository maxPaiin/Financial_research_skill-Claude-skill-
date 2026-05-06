# Data Sources

Implementation reference for `scripts/fetch_market_data.py` and `scripts/fetch_macro_data.py`.

## 1. Setup

```bash
pip install yfinance fredapi pandas pandas-datareader --break-system-packages
```

Optional environment variable:
```bash
export FRED_API_KEY="your_free_key_from_fred.stlouisfed.org"
```

If `FRED_API_KEY` is unset, scripts fall back to yfinance proxies and note the degradation.

## 2. yfinance field map

For each ticker:

| Field in `market.json` | yfinance source |
|---|---|
| price | `Ticker.info["currentPrice"]` or last close |
| market_cap | `Ticker.info["marketCap"]` |
| industry | `Ticker.info["industry"]` (Yahoo's GICS-like; map to our buckets in §3) |
| sector | `Ticker.info["sector"]` |
| pe | `Ticker.info["trailingPE"]` |
| pbr | `Ticker.info["priceToBook"]` |
| ev_ebitda | `Ticker.info["enterpriseToEbitda"]` |
| roe | `Ticker.info["returnOnEquity"]` |
| eps_estimate_t | `Ticker.analyst_price_targets` / `earnings_estimates` (current quarter mean) |
| eps_estimate_t_minus_1 | same field, 1 quarter ago — pulled from `earnings_history` |
| past_6m_return | computed from `Ticker.history(period="6mo")` |

**Caveats:**
- `Ticker.info` is unstable across yfinance versions; the script wraps each access in try/except and treats missing fields as `null`.
- For non-US tickers, suffix matters: `7203.T` (Toyota Tokyo), `0700.HK` (Tencent HK), `2330.TW` (TSMC Taiwan). The fund prospectus usually gives the local ticker — script normalizes to yfinance format.

## 3. Industry bucket mapping

Yahoo's `industry` field is fine-grained (e.g., "Semiconductors", "Software—Application"). Our scoring uses coarser buckets that match `scoring_playbook.md` §2.1. Mapping:

```python
INDUSTRY_MAP = {
    "Banks—Diversified": "financial",
    "Banks—Regional": "financial",
    "Insurance—Life": "financial",
    "Insurance—Property & Casualty": "financial",
    "Capital Markets": "financial",

    "Oil & Gas E&P": "commodity",
    "Oil & Gas Integrated": "commodity",
    "Steel": "commodity",
    "Copper": "commodity",
    "Gold": "commodity",
    "Agricultural Inputs": "commodity",

    "Semiconductors": "technology",
    "Software—Application": "technology",
    "Software—Infrastructure": "technology",
    "Computer Hardware": "technology",
    "Consumer Electronics": "technology",

    "Auto Manufacturers": "export",          # Japan-listed only
    "Auto Parts": "export",                  # Japan-listed only

    # ... extend as needed
}

def map_industry(yahoo_industry: str, market: str) -> str:
    # Special case: auto only counts as 'export' if listed in Japan
    if yahoo_industry in {"Auto Manufacturers", "Auto Parts"}:
        return "export" if market == "JP" else "consumer_cyclical"
    return INDUSTRY_MAP.get(yahoo_industry, "other")
```

Unmapped industries fall to `"other"`, which receives no macro tilt.

## 4. Industry ETF map

For `industry_etf_return_12m`, map our buckets to representative ETFs:

| Bucket | US ETF | Asia equivalent (if needed) |
|---|---|---|
| financial | XLF | (Japan: 1615.T) |
| technology | XLK | (Japan: 1625.T) |
| commodity | XLE / XLB blended | (HK: 2826.HK) |
| export | EWJ | n/a (already JP) |
| healthcare | XLV | |
| consumer_staples | XLP | |
| consumer_cyclical | XLY | |
| industrials | XLI | |
| utilities | XLU | |
| real_estate | XLRE | |
| communications | XLC | |

## 5. FRED series IDs (macro)

| Variable | FRED ID | yfinance fallback |
|---|---|---|
| 10Y Treasury yield | `DGS10` | `^TNX` (close/10) |
| Fed funds rate | `DFF` | n/a (use TNX trend) |
| CPI YoY | `CPIAUCSL` (compute YoY) | n/a |
| DXY | `DTWEXBGS` | `DX-Y.NYB` |
| USD/JPY | n/a | `JPY=X` |
| 3M T-bill (risk-free) | `DGS3MO` | `^IRX` (close/100) |

## 6. Caching

```python
# /home/claude/work/cache/{ticker}__{YYYY-MM-DD}.json
# /home/claude/work/cache/macro__{YYYY-MM-DD}.json
```

Scripts check the cache first; only call APIs on miss. A single-day TTL is sufficient — fundamentals don't move intraday.

## 7. Failure modes

| Symptom | Handling |
|---|---|
| yfinance returns empty for a ticker | Write `{"status": "missing", "reason": "no_data"}`; Stage 3 marks as `unscored` |
| Yahoo rate-limits (429) | Exponential backoff up to 3 retries, then write `{"status": "missing", "reason": "rate_limit"}` |
| FRED key invalid | Fall back to yfinance proxies; flag `macro.degraded = true` |
| No internet at all | Fail loudly; cannot proceed past Stage 2 |

## 8. Python skeleton

```python
import yfinance as yf
import json, time
from pathlib import Path

def fetch_one(ticker: str, market: str) -> dict:
    cache_path = Path(f"/home/claude/work/cache/{ticker}__{date.today().isoformat()}.json")
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    try:
        t = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="6mo")
        result = {
            "ticker": ticker,
            "price": info.get("currentPrice"),
            "market_cap": info.get("marketCap"),
            "industry_raw": info.get("industry"),
            "industry": map_industry(info.get("industry"), market),
            "pe": info.get("trailingPE"),
            "pbr": info.get("priceToBook"),
            "ev_ebitda": info.get("enterpriseToEbitda"),
            "roe": info.get("returnOnEquity"),
            "past_6m_return": (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) if len(hist) > 0 else None,
            # eps fields require additional calls — see fetch_market_data.py
        }
    except Exception as e:
        result = {"ticker": ticker, "status": "missing", "reason": str(e)[:100]}
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result))
    return result
```

The full script is in `scripts/fetch_market_data.py`.