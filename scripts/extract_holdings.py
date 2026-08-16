"""
Stage 1 helper: US filtering, ticker normalization, currency normalization,
deduplication, and PIT snapshot grouping.

Reads holdings.json (written by Claude after parsing each fund PDF)
and produces:
  - Per-fund scope_summary (US kept, non-US dropped, non-equity dropped)
  - Per-fund normalised `currency` (ISO-4217 or null) — v0.32 G1.1
  - Per-fund `thin_us_exposure` flag (20–35% of AUM in US equity) — v0.32 G2
  - unique_universe array with n_funds_holding, weights, avg_weight, etc.
  - pit_snapshot_info for each fund

Input shape (written by Claude at Stage 1a):
{
  "funds": [
    {
      "fund_id": "F1",
      "fund_name": "...",
      "issuer": "...",
      "asof": "YYYY-MM-DD",
      "currency": "USD",          <- REQUIRED (v0.32 G1.1); null if the
                                     factsheet does not state one. NEVER
                                     defaulted to USD.
      "total_aum": 12345678901.0,
      "holdings": [
        {"ticker_raw": "AAPL", "name": "...", "weight": 0.0723, "isin": "US..."}
      ]
    }
  ]
}
"""

import sys
import json
import re
import argparse
from pathlib import Path
from collections import defaultdict

# Exchange suffixes that indicate non-US primary listings — drop these.
_DROP_SUFFIXES = {
    ".T", ".HK", ".TW", ".L", ".SS", ".SZ", ".PA", ".DE", ".AS",
    ".MI", ".MC", ".TO", ".AX", ".KS", ".SI", ".BK",
}

# US exchange suffixes to strip (normalize to clean ticker).
# `.A` is deliberately omitted: in modern equity data feeds it overwhelmingly
# means share class A (BRK.A vs BRK.B are *different securities*), not the
# legacy NYSE-American exchange flag. Stripping `.A` would conflate the two
# Berkshire share classes — neither EDGAR nor yfinance would resolve `BRK`
# to the correct row.
_STRIP_SUFFIXES = {" US", ".O", ".N", ".OQ", ".OB", ".PK"}

# ISIN prefix for US listings.
_US_ISIN_PREFIXES = {"US"}

# Non-equity classification — match as whole tokens, not substrings, so a
# company name like "Cashmere Inc" or "ETFix Industries" doesn't get dropped.
# Multi-word phrases use `\s+` so "money market" / "money  market" / "money\tmarket"
# all match while still requiring the words to be adjacent.
_NON_EQUITY_RE = re.compile(
    r"\b(?:"
    r"cash|bonds?|treasury|derivatives?|options?|futures?|"
    r"etfs?|money\s+market|currenc(?:y|ies)|swaps?|warrants?|"
    r"index\s+funds?|repo|repurchase\s+agreements?|"
    r"commercial\s+papers?"
    r")\b",
    re.IGNORECASE,
)

# Minimum holdings to keep a fund (§3.1.2 D9).
_MIN_HOLDINGS = 5
# Minimum weight fraction of total AUM to keep a fund.
_MIN_AUM_WEIGHT = 0.20
# v0.32 G2: upper edge of the "thin US exposure" band. A fund between
# _MIN_AUM_WEIGHT and this value passes the viability gate but its US sleeve is
# marginal — so its vote in the consensus signal rests on very little. Flagged,
# never rejected and never down-weighted (that would change C, which is locked).
_THIN_US_WEIGHT_MAX = 0.35

# --- v0.32 G1: reporting-currency normalisation ------------------------------
# `currency` is a REQUIRED Stage 1a field. It is normalised to an ISO-4217 code
# here; anything that cannot be resolved unambiguously becomes None, which the
# aggregation step treats exactly like a non-USD currency (excluded, never
# converted). Defaulting to USD is precisely the silent assumption v0.32 removes.
_ISO4217_RE = re.compile(r"^[A-Z]{3}$")

# Only unambiguous spellings are mapped. A bare "$" could be USD, HKD, SGD or
# AUD, and "¥" could be JPY or CNY — those resolve to None, not to a guess.
_AMBIGUOUS_CURRENCY_TOKENS = {"$", "¥", "￥", "元"}

_CURRENCY_ALIASES = {
    "US$": "USD", "USD$": "USD", "US DOLLAR": "USD", "US DOLLARS": "USD",
    "UNITED STATES DOLLAR": "USD",
    "HK$": "HKD", "HKD$": "HKD", "HONG KONG DOLLAR": "HKD",
    "HONG KONG DOLLARS": "HKD",
    "EURO": "EUR", "EUROS": "EUR", "€": "EUR",
    "£": "GBP", "STERLING": "GBP", "POUND STERLING": "GBP",
    "RMB": "CNY", "RENMINBI": "CNY",
}


