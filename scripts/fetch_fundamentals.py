"""
Stage 2b: Fetch fundamentals for the unique universe and write fundamentals.json.

For each ticker in `holdings.unique_universe`, calls ProviderRegistry (EDGAR →
yfinance fallback) and serializes the FundamentalsRecord dataclass tree into
JSON. Tickers that return nothing from both providers are written to a separate
`unscored_tickers.json` list so Stage 2d can mark them as unscored.

Output schema — fundamentals.json (canonical):
{
  "<TICKER>": {
    "ticker": "AAPL",
    "asof": "2025-05-21",
    "roe_5y": [{"value": 0.45, "confidence": 0.9, "source": "...",
                "asof": "2025-05-21", "n_sources_agreed": 1}, ...],
    "roe_5y_avg": 0.42,
    "ev_ebitda": {"value": 23.4, ...} | null,
    "debt_equity": {"value": 1.95, ...} | null,
    "net_income_5y": [...],
    "industry": "technology",
    "market_cap": {...} | null,
    "adv": {...} | null,
    "is_adr": false,
    "overall_confidence": 0.78,
    "source": "edgar" | "yfinance"
  },
  ...
}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from providers.base import DataPoint, FundamentalsRecord  # noqa: E402
from providers.registry import ProviderRegistry  # noqa: E402
from validate_uploads import valid_email, EMAIL_GATE_MESSAGE  # noqa: E402


def _serialize(obj):
    if obj is None:
        return None
    if isinstance(obj, date):
        return obj.isoformat()
    if is_dataclass(obj):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


def _roe_5y_avg(roe_5y: list[Optional[DataPoint]]) -> Optional[float]:
    """Mean of non-None ROE values; None if fewer than 2 valid points."""
    vals = [dp.value for dp in roe_5y if dp is not None and dp.value is not None]
    if len(vals) < 2:
        return None
    return round(sum(vals) / len(vals), 4)


def _overall_confidence(rec: FundamentalsRecord) -> float:
    """Mean confidence across all DataPoints that carry a value."""
    confs: list[float] = []
    for dp in rec.roe_5y or []:
        if dp is not None and dp.value is not None:
            confs.append(dp.confidence)
    for dp in rec.net_income_5y or []:
        if dp is not None and dp.value is not None:
            confs.append(dp.confidence)
    for field in (rec.ev_ebitda, rec.debt_equity, rec.market_cap, rec.adv):
        if field is not None and field.value is not None:
            confs.append(field.confidence)
    if not confs:
        return 0.0
    return round(sum(confs) / len(confs), 4)


def record_to_dict(rec: FundamentalsRecord, source: str) -> dict:
    d = _serialize(rec)
    d["roe_5y_avg"] = _roe_5y_avg(rec.roe_5y)
    d["overall_confidence"] = _overall_confidence(rec)
    d["source"] = source
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True, help="holdings.json with unique_universe")
    ap.add_argument("--asof", help="ISO date (YYYY-MM-DD). Defaults to today.")
    ap.add_argument("--out", required=True, help="Output fundamentals.json path")
    ap.add_argument(
        "--unscored-out",
        help="Optional path to write unscored_tickers.json. "
             "Defaults to <out-dir>/unscored_tickers.json.",
    )
    ap.add_argument(
        "--provenance-out",
        help="Optional path to write data_provenance.json (Stage 2c output). "
             "Defaults to <out-dir>/data_provenance.json.",
    )
    ap.add_argument(
        "--email",
        help="SEC EDGAR contact email (B1). Falls back to EDGAR_CONTACT_EMAIL. "
             "REQUIRED — SEC returns 403 without a contact email in the UA.",
    )
    args = ap.parse_args()

    # B1: enforce the email gate at the EDGAR-calling stage too. The user-facing
    # gate is Stage 0 (validate_uploads.py), but fetching without a valid email
    # would 403 against SEC, so we halt here as well.
    contact_email = (args.email or os.environ.get("EDGAR_CONTACT_EMAIL") or "").strip()
    if not valid_email(contact_email):
        print(EMAIL_GATE_MESSAGE, file=sys.stderr)
        sys.exit(2)

    asof = date.fromisoformat(args.asof) if args.asof else date.today()
    holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    universe = holdings.get("unique_universe", [])
    tickers = [u["ticker"] for u in universe if u.get("ticker")]

    if not tickers:
        print("WARNING: unique_universe is empty. Did you run extract_holdings.py --dedupe?",
              file=sys.stderr)

    registry = ProviderRegistry(contact_email=contact_email)
    fundamentals: dict[str, dict] = {}
    unscored: list[dict] = []

    for tkr in tickers:
        record, source = registry.fetch(tkr, asof)
        if record is None:
            unscored.append({
                "ticker": tkr,
                "reason": "no data from EDGAR or yfinance",
            })
            continue
        fundamentals[tkr] = record_to_dict(record, source)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(fundamentals, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    unscored_path = (
        Path(args.unscored_out) if args.unscored_out
        else out_path.parent / "unscored_tickers.json"
    )
    unscored_path.write_text(
        json.dumps({"unscored": unscored, "n_unscored": len(unscored)},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    provenance_path = (
        Path(args.provenance_out) if args.provenance_out
        else out_path.parent / "data_provenance.json"
    )
    registry.flush_provenance(provenance_path)

    print(
        f"Scored {len(fundamentals)}/{len(tickers)} tickers -> {out_path}; "
        f"{len(unscored)} unscored -> {unscored_path}; "
        f"provenance -> {provenance_path}"
    )


if __name__ == "__main__":
    main()
