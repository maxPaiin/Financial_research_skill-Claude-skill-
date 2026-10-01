"""
Stage 2f-iii (v0.4 B6): exit liquidity — and the input review that travels with it.

v0.4 moves crowding out of the rank (DEC-4). v0.3's discount measured NAV
weight — conviction — rather than exit risk: its weight term saturated at a
10% average weight, which is also the single-issuer ceiling, and its liquidity
term could only add to the discount (F2). Position size no longer lowers a
stock's rank; the consensus signal lives in consensus_signal.py. What remains
here is the one crowding question the factsheets can answer — how long would
it take these funds to sell — and it feeds the coherence overlay as a
demotion-only risk check (coherence_audit.py, `exit_liquidity`).

  aggregate_position_usd = sum over USD-reporting holders of fund_AUM x weight
  days_to_liquidate      = aggregate_position_usd / ADV_usd
  is_exit_crowded        = days_to_liquidate >= DTL_FULL (10)

DTL_FULL = 10 is a round, uncalibrated number — there is no backtest to fit it
against — and it is labelled as such wherever it is shown. The formula assumes
every holder exits at once, the tail-risk framing. Each figure is labelled
`liquidity-inclusive` (AUM and ADV available) or `no-liquidity-data`.

Seven to eleven Hong Kong-distributed funds are too small to crowd US large
caps, and global crowding cannot be measured from factsheets; this check flags
only what these holders alone would take to unwind.

v0.32 G1 — the numerator must be USD. ADV is always USD, so a fund reporting
AUM in HKD or JPY would inflate days_to_liquidate by roughly the FX rate,
silently. `fund_aum_map()` therefore admits AUM ONLY from funds whose
normalised `currency == "USD"`; non-USD and unstated funds are excluded (never
converted). No FX conversion exists in this codebase.

The input review (currency census, thin-US-exposure report) and the fund-style
distribution are carried here for Layer 2 and Appendix 3. They are disclosure
only: nothing reads them back to change a number.

Inputs:
  --overlap        overlap.json (holders and weights per ticker)
  --holdings       holdings.json (optional; fund AUM, currency and style)
  --fundamentals   fundamentals.json (optional; per-ticker ADV in USD)
  --out            crowding_signals.json

Output schema — crowding_signals.json (spec §7.4):
{
  "n_signals": 100,
  "dtl_threshold": 10.0,
  "homogeneity": {...display only...},
  "input_review": {"currency": {...}, "thin_us_exposure": {...}},
  "signals": [
    {"ticker": "AAPL", "days_to_liquidate": 0.06,
     "liquidity_label": "liquidity-inclusive", "is_exit_crowded": false,
     "aggregate_position_usd": 2.1e9, "n_holders": 5, "n_usd_aum_holders": 3}
  ]
}
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from extract_holdings import is_accepted

# Days-to-liquidate at/above which a position is exit-crowded. Uncalibrated —
# a round number separating "days" from "weeks"; labelled as such in reports.
_DTL_FULL = 10.0

# Input-set homogeneity (display only): dominant style share at/above which
# the run's style distribution is flagged homogeneous (Appendix 3).
_HOMOGENEITY_THRESHOLD = 0.80

# Coarse style vocabulary (must match Stage 1a fund-style inference).
_KNOWN_STYLES = {
    "value", "growth", "blend", "income_dividend",
    "sector_specific", "small_mid_cap", "region_tilt_non_us",
}

LIQUIDITY_INCLUSIVE = "liquidity-inclusive"
NO_LIQUIDITY_DATA = "no-liquidity-data"


@dataclass
class ExitLiquidity:
    ticker: str
    days_to_liquidate: Optional[float]
    liquidity_label: str        # "liquidity-inclusive" | "no-liquidity-data"
    is_exit_crowded: bool       # days_to_liquidate >= _DTL_FULL (uncalibrated)


def compute(
    ticker: str,
    adv_usd: Optional[float] = None,
    aggregate_position_usd: Optional[float] = None,
) -> ExitLiquidity:
    """Days-to-liquidate for one ticker, or a no-liquidity-data label.

    Both inputs are USD: ADV always is, and the aggregate admits USD-reported
    AUM only (fund_aum_map). Either missing -> no figure, never a guess.
    """
    if (adv_usd and adv_usd > 0
            and aggregate_position_usd is not None and aggregate_position_usd > 0):
        dtl = aggregate_position_usd / adv_usd
        return ExitLiquidity(ticker, round(dtl, 4), LIQUIDITY_INCLUSIVE, dtl >= _DTL_FULL)
    return ExitLiquidity(ticker, None, NO_LIQUIDITY_DATA, False)


def _accepted_funds(holdings: dict) -> list[dict]:
    # v0.4 B1: a share class merged into its identical twin is not a second fund.
    return [f for f in holdings.get("funds", []) if is_accepted(f)]


def fund_style_map(holdings: dict) -> dict[str, str]:
    """fund_id -> coarse style label, over accepted funds only (A3).

    Display only (v0.4): style labels are LLM-inferred and never enter the
    rank (I9). A fund's reporting currency has no bearing here: G1.2 excludes
    non-USD AUM from the exit-liquidity aggregate only.
    """
    style_by_fund: dict[str, str] = {}
    for f in _accepted_funds(holdings):
        style = f.get("style")
        # `style` may be a single label or a list; take the first known label.
        if isinstance(style, list):
            style = next((s for s in style if s in _KNOWN_STYLES), None)
        if isinstance(style, str) and style in _KNOWN_STYLES:
            style_by_fund[f["fund_id"]] = style
    return style_by_fund


def fund_aum_map(holdings: dict) -> tuple[dict[str, float], dict]:
    """fund_id -> total_aum for USD reporters only (v0.32 G1.2), + a report.

    INVARIANT — every value in the returned map is denominated in USD. The sum
    built from it (`aggregate_position_usd`) is therefore USD-true, which is
    what makes `days_to_liquidate = aggregate_position_usd / adv_usd` a ratio of
    like units. ADV is always USD; admitting an HKD- or JPY-reported AUM here
    would overstate days-to-liquidate by roughly the FX rate, silently.

    A fund whose currency is non-USD *or* null is omitted from the map. This
    needs no new logic downstream: a fund without usable AUM drops out of the
    aggregate, and a ticker left with no usable AUM is labelled
    `no-liquidity-data`. Exclusion — never conversion:
    FX would require a rate source, a rate-date policy and a new provenance
    path, three new failure modes to repair a metric that already degrades
    cleanly (G1.3). **Do not add FX conversion here.**
    """
    accepted = _accepted_funds(holdings)
    aum_by_fund: dict[str, float] = {}
    by_currency: dict[str, int] = {}
    excluded: list[dict] = []
    n_missing_aum = 0

    for f in accepted:
        fid = f["fund_id"]
        currency = f.get("currency")
        label = currency if isinstance(currency, str) and currency else "unstated"
        by_currency[label] = by_currency.get(label, 0) + 1

        aum = f.get("total_aum")
        has_aum = isinstance(aum, (int, float)) and not isinstance(aum, bool) and aum > 0

        if currency == "USD":
            if has_aum:
                aum_by_fund[fid] = float(aum)
            else:
                n_missing_aum += 1
            continue

        # Non-USD or unstated: excluded from the aggregate, and named so the
        # exclusion is visible rather than silent (G1.4).
        if has_aum:
            excluded.append({
                "fund_id": fid,
                "fund_name": f.get("fund_name"),
                "currency": currency,
            })

    report = {
        "n_funds": len(accepted),
        "by_currency": dict(sorted(by_currency.items(), key=lambda kv: (-kv[1], kv[0]))),
        "n_usd_aum_used": len(aum_by_fund),
        "n_excluded_for_currency": len(excluded),
        "excluded_funds": excluded,
        "n_usd_missing_aum": n_missing_aum,
        "fx_conversion": False,
    }
    return aum_by_fund, report


def thin_exposure_report(holdings: dict) -> dict:
    """v0.32 G2: accepted funds flagged thin at Stage 1b, for disclosure only.

    Nothing reads the flag to change a number: a thin fund's votes count
    in full in consensus_signal.py.
    """
    accepted = _accepted_funds(holdings)
    thin = [
        {
            "fund_id": f["fund_id"],
            "fund_name": f.get("fund_name"),
            "weight_kept": (f.get("scope_summary") or {}).get("weight_kept"),
        }
        for f in accepted
        if f.get("thin_us_exposure")
    ]
    return {
        "n_funds": len(accepted),
        "n_thin": len(thin),
        "share_thin": round(len(thin) / len(accepted), 4) if accepted else 0.0,
        "band": [0.20, 0.35],
        "funds": thin,
    }


def _fund_maps(holdings: dict) -> tuple[dict[str, float], dict[str, str], dict]:
    """Build the AUM (USD-only), style, and currency-report maps."""
    aum_by_fund, currency_report = fund_aum_map(holdings)
    return aum_by_fund, fund_style_map(holdings), currency_report


def homogeneity_report(style_by_fund: dict[str, str], n_funds: int) -> dict:
    """Run-level style concentration over the input set of funds (display only)."""
    if not style_by_fund:
        return {
            "labelled": False,
            "dominant_style": None,
            "dominant_share": None,
            "is_homogeneous": False,
            "style_distribution": {},
            "n_funds": n_funds,
        }
    dist: dict[str, int] = {}
    for s in style_by_fund.values():
        dist[s] = dist.get(s, 0) + 1
    total = sum(dist.values())
    dominant_style, dominant_count = min(dist.items(), key=lambda kv: (-kv[1], kv[0]))
    dominant_share = dominant_count / total if total else 0.0
    return {
        "labelled": True,
        "dominant_style": dominant_style,
        "dominant_share": round(dominant_share, 4),
        "is_homogeneous": dominant_share >= _HOMOGENEITY_THRESHOLD,
        "style_distribution": dict(sorted(dist.items(), key=lambda kv: (-kv[1], kv[0]))),
        "n_funds": n_funds,
    }


def _adv_by_ticker(fundamentals: dict) -> dict[str, float]:
    """Extract adv USD per ticker from fundamentals.json (exit liquidity)."""
    out: dict[str, float] = {}
    for tkr, rec in fundamentals.items():
        adv = (rec or {}).get("adv")
        val = adv.get("value") if isinstance(adv, dict) else None
        if isinstance(val, (int, float)) and val > 0:
            out[tkr] = float(val)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlap", required=True, help="overlap.json from overlap_analysis.py")
    ap.add_argument("--holdings", help="holdings.json (fund AUM, currency, style). "
                                       "Optional: absent -> no liquidity data.")
    ap.add_argument("--fundamentals", help="fundamentals.json (per-ticker ADV in USD). "
                                           "Optional: absent -> no liquidity data.")
    ap.add_argument("--out", required=True, help="Output crowding_signals.json path")
    args = ap.parse_args()

    overlap = json.loads(Path(args.overlap).read_text(encoding="utf-8"))
    rows = overlap.get("overlap", [])

    aum_by_fund: dict[str, float] = {}
    style_by_fund: dict[str, str] = {}
    currency_report: dict = {}
    thin_report: dict = {}
    n_funds = 0
    if args.holdings:
        holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
        aum_by_fund, style_by_fund, currency_report = _fund_maps(holdings)
        thin_report = thin_exposure_report(holdings)
        n_funds = sum(1 for f in holdings.get("funds", []) if is_accepted(f))

    adv_by_ticker: dict[str, float] = {}
    if args.fundamentals:
        fundamentals = json.loads(Path(args.fundamentals).read_text(encoding="utf-8"))
        adv_by_ticker = _adv_by_ticker(fundamentals)

    homogeneity = homogeneity_report(style_by_fund, n_funds)

    signals: list[dict] = []
    for r in rows:
        ticker = r.get("ticker")
        if not ticker:
            continue
        held_by = r.get("held_by", []) or []
        weights_by_fund = r.get("weights_by_fund", {}) or {}

        # Aggregate position $ across holders that disclose a USD AUM.
        # `aum_by_fund` is USD-only by construction (G1.2), so this sum is
        # USD-true and its name is accurate rather than aspirational — do not
        # widen the map to other currencies without converting, and conversion
        # is deliberately out of scope.
        usd_holders = [fid for fid in held_by
                       if fid in aum_by_fund and isinstance(weights_by_fund.get(fid), (int, float))]
        aggregate_position_usd = (sum(aum_by_fund[fid] * weights_by_fund[fid] for fid in usd_holders)
                                  if usd_holders else None)

        result = compute(ticker, adv_by_ticker.get(ticker), aggregate_position_usd)
        signals.append({
            "ticker": result.ticker,
            "days_to_liquidate": result.days_to_liquidate,
            "liquidity_label": result.liquidity_label,
            "is_exit_crowded": result.is_exit_crowded,
            "aggregate_position_usd": round(aggregate_position_usd, 2)
            if aggregate_position_usd is not None else None,
            "n_holders": len(held_by),
            "n_usd_aum_holders": len(usd_holders),
        })

    out = {
        "n_signals": len(signals),
        "dtl_threshold": _DTL_FULL,
        "homogeneity": homogeneity,
        # v0.32 G4: the input-review findings that Layer 2 and Appendix 3 report.
        # Carried here because both already read this file; nothing below reads
        # them back to change a score.
        "input_review": {
            "currency": currency_report,
            "thin_us_exposure": thin_report,
        },
        "signals": signals,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    n_liq = sum(1 for x in signals if x["liquidity_label"] == LIQUIDITY_INCLUSIVE)
    n_crowded = sum(1 for x in signals if x["is_exit_crowded"])
    print(f"Exit liquidity: {len(signals)} tickers -> {out_path} "
          f"({n_liq} with days-to-liquidate, {n_crowded} at >= {_DTL_FULL:g} days; "
          f"currency_excluded={currency_report.get('n_excluded_for_currency', 0)}, "
          f"thin_funds={thin_report.get('n_thin', 0)})")


if __name__ == "__main__":
    main()
