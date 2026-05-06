#!/usr/bin/env python3
"""
Stage 1 helper: deduplicate stocks across funds and build the unique universe.

Reads holdings.json (written by Claude after parsing each fund prospectus PDF)
and adds a `unique_universe` array tracking which funds hold each ticker.

Input shape:
{
  "funds": [
    {
      "fund_id": "F1",
      "fund_name": "...",
      "fund_type": "...",
      "currency": "USD",
      "reporting_date": "2025-Q4",
      "holdings": [
        {"ticker": "AAPL", "name": "Apple Inc.", "weight": 0.0723, "market": "US"},
        ...
      ]
    },
    ...
  ]
}

Output: same file, with a `unique_universe` array appended:
{
  ...,
  "unique_universe": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "market": "US",
      "held_by": ["F1", "F3", "F7"],
      "weights_by_fund": {"F1": 0.0723, "F3": 0.0512, "F7": 0.0641},
      "n_funds_holding": 3,
      "max_weight": 0.0723
    },
    ...
  ]
}
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict


def normalize_ticker(ticker: str, market: str) -> str:
    """Convert local ticker to yfinance format."""
    ticker = ticker.strip().upper()
    if market == "US" or "." in ticker:
        return ticker
    suffix_map = {
        "JP": ".T",
        "HK": ".HK",
        "TW": ".TW",
        "CN": ".SS",   # Shanghai; .SZ for Shenzhen — caller may need to override
        "UK": ".L",
        "DE": ".DE",
        "FR": ".PA",
    }
    return ticker + suffix_map.get(market, "")


def dedupe(holdings_data: dict) -> dict:
    """Build the unique_universe array."""
    universe = defaultdict(lambda: {
        "ticker": None,
        "name": None,
        "market": None,
        "held_by": [],
        "weights_by_fund": {},
    })

    for fund in holdings_data.get("funds", []):
        fid = fund["fund_id"]
        for h in fund.get("holdings", []):
            tkr = normalize_ticker(h["ticker"], h.get("market", "US"))
            entry = universe[tkr]
            entry["ticker"] = tkr
            entry["name"] = entry["name"] or h.get("name")
            entry["market"] = entry["market"] or h.get("market", "US")
            entry["held_by"].append(fid)
            entry["weights_by_fund"][fid] = h.get("weight", 0.0)

    result = []
    for tkr, e in universe.items():
        e["n_funds_holding"] = len(e["held_by"])
        weights = list(e["weights_by_fund"].values())
        e["max_weight"] = max(weights) if weights else 0.0
        e["avg_weight"] = sum(weights) / len(weights) if weights else 0.0
        result.append(e)

    # Sort: most-held first, then by max_weight
    result.sort(key=lambda x: (-x["n_funds_holding"], -x["max_weight"]))
    holdings_data["unique_universe"] = result
    holdings_data["universe_size"] = len(result)
    return holdings_data


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Path to holdings.json")
    p.add_argument("--dedupe", action="store_true", help="Run dedupe and write back")
    args = p.parse_args()

    path = Path(args.input)
    data = json.loads(path.read_text(encoding="utf-8"))

    if args.dedupe:
        data = dedupe(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Universe size: {data['universe_size']} unique tickers across {len(data['funds'])} funds.")
    else:
        # Just summarize
        print(json.dumps({
            "n_funds": len(data.get("funds", [])),
            "universe_size": data.get("universe_size", "not yet deduped"),
        }, indent=2))


if __name__ == "__main__":
    main()