def normalize_currency(raw) -> str | None:
    """Normalise a reported currency to an ISO-4217 code, or None (G1.1).

    None means "not stated / not resolvable". It is NEVER a synonym for USD:
    downstream, None and a non-USD code follow the same path (excluded from the
    exit-liquidity aggregate). No FX conversion exists anywhere in this codebase
    by design — see references/crowding_signal.md.
    """
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    if s in _AMBIGUOUS_CURRENCY_TOKENS:
        return None
    # "U.S. DOLLAR" -> "US DOLLAR"; "U.S.D" -> "USD"
    key = " ".join(s.replace(".", "").split())
    if key in _AMBIGUOUS_CURRENCY_TOKENS:
        return None
    if s in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[s]
    if key in _CURRENCY_ALIASES:
        return _CURRENCY_ALIASES[key]
    if _ISO4217_RE.match(key):
        return key
    return None


def is_thin_us_exposure(weight_kept: float | None) -> bool:
    """v0.32 G2: accepted fund whose US sleeve sits just above the viability line."""
    if not isinstance(weight_kept, (int, float)):
        return False
    return _MIN_AUM_WEIGHT <= float(weight_kept) <= _THIN_US_WEIGHT_MAX


def is_non_equity(h: dict) -> bool:
    name = h.get("name") or ""
    return bool(_NON_EQUITY_RE.search(name))


# Accept 1–5 letter base, optionally followed by a 1–2 letter share-class
# suffix after a dot. Covers `AAPL`, `BRK.B`, `LGF.A`, `BAC.PB` (preferred B
# series, which the v1 regex with `[A-Z]?` would have rejected).
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$")


def normalize_us_ticker(raw: str) -> str | None:
    """
    Strip exchange suffixes. Returns normalized ticker for US listings,
    or None if the ticker indicates a non-US primary listing.
    """
    t = (raw or "").strip().upper()

    # Drop non-US suffixes
    for suffix in _DROP_SUFFIXES:
        if t.endswith(suffix):
            return None

    # Strip US-exchange suffixes to get clean ticker
    for suffix in sorted(_STRIP_SUFFIXES, key=len, reverse=True):
        if t.upper().endswith(suffix.upper()):
            t = t[: -len(suffix)].strip()
            break

    if not t or not _TICKER_RE.match(t):
        return None

    return t


def is_us_by_isin(isin: str | None) -> bool:
    if not isin:
        return False
    return isin[:2].upper() in _US_ISIN_PREFIXES


def filter_fund_holdings(fund: dict) -> tuple[list[dict], dict]:
    """
    Filter a fund's holdings to US equities only.
    Returns (kept_holdings, scope_summary).
    """
    raw_holdings = fund.get("holdings", [])
    kept, dropped_non_us, dropped_non_equity = [], [], []

    for h in raw_holdings:
        raw = h.get("ticker_raw") or h.get("ticker", "")
        isin = h.get("isin")

        if is_non_equity(h):
            dropped_non_equity.append(raw)
            continue

        normalized = normalize_us_ticker(raw)

        if normalized is None:
            # Try ISIN fallback
            if is_us_by_isin(isin):
                # Use ISIN-derived ticker if possible (LLM extraction should handle this)
                normalized = h.get("ticker_resolved") or None

        if normalized is None:
            dropped_non_us.append(raw)
            continue

        kept.append({**h, "ticker_normalized": normalized})

    weight_kept = sum(h.get("weight", 0) for h in kept)
    weight_dropped = sum(h.get("weight", 0) for h in raw_holdings) - weight_kept

    scope_summary = {
        "n_holdings_total": len(raw_holdings),
        "n_holdings_kept_us_equity": len(kept),
        "n_dropped_non_us": len(dropped_non_us),
        "n_dropped_non_equity": len(dropped_non_equity),
        "tickers_dropped_non_us": dropped_non_us,
        "tickers_dropped_non_equity": dropped_non_equity,
        "weight_kept": round(weight_kept, 4),
        "weight_dropped": round(weight_dropped, 4),
    }
    return kept, scope_summary


def check_fund_viability(fund: dict, kept: list, aum: float | None) -> tuple[bool, str]:
    """Apply rejection thresholds per §3.1.2 (D9)."""
    if len(kept) < _MIN_HOLDINGS:
        return False, f"Only {len(kept)} US equity holdings extracted (minimum {_MIN_HOLDINGS})"
    if aum and aum > 0:
        weight_sum = sum(h.get("weight", 0) for h in kept)
        if weight_sum < _MIN_AUM_WEIGHT:
            return False, (
                f"US equity holdings sum to {weight_sum:.1%} of AUM "
                f"(minimum {_MIN_AUM_WEIGHT:.0%})"
            )
    return True, ""


