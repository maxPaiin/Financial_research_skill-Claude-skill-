"""
Consensus flow (v0.4 D2): between two factsheets, did the funds add to a stock
or trim it?

A factsheet weight moves for two reasons: the manager traded, or prices moved.
Had the fund not traded, the weight would have drifted to

    w* = w_prev × (1 + r_i) / (1 + R_f)

where r_i is the stock's price return and R_f the fund's return between the two
`asof` dates. The trade is what drift does not explain:  trade = w_now − w*.

  r_i   daily closes from yfinance_provider.fetch_close_series_dated (adjusted
        for splits), the last close on or before each asof date.
  R_f   the fund's NAV per share — only when both snapshots report in USD
        (currency == "USD"): a non-USD class's NAV return mixes in currency
        moves, which I8 forbids converting. Otherwise the return of the fund's
        benchmark proxy ETF (benchmark_weights.json), otherwise SPY's. The
        source is recorded per fund.
  ε     factsheets round weights to a step (1pp, 0.1pp, 0.01pp, …), detected
        per snapshot from the fund's disclosed weights; ε = half the step.
        Both weights in a comparison are rounded, so a row is a trade only
        beyond the rounding both can carry: ε_now + ε_prev·(1 + r_i)/(1 + R_f).
        Pure drift on rounded weights never crosses it; one ε alone would call
        a trade on about a quarter of untouched positions.
  s     +1 (added) if trade > threshold, −1 (trimmed) if trade < −threshold,
        else 0.

Per stock, over the funds that disclose it in both snapshots (the comparable
funds), with ω the funds' independence weights from consensus.json:

  building      Σ ω s > 0 and at least 2 funds added
  unwinding     Σ ω s < 0 and at least 2 funds trimmed
  mixed         otherwise
  insufficient  fewer than 2 comparable funds

A stock in only one snapshot "entered disclosure" or "left disclosure" and is
recorded without a sign: a factsheet lists only its top holdings, so a name can
leave the list because others grew.

Funds are matched on fund_isin, otherwise on the exact normalised fund_name; an
unmatched fund is excluded and listed. So is a fund whose prior asof is not
earlier than its current one, or whose return cannot be measured.

The prior snapshot is the holdings.json of an earlier run (after p2), or the
work_bundle.zip that run left in its outputs directory. This script reads
holdings, fund weights, benchmark proxies and prices — never the rank — and
writes consensus_flow.json, which only the coherence overlay reads (D3). It
cannot move a rank.

Usage:
  consensus_flow.py --holdings holdings.json
                    --prior-holdings <holdings.json | work_bundle.zip>
                    --consensus consensus.json
                    [--benchmark-weights benchmark_weights.json]
                    --out consensus_flow.json
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_holdings import fund_order_key, is_accepted, us_sleeve_vector  # noqa: E402

VERSION = "0.4"
MARKET_ETF = "SPY"
STEPS = (0.01, 0.001, 0.0001, 0.00001)      # 1pp, 0.1pp, 0.01pp, 0.001pp
MIN_COMPARABLE = 2                          # a flow needs two funds to compare
MIN_SAME_DIRECTION = 2                      # building / unwinding need two funds agreeing
STATES = ("building", "unwinding", "mixed", "insufficient")
STALE_DAYS = 7                              # a close older than this does not price a date
_ON_STEP = 1e-6
_EPS = 1e-12
_AT_THRESHOLD = 1e-9    # 0.04 - 0.05 is -0.010000000000000002: a move that only ties
                        # the rounding bound is not a trade

Fetch = Callable[[list[str], date, date], dict[str, list[tuple[date, float]]]]


# --- Inputs ------------------------------------------------------------------------

def load_prior(path: Path) -> dict:
    """holdings.json, or the holdings.json inside an earlier run's work_bundle.zip."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            if "holdings.json" not in zf.namelist():
                raise ValueError(f"{path.name} holds no holdings.json")
            return json.loads(zf.read("holdings.json").decode("utf-8"))
    return json.loads(path.read_text(encoding="utf-8"))


