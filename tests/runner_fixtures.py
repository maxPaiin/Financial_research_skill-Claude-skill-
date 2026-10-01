"""
An offline input set for the phase-runner tests (v0.4 C6/C7).

build(work, replay) writes a reviewed holdings.json for seven funds into
`work` and everything an offline run needs into `replay`:

  replay/sec_exchange.json        the recorded SEC exchange-file sample
  replay/edgar_cache/             its ticker map + Apple's recorded facts and
                                  submissions (so AAPL goes through EDGAR offline)
  replay/yfinance/<SYMBOL>.json   synthetic yfinance replays: statements, info and
                                  300 daily closes per ticker; IXN/SPY top holdings;
                                  SPY/XLK/XLC/XLY price histories

All numbers are synthetic except the recorded SEC files.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "edgar"

TICKERS = ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "INTC", "QCOM",
           "TXN", "CSCO", "AMZN", "META", "GOOGL", "NOW"]
_SECTOR = {"AMZN": "Consumer Cyclical", "META": "Communication Services",
           "GOOGL": "Communication Services"}

FUNDS = [
    ("F1", "Global Technology Fund A", "MSCI AC World Information Technology Index",
     {"NVDA": 0.090, "AAPL": 0.085, "MSFT": 0.080, "AVGO": 0.060, "ORCL": 0.045, "CRM": 0.040,
      "AMD": 0.035, "NOW": 0.030}),
    ("F2", "Global Technology Fund B", "MSCI AC World Information Technology Index",
     {"NVDA": 0.095, "MSFT": 0.090, "AAPL": 0.070, "AVGO": 0.065, "AMD": 0.050, "ADBE": 0.040,
      "QCOM": 0.035, "TXN": 0.030}),
    ("F3", "Global Technology Fund C", "MSCI ACWI Information Technology Index",
     {"MSFT": 0.085, "NVDA": 0.080, "AAPL": 0.075, "ORCL": 0.055, "CRM": 0.050, "INTC": 0.035,
      "CSCO": 0.032, "AMD": 0.031}),
    ("F4", "US Large Cap Growth Fund", "S&P 500 Index",
     {"MSFT": 0.095, "AAPL": 0.090, "NVDA": 0.085, "AMZN": 0.070, "META": 0.060, "GOOGL": 0.055,
      "AVGO": 0.040, "NOW": 0.035}),
    ("F5", "US Equity Fund", "S&P 500 Index",
     {"AAPL": 0.080, "MSFT": 0.078, "AMZN": 0.065, "GOOGL": 0.060, "META": 0.050, "NVDA": 0.045,
      "CSCO": 0.034, "TXN": 0.033}),
    ("F6", "Asia Pacific Income Fund", "Hang Seng Index",
     {"AVGO": 0.050, "QCOM": 0.045, "TXN": 0.042, "CSCO": 0.040, "INTC": 0.038, "AAPL": 0.036}),
    ("F7", "Global Opportunities Fund", None,
     {"AMZN": 0.060, "GOOGL": 0.055, "META": 0.050, "ADBE": 0.045, "CRM": 0.040, "ORCL": 0.036}),
]

ETF_TOP = {
    "IXN": {"NVDA": 0.18, "AAPL": 0.15, "MSFT": 0.13, "AVGO": 0.05, "ORCL": 0.03, "CRM": 0.025,
            "AMD": 0.024, "CSCO": 0.023, "ADBE": 0.022, "QCOM": 0.021},
    "SPY": {"NVDA": 0.075, "MSFT": 0.068, "AAPL": 0.066, "AMZN": 0.041, "META": 0.028,
            "AVGO": 0.026, "GOOGL": 0.024, "TSLA": 0.020, "BRK-B": 0.017, "JPM": 0.015},
}


def _history(start_price: float, daily: float, n: int = 300) -> list:
    # 300 weekdays from 2025-06-02 end in late July 2026; flow tests pass more.
    out, d, p = [], date(2025, 6, 2), start_price
    while len(out) < n:
        if d.weekday() < 5:
            out.append([d.isoformat(), round(p, 4)])
            p *= 1 + daily
        d += timedelta(days=1)
    return out


def _stock_replay(i: int, ticker: str, days: int = 300) -> dict:
    roe = 0.12 + 0.015 * i                      # distinct quality per ticker
    equity = 50e9 + 5e9 * i
    return {
        "_synthetic": "runner fixture",
        "info": {"symbol": ticker, "debtToEquity": 40.0 + 3 * i, "enterpriseToEbitda": 15.0 + i,
                 "marketCap": 5e11 + 1e10 * i, "averageDailyVolume10Day": 2e7 + 1e6 * i,
                 "currentPrice": 150.0 + i, "sector": _SECTOR.get(ticker, "Technology"),
                 "country": "United States", "financialCurrency": "USD", "bookValue": 30.0},
        "income_stmt": {f"{y}-12-31": {"Net Income": roe * equity * (1 + 0.02 * (y - 2022))}
                        for y in (2022, 2023, 2024, 2025)},
        "balance_sheet": {f"{y}-12-31": {"Stockholders Equity": equity * (1 + 0.02 * (y - 2022))}
                          for y in (2022, 2023, 2024, 2025)},
        "history": _history(100.0 + i, 0.0005 + 0.0001 * i, days),
    }


def build(work: Path, replay: Path, history_days: int = 300) -> None:
    work.mkdir(parents=True, exist_ok=True)
    funds = []
    for fid, name, bench, weights in FUNDS:
        rows = [{"name": f"{t} Corp", "ticker_raw": t, "isin": None, "weight": w, "page": 1}
                for t, w in weights.items()]
        rows.append({"name": "Tencent Holdings", "ticker_raw": "0700.HK", "isin": None,
                     "weight": 0.03, "page": 1})
        funds.append({"fund_id": fid, "fund_name": name, "issuer": None, "asof": "2026-08-31",
                      "currency": "USD", "total_aum": 2e9 + 1e9 * int(fid[1:]),
                      "benchmark": bench, "style": "growth", "holdings": rows})
    (work / "holdings.json").write_text(json.dumps({"funds": funds}, indent=1), encoding="utf-8")

    (replay / "edgar_cache").mkdir(parents=True, exist_ok=True)
    (replay / "yfinance").mkdir(parents=True, exist_ok=True)
    sample = _FIXTURES / "company_tickers_exchange_sample.json"
    shutil.copy(sample, replay / "sec_exchange.json")
    shutil.copy(sample, replay / "edgar_cache" / "ticker_exchange_map.json")
    for name in ("facts_320193.json", "submissions_320193.json"):
        shutil.copy(_FIXTURES / name, replay / "edgar_cache" / name)
    for i, t in enumerate(TICKERS):
        (replay / "yfinance" / f"{t}.json").write_text(json.dumps(_stock_replay(i, t, history_days)))
    for etf, top in ETF_TOP.items():
        (replay / "yfinance" / f"{etf}.json").write_text(json.dumps({
            "info": {"symbol": etf, "quoteType": "ETF"}, "top_holdings": top,
            "history": _history(400.0, 0.0006, history_days)}))
    for etf, drift in (("XLK", 0.0009), ("XLC", 0.0004), ("XLY", 0.0002)):
        (replay / "yfinance" / f"{etf}.json").write_text(json.dumps({
            "info": {"symbol": etf}, "history": _history(200.0, drift, history_days)}))
