"""
Stage 2d: Quality screen — PASS / FAIL filter for the unique universe.

Quality is a filter, not a ranker. Output is binary: PASS or FAIL with reason.
All thresholds are the canonical location per §5.3.

PASS criteria — ALL must hold:
  1. ROE positive in >= 3 of last 5 fiscal years
  2. Debt/Equity available AND < 5.0 (distress ceiling)
  3. No 3 consecutive years of negative net income
  4. At least 2 of 3 key metrics available with confidence >= 0.4

Inputs:
  --holdings        holdings.json (for the universe of tickers)
  --fundamentals    fundamentals.json (produced by fetch_fundamentals.py)
  --unscored        unscored_tickers.json (optional; merged into output)
  --out             screen_results.json

Output schema — screen_results.json:
{
  "n_in_universe": 50,
  "n_scored": 45,
  "n_passed": 30,
  "n_failed": 15,
  "n_unscored": 5,
  "results": [
    {"ticker": "AAPL", "passed": true,  "reason": null, "detail": null,
     "source": "edgar"},
    {"ticker": "XYZ",  "passed": false, "reason": "roe_insufficient",
     "detail": "ROE positive in only 2/5 years", "source": "yfinance"}
  ],
  "unscored": [
    {"ticker": "ABC", "reason": "no data from EDGAR or yfinance"}
  ]
}
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from providers.base import DataPoint, FundamentalsRecord  # noqa: E402

# Canonical thresholds — do not duplicate elsewhere.
MIN_ROE_POSITIVE_YEARS = 3          # of 5
DEBT_EQUITY_CEILING = 5.0
MAX_CONSECUTIVE_NEGATIVE_NI = 3     # if >=3 consecutive → FAIL
MIN_CONFIDENCE = 0.4
MIN_METRICS_AVAILABLE = 2           # of 3 key metrics (ROE 5y, EV/EBITDA, D/E)


@dataclass
class ScreenResult:
    ticker: str
    passed: bool
    reason: Optional[str] = None    # non-None only for FAIL
    detail: Optional[str] = None    # human-readable detail for FAIL


def screen(ticker: str, record: FundamentalsRecord) -> ScreenResult:
    """Apply the quality screen to a FundamentalsRecord. Returns ScreenResult."""
    reasons = []

    # 1. ROE positive years
    roe_values = [dp.value for dp in record.roe_5y if dp is not None and dp.value is not None]
    n_positive_roe = sum(1 for v in roe_values if v > 0)
    if len(roe_values) >= 3 and n_positive_roe < MIN_ROE_POSITIVE_YEARS:
        reasons.append(("roe_insufficient", f"ROE positive in only {n_positive_roe}/5 years"))

    # 2. Debt/Equity ceiling
    if record.debt_equity is not None and record.debt_equity.value is not None:
        if record.debt_equity.value >= DEBT_EQUITY_CEILING:
            reasons.append((
                "distress_debt_ratio",
                f"D/E = {record.debt_equity.value:.1f} exceeds {DEBT_EQUITY_CEILING} ceiling",
            ))
    # Note: if D/E is unavailable, we don't fail on this criterion alone (handled by metric count)

    # 3. Consecutive negative net income
    ni_values = [
        dp.value for dp in record.net_income_5y if dp is not None and dp.value is not None
    ]
    if ni_values:
        max_consecutive = _max_consecutive_negatives(ni_values)
        if max_consecutive >= MAX_CONSECUTIVE_NEGATIVE_NI:
            reasons.append((
                "persistent_negative_earnings",
                f"Net income negative in {max_consecutive} consecutive years",
            ))

    # 4. Minimum data availability
    n_available = 0
    if roe_values:
        n_available += 1
    if record.ev_ebitda is not None and record.ev_ebitda.value is not None \
            and record.ev_ebitda.confidence >= MIN_CONFIDENCE:
        n_available += 1
    if record.debt_equity is not None and record.debt_equity.value is not None \
            and record.debt_equity.confidence >= MIN_CONFIDENCE:
        n_available += 1

    if n_available < MIN_METRICS_AVAILABLE:
        reasons.append((
            "insufficient_data",
            f"Only {n_available} of 3 key metrics available (need >= {MIN_METRICS_AVAILABLE})",
        ))

    if reasons:
        reason_code, detail = reasons[0]
        return ScreenResult(ticker=ticker, passed=False, reason=reason_code, detail=detail)

    return ScreenResult(ticker=ticker, passed=True)


def _max_consecutive_negatives(values: list[float]) -> int:
    """Count maximum run of consecutive negative values."""
    max_run = 0
    current_run = 0
    for v in values:
        if v < 0:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


# --- Deserialization: fundamentals.json (dict) → FundamentalsRecord ---------

def _dp_from_dict(x: Optional[dict]) -> Optional[DataPoint]:
    if not isinstance(x, dict):
        return None
    asof_raw = x.get("asof")
    try:
        asof = date.fromisoformat(asof_raw) if isinstance(asof_raw, str) else date.today()
    except ValueError:
        asof = date.today()
    return DataPoint(
        value=x.get("value"),
        confidence=float(x.get("confidence", 0.0)),
        source=x.get("source", ""),
        asof=asof,
        n_sources_agreed=int(x.get("n_sources_agreed", 1)),
    )


def _parse_date(raw, default: Optional[date] = None) -> Optional[date]:
    if not isinstance(raw, str):
        return default
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return default


def record_from_dict(d: dict) -> FundamentalsRecord:
    asof = _parse_date(d.get("asof"), default=date.today())
    return FundamentalsRecord(
        ticker=d.get("ticker", ""),
        asof=asof,
        roe_5y=[_dp_from_dict(x) for x in d.get("roe_5y", [])],
        ev_ebitda=_dp_from_dict(d.get("ev_ebitda")),
        debt_equity=_dp_from_dict(d.get("debt_equity")),
        net_income_5y=[_dp_from_dict(x) for x in d.get("net_income_5y", [])],
        industry=d.get("industry"),
        market_cap=_dp_from_dict(d.get("market_cap")),
        adv=_dp_from_dict(d.get("adv")),
        is_adr=bool(d.get("is_adr", False)),
        data_asof=_parse_date(d.get("data_asof"), default=None),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True, help="holdings.json with unique_universe")
    ap.add_argument("--fundamentals", required=True, help="fundamentals.json from Stage 2b")
    ap.add_argument("--unscored", help="Optional unscored_tickers.json from Stage 2b")
    ap.add_argument("--out", required=True, help="Output screen_results.json path")
    args = ap.parse_args()

    holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    fundamentals = json.loads(Path(args.fundamentals).read_text(encoding="utf-8"))

    universe = [u["ticker"] for u in holdings.get("unique_universe", []) if u.get("ticker")]
    universe_set = set(universe)

    unscored_in: list[dict] = []
    if args.unscored:
        try:
            unscored_in = json.loads(Path(args.unscored).read_text(encoding="utf-8")).get(
                "unscored", []
            )
        except FileNotFoundError:
            unscored_in = []

    unscored_tickers = {u["ticker"] for u in unscored_in if u.get("ticker")}

    # Any universe ticker not in fundamentals and not already in unscored input → unscored
    derived_unscored = [
        {"ticker": t, "reason": "missing from fundamentals.json"}
        for t in universe if t not in fundamentals and t not in unscored_tickers
    ]
    unscored = unscored_in + derived_unscored

    results: list[dict] = []
    for ticker, rec_dict in fundamentals.items():
        if ticker not in universe_set:
            continue  # ignore stale entries not in current universe
        record = record_from_dict(rec_dict)
        sr = screen(ticker, record)
        results.append({
            "ticker": sr.ticker,
            "passed": sr.passed,
            "reason": sr.reason,
            "detail": sr.detail,
            "source": rec_dict.get("source"),
        })

    n_passed = sum(1 for r in results if r["passed"])
    n_failed = sum(1 for r in results if not r["passed"])

    out = {
        "n_in_universe": len(universe),
        "n_scored": len(results),
        "n_passed": n_passed,
        "n_failed": n_failed,
        "n_unscored": len(unscored),
        "results": results,
        "unscored": unscored,
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Screened {len(results)} of {len(universe)} (passed={n_passed}, "
        f"failed={n_failed}, unscored={len(unscored)}) -> {out_path}"
    )


if __name__ == "__main__":
    main()