def _number(value) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _date(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def normalise_name(name) -> str:
    """Exact match after Unicode, case and whitespace normalisation — nothing looser."""
    return " ".join(unicodedata.normalize("NFKC", str(name or "")).casefold().split())


def _isin(fund: dict) -> str:
    return str(fund.get("fund_isin") or "").strip().upper()


# --- Matching, rounding, prices ------------------------------------------------------

def match_funds(current: list[dict], prior: list[dict]) -> tuple[dict, list[dict]]:
    """({current fund_id: (prior fund, "fund_isin" | "fund_name")}, [excluded])."""
    by_isin: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for p in prior:
        if _isin(p):
            by_isin.setdefault(_isin(p), []).append(p)
        if normalise_name(p.get("fund_name")):
            by_name.setdefault(normalise_name(p.get("fund_name")), []).append(p)
    matched: dict[str, tuple[dict, str]] = {}
    excluded: list[dict] = []
    used: set[int] = set()
    for f in current:
        found = None
        for how, pool in (("fund_isin", by_isin.get(_isin(f), []) if _isin(f) else []),
                          ("fund_name", by_name.get(normalise_name(f.get("fund_name")), []))):
            free = [p for p in pool if id(p) not in used]
            if len(free) == 1:
                found = (free[0], how)
                break
            if len(free) > 1:
                excluded.append({"fund_id": f["fund_id"],
                                 "reason": f"more than one prior fund shares its {how}"})
                found = False
                break
        if found:
            matched[f["fund_id"]] = found
            used.add(id(found[0]))
        elif found is None:
            excluded.append({"fund_id": f["fund_id"],
                             "reason": "no prior snapshot with the same fund_isin or fund_name"})
    return matched, excluded


def reporting_step(weights) -> Optional[float]:
    """The coarsest step every disclosed weight sits on (0.001 = weights in 0.1pp)."""
    ws = [w for w in (_number(x) for x in weights) if w is not None and w > 0]
    if not ws:
        return None
    for step in STEPS:
        if all(abs(w / step - round(w / step)) < _ON_STEP for w in ws):
            return step
    return STEPS[-1]


def _disclosed_weights(fund: dict) -> list:
    return [h.get("weight") for key in ("holdings", "holdings_us")
            for h in fund.get(key) or []]


def close_on_or_before(series: list[tuple[date, float]], day: date) -> Optional[float]:
    best = None
    for d, value in series:
        if d > day:
            break
        best = (d, value)
    if best is None or (day - best[0]).days > STALE_DAYS:
        return None
    return best[1]


def period_return(series: list[tuple[date, float]], start: date, end: date) -> Optional[float]:
    a, b = close_on_or_before(series, start), close_on_or_before(series, end)
    if a is None or b is None or a <= 0:
        return None
    return b / a - 1


def fund_return(cur: dict, prev: dict, proxy: Optional[str], closes: dict,
                start: date, end: date) -> tuple[Optional[float], Optional[str]]:
    """R_f and where it came from: USD NAV, else the proxy ETF, else SPY (I8)."""
    if cur.get("currency") == "USD" and prev.get("currency") == "USD":
        nav_now, nav_prev = _number(cur.get("nav_per_share")), _number(prev.get("nav_per_share"))
        if nav_now and nav_prev and nav_now > 0 and nav_prev > 0:
            return nav_now / nav_prev - 1, "nav_usd"
    for symbol, source in ((proxy, f"proxy:{proxy}"), (MARKET_ETF, "spy")):
        if symbol:
            r = period_return(closes.get(symbol) or [], start, end)
            if r is not None:
                return r, source
    return None, None


def row_signal(w_prev: float, w_now: float, r_stock: float, r_fund: float,
               step_now: float, step_prev: float) -> dict:
    """One fund's trade in one stock, net of price drift and of rounding."""
    k = (1 + r_stock) / (1 + r_fund)
    expected = w_prev * k
    trade = w_now - expected
    threshold = step_now / 2 + k * step_prev / 2
    bound = threshold + _AT_THRESHOLD
    s = 1 if trade > bound else -1 if trade < -bound else 0
    return {"w_expected": expected, "trade": trade, "threshold": threshold, "s": s}


def flow_state(n_comparable: int, n_added: int, n_trimmed: int, sum_omega_s: float) -> str:
    if n_comparable < MIN_COMPARABLE:
        return "insufficient"
    if sum_omega_s > _EPS and n_added >= MIN_SAME_DIRECTION:
        return "building"
    if sum_omega_s < -_EPS and n_trimmed >= MIN_SAME_DIRECTION:
        return "unwinding"
    return "mixed"


# --- The computation ---------------------------------------------------------------

def compute(holdings: dict, prior: dict, consensus: dict,
            benchmark_weights: Optional[dict], fetch: Fetch) -> dict:
    """consensus_flow.json content. `fetch(symbols, start, end)` supplies dated closes."""
    omega = {f["fund_id"]: f.get("omega") or 0.0 for f in consensus.get("funds", [])}
    current = sorted((f for f in holdings.get("funds", []) if is_accepted(f) and f["fund_id"] in omega),
                     key=lambda f: fund_order_key(f["fund_id"]))
    prior_funds = [f for f in prior.get("funds", []) if is_accepted(f)]
    matched, excluded = match_funds(current, prior_funds)
    bench = benchmark_weights or {}

    pairs = []
    for f in current:
        if f["fund_id"] not in matched:
            continue
        p, how = matched[f["fund_id"]]
        start, end = _date(p.get("asof")), _date(f.get("asof"))
        if not start or not end or start >= end:
            excluded.append({"fund_id": f["fund_id"],
                             "reason": f"prior asof {p.get('asof')} is not before {f.get('asof')}"})
            continue
        pairs.append((f, p, how, start, end))

    closes: dict = {}
    if pairs:
        symbols = {MARKET_ETF}
        for f, p, *_ in pairs:
            symbols |= set(us_sleeve_vector(f)) & set(us_sleeve_vector(p))
            proxy = (bench.get(f["fund_id"]) or {}).get("proxy")
            if proxy:
                symbols.add(proxy)
        first = min(s for *_, s, _ in pairs) - timedelta(days=STALE_DAYS + 3)
        closes = fetch(sorted(symbols), first, max(e for *_, e in pairs))

    funds_out, stocks = [], {}
    for f, p, how, start, end in pairs:
        fid = f["fund_id"]
        proxy = (bench.get(fid) or {}).get("proxy")
        r_f, source = fund_return(f, p, proxy, closes, start, end)
        if r_f is None:
            excluded.append({"fund_id": fid, "reason": "no fund return: no USD NAV, and no "
                             "proxy-ETF or SPY prices for the period"})
            continue
        step_now = reporting_step(_disclosed_weights(f)) or STEPS[-1]
        step_prev = reporting_step(_disclosed_weights(p)) or STEPS[-1]
        funds_out.append({"fund_id": fid, "matched_on": how, "prior_asof": start.isoformat(),
                          "asof": end.isoformat(), "r_fund": round(r_f, 6),
                          "r_fund_source": source, "omega": omega[fid],
                          "step_now": step_now, "step_prev": step_prev})
        v_now, v_prev = us_sleeve_vector(f), us_sleeve_vector(p)
        for ticker in sorted(set(v_now) | set(v_prev)):
            rec = stocks.setdefault(ticker, {"ticker": ticker, "funds": [], "entered_disclosure": [],
                                             "left_disclosure": [], "unpriced": []})
            if ticker not in v_prev:
                rec["entered_disclosure"].append(fid)
                continue
            if ticker not in v_now:
                rec["left_disclosure"].append(fid)
                continue
            r_i = period_return(closes.get(ticker) or [], start, end)
            if r_i is None:
                rec["unpriced"].append(fid)
                continue
            sig = row_signal(v_prev[ticker], v_now[ticker], r_i, r_f, step_now, step_prev)
            rec["funds"].append({"fund_id": fid, "w_prev": round(v_prev[ticker], 6),
                                 "w_now": round(v_now[ticker], 6),
                                 "w_expected": round(sig["w_expected"], 6),
                                 "trade": round(sig["trade"], 6),
                                 "threshold": round(sig["threshold"], 6), "s": sig["s"],
                                 "r_stock": round(r_i, 6), "r_fund": round(r_f, 6)})

    counts = {state: 0 for state in STATES}
    out_stocks = []
    for ticker in sorted(stocks):
        rec = stocks[ticker]
        signs = [(row["fund_id"], row["s"]) for row in rec["funds"]]
        n_added = sum(1 for _, s in signs if s > 0)
        n_trimmed = sum(1 for _, s in signs if s < 0)
        sum_omega_s = sum(omega[fid] * s for fid, s in signs)
        state = flow_state(len(signs), n_added, n_trimmed, sum_omega_s)
        counts[state] += 1
        out_stocks.append({"ticker": ticker, "state": state,
                           "sum_omega_s": round(sum_omega_s, 6), "n_comparable": len(signs),
                           "n_added": n_added, "n_trimmed": n_trimmed,
                           "n_unchanged": len(signs) - n_added - n_trimmed, **rec})

    excluded.sort(key=lambda e: fund_order_key(e["fund_id"]))
    return {
        "version": VERSION,
        "method": "drift-adjusted factsheet weights (D2)",
        "market_etf": MARKET_ETF,
        "n_funds": len(current),
        "n_comparable_funds": len(funds_out),
        "funds": funds_out,
        "excluded_funds": excluded,
        "counts": counts,
        "stocks": out_stocks,
    }


def _fetch_yfinance(symbols: list[str], start: date, end: date) -> dict:
    # Imported lazily so the module and its tests stay importable without yfinance (I11).
    from providers.yfinance_provider import fetch_close_series_dated
    return fetch_close_series_dated(symbols, start, end)


def main() -> int:
    ap = argparse.ArgumentParser(description="Consensus flow between two factsheet snapshots")
    ap.add_argument("--holdings", required=True, help="holdings.json of this run (after p2)")
    ap.add_argument("--prior-holdings", required=True,
                    help="an earlier run's holdings.json, or its work_bundle.zip")
    ap.add_argument("--consensus", required=True, help="consensus.json (fund weights ω)")
    ap.add_argument("--benchmark-weights", help="benchmark_weights.json (proxy ETFs)")
    ap.add_argument("--out", required=True, help="Output consensus_flow.json")
    args = ap.parse_args()

    read = lambda p: json.loads(Path(p).read_text(encoding="utf-8"))  # noqa: E731
    try:
        prior = load_prior(Path(args.prior_holdings))
    except (OSError, ValueError) as e:
        print(f"ERROR: cannot read the prior snapshot: {e}", file=sys.stderr)
        return 1
    out = compute(read(args.holdings), prior, read(args.consensus),
                  read(args.benchmark_weights) if args.benchmark_weights else None,
                  _fetch_yfinance)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    c = out["counts"]
    print(f"Consensus flow: {out['n_comparable_funds']} of {out['n_funds']} funds comparable; "
          f"building {c['building']}, unwinding {c['unwinding']}, mixed {c['mixed']}, "
          f"insufficient {c['insufficient']} -> {out_path}")
    for e in out["excluded_funds"]:
        print(f"  excluded {e['fund_id']}: {e['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