def dedupe(holdings_data: dict) -> dict:
    """Build unique_universe from all kept (US equity) holdings."""
    universe: dict[str, dict] = defaultdict(lambda: {
        "ticker": None,
        "name": None,
        "held_by": [],
        "weights_by_fund": {},
    })

    valid_funds = [f for f in holdings_data.get("funds", []) if not f.get("rejected")]

    for fund in valid_funds:
        fid = fund["fund_id"]
        for h in fund.get("holdings_us", []):
            tkr = h.get("ticker_normalized") or h.get("ticker_raw", "")
            entry = universe[tkr]
            entry["ticker"] = tkr
            entry["name"] = entry["name"] or h.get("name")
            entry["held_by"].append(fid)
            entry["weights_by_fund"][fid] = h.get("weight", 0.0)

    result = []
    for tkr, e in universe.items():
        weights = list(e["weights_by_fund"].values())
        e["n_funds_holding"] = len(e["held_by"])
        e["max_weight"] = round(max(weights), 4) if weights else 0.0
        e["avg_weight"] = round(sum(weights) / len(weights), 4) if weights else 0.0
        e["sum_of_weights"] = round(sum(weights), 4)
        result.append(e)

    result.sort(key=lambda x: (-x["n_funds_holding"], -x["max_weight"]))
    holdings_data["unique_universe"] = result
    holdings_data["universe_size"] = len(result)
    return holdings_data


def add_pit_snapshot_info(holdings_data: dict) -> dict:
    """Stage 1d: Group snapshots by (fund_family, asof) for PIT tracking."""
    pit_info = []
    for fund in holdings_data.get("funds", []):
        if fund.get("rejected"):
            continue
        # Most users supply one snapshot per fund → single_snapshot_mode
        asof = fund.get("asof", "unknown")
        pit_info.append({
            "fund_id": fund["fund_id"],
            "fund_name": fund.get("fund_name"),
            "snapshots_available": 1,
            "date_range": asof,
            "mode": "single_snapshot",
        })
    holdings_data["pit_snapshot_info"] = pit_info
    return holdings_data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to holdings.json from Stage 1a")
    ap.add_argument("--dedupe", action="store_true")
    ap.add_argument("--out", help="Output path (defaults to overwrite input)")
    args = ap.parse_args()

    path = Path(args.input)
    data = json.loads(path.read_text(encoding="utf-8"))

    rejected_funds = []
    valid_count = 0

    for fund in data.get("funds", []):
        kept, scope = filter_fund_holdings(fund)
        fund["scope_summary"] = scope

        # G1.1: normalise the reporting currency before anything reads it. The
        # raw string is preserved so the Layer 1 table can show what the
        # factsheet actually said when it did not resolve.
        raw_currency = fund.get("currency")
        normalized_currency = normalize_currency(raw_currency)
        if raw_currency is not None and raw_currency != normalized_currency:
            fund["currency_raw"] = raw_currency
        fund["currency"] = normalized_currency

        viable, reason = check_fund_viability(fund, kept, fund.get("total_aum"))
        if not viable:
            fund["rejected"] = True
            fund["rejection_reason"] = reason
            rejected_funds.append(fund["fund_id"])
            print(f"REJECTED {fund['fund_id']} ({fund.get('fund_name')}): {reason}", file=sys.stderr)
        else:
            fund["rejected"] = False
            fund["holdings_us"] = kept
            # G2: warn on a marginal pass. Advisory only — the fund is accepted
            # in full and its consensus contribution is untouched.
            fund["thin_us_exposure"] = is_thin_us_exposure(scope.get("weight_kept"))
            if fund["thin_us_exposure"]:
                print(
                    f"THIN US EXPOSURE {fund['fund_id']} ({fund.get('fund_name')}): "
                    f"US equity is {scope.get('weight_kept', 0):.1%} of AUM "
                    f"({_MIN_AUM_WEIGHT:.0%}–{_THIN_US_WEIGHT_MAX:.0%} band) — accepted, "
                    "but its consensus vote rests on a marginal US sleeve.",
                    file=sys.stderr,
                )
            if normalized_currency != "USD":
                stated = (
                    f"reports AUM in {normalized_currency}"
                    if normalized_currency
                    else "does not state a reporting currency"
                )
                print(
                    f"NON-USD AUM {fund['fund_id']} ({fund.get('fund_name')}): {stated} "
                    "— excluded from the days-to-liquidate aggregate (no FX conversion "
                    "is performed); affected tickers fall back to NAV-only crowding.",
                    file=sys.stderr,
                )
            valid_count += 1

    if valid_count < 7:
        print(
            f"ERROR: Only {valid_count} funds passed extraction (need >= 7). "
            f"Rejected: {rejected_funds}. "
            "Please replace failed PDFs with factsheets that include clear holdings tables.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.dedupe:
        data = dedupe(data)
        data = add_pit_snapshot_info(data)

    out_path = Path(args.out) if args.out else path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    accepted = [f for f in data.get("funds", []) if not f.get("rejected")]
    n_thin = sum(1 for f in accepted if f.get("thin_us_exposure"))
    n_non_usd = sum(1 for f in accepted if f.get("currency") != "USD")
    print(f"Funds accepted: {valid_count} | Rejected: {len(rejected_funds)} "
          f"| Thin US exposure: {n_thin} | Non-USD/unstated AUM: {n_non_usd}")
    if args.dedupe:
        print(f"Universe: {data.get('universe_size', 0)} unique US-listed tickers")


if __name__ == "__main__":
    main()
