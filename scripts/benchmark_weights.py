"""
Stage 2f-i (v0.4 B3): benchmark proxy weights per fund.

DEC-1 makes a vote mean "held at or above benchmark weight" for stocks a
fund's benchmark is heavy in. For each accepted fund this script maps the
benchmark printed on its factsheet (Stage 1a `benchmark`; null when the
factsheet prints none — it is never inferred) to a proxy ETF
(providers/benchmark_map.py) and records the proxy's top-10 weights:

  {"F1": {"benchmark": "...", "proxy": "IXN", "proxy_quality": "approximate (...)",
          "top10": {"NVDA": 0.18, ...}, "b10": 0.021,
          "fetched_at": "2026-04-15", "error": null}}

`b10` is the smallest of the ten weights. On any failure — no benchmark
printed, a benchmark the table does not map, or no top holdings from the data
source — `proxy` is null and `error` says why; that fund then casts presence
votes (consensus_signal.py), which the report discloses as vote-basis coverage.

Usage:
  benchmark_weights.py --holdings holdings.json --out benchmark_weights.json
                       [--replay saved_top_holdings.json]

--replay reads a saved {etf: {ticker: weight}} file instead of the network.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_holdings import fund_order_key, is_accepted  # noqa: E402
from providers.benchmark_map import proxy_for  # noqa: E402

_TOP_N = 10

Fetcher = Callable[[list[str]], dict[str, dict[str, float]]]


def _live_fetch(etfs: list[str]) -> dict[str, dict[str, float]]:
    # Imported lazily so this module (and its tests) need no network stack.
    from providers.yfinance_provider import fetch_etf_top_holdings
    return fetch_etf_top_holdings(etfs)


def build(holdings: dict, fetch: Fetcher = _live_fetch,
          fetched_at: Optional[str] = None) -> dict[str, dict]:
    """benchmark_weights.json content, keyed by fund_id in natural order."""
    funds = sorted((f for f in holdings.get("funds", []) if is_accepted(f)),
                   key=lambda f: fund_order_key(f["fund_id"]))
    mapped = {f["fund_id"]: proxy_for(f.get("benchmark")) for f in funds}
    etfs = sorted({m[0] for m in mapped.values() if m})
    try:
        tops = fetch(etfs) if etfs else {}
    except Exception as e:  # noqa: BLE001 — a failed fetch is a recorded reason
        print(f"WARNING: proxy top-holdings fetch failed: {e}", file=sys.stderr)
        tops = {}

    out: dict[str, dict] = {}
    for f in funds:
        bench = f.get("benchmark")
        rec = {"benchmark": bench, "proxy": None, "proxy_quality": None, "top10": {},
               "b10": None, "fetched_at": fetched_at or date.today().isoformat(),
               "error": None}
        match = mapped[f["fund_id"]]
        if not bench:
            rec["error"] = "no benchmark printed on the factsheet"
        elif match is None:
            rec["error"] = f"benchmark not in the proxy table: {bench}"
        else:
            etf, quality = match
            weights = {t: float(w) for t, w in (tops.get(etf) or {}).items()
                       if isinstance(w, (int, float)) and w > 0}
            if not weights:
                rec["error"] = f"top holdings unavailable for {etf}"
            else:
                top = dict(sorted(weights.items(), key=lambda kv: (-kv[1], kv[0]))[:_TOP_N])
                rec.update(proxy=etf, proxy_quality=quality, top10=top,
                           b10=min(top.values()))
        out[f["fund_id"]] = rec
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 2f-i: benchmark proxy top-10 weights")
    ap.add_argument("--holdings", required=True, help="holdings.json after Stage 1b-d")
    ap.add_argument("--out", required=True, help="Output benchmark_weights.json")
    ap.add_argument("--replay", help="Saved {etf: {ticker: weight}} instead of the network")
    args = ap.parse_args()

    holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    fetch: Fetcher = _live_fetch
    if args.replay:
        saved = json.loads(Path(args.replay).read_text(encoding="utf-8"))
        fetch = lambda etfs: {e: saved[e] for e in etfs if e in saved}  # noqa: E731
    out = build(holdings, fetch)

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    with_proxy = sum(1 for r in out.values() if r["proxy"])
    print(f"Benchmark proxies: {with_proxy}/{len(out)} funds -> {path}")
    for fid, r in out.items():
        print(f"  {fid}: {r['proxy'] + ' (' + r['proxy_quality'] + ')' if r['proxy'] else r['error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
