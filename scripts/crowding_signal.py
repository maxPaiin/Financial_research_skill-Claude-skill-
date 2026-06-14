"""
Stage 2f: Consensus-with-crowding-discount signal (v0.3).

Produces a single signal that combines how widely held a stock is (consensus)
with a discount for HK-channel crowding. Two separate signals would imply
independence that does not exist (§6 D6 decision).

v0.3 rebuilds *what consensus measures* so it carries risk information, not
crowd-following (premise 3 — "consensus is not alpha"):

  A2 — Exit-crowdedness (days-to-liquidate).
       The reflexive "everyone exits the same door" risk is position size
       *relative to exit liquidity*, not relative to NAV. We fold a bounded,
       increasing function of days_to_liquidate into the crowding discount:
         aggregate_position_$ = Σ_funds (fund_AUM × weight_in_fund)
         days_to_liquidate    = aggregate_position_$ / ADV_usd
         liq                  = clamp(days_to_liquidate / DTL_FULL, 0, 1)
         crowding_raw'        = crowding_raw × (1 + LIQ_WEIGHT × liq)
       The discount is still capped at MAX_DISCOUNT. The formula deliberately
       assumes *simultaneous exit by all holders* — the tail-risk framing the
       tool is meant to surface. Each stock is labelled `liquidity-inclusive`
       (the liquidity path produced the figure) or `NAV-only` (fell back to
       the v0.2 pure-weight discount because AUM and/or ADV were missing).

  A3 — Style-diversity-weighted consensus.
       A name held by funds spanning several distinct styles is more
       informative than the same number of single-style funds ("AAPL held by
       9/9 tech funds" carries ~zero information — the consensus is measuring
       the input bias). We weight consensus by holder style-diversity:
         diversity      = (n_distinct_styles - 1) / (n_funds_holding - 1)
         consensus'     = consensus_raw × (STYLE_MIN_FACTOR
                                           + (1 - STYLE_MIN_FACTOR) × diversity)
       Within-style agreement is pushed down; cross-style agreement up. When
       no style labels are present, the factor is 1.0 (no change) and the run
       is flagged style-unlabelled.

       Stratified sampling is ABANDONED for v0.3 (sample too small to stratify;
       token budget). The replacement is this diversity weighting plus a
       run-level homogeneity warning: if the *input set* of funds is
       style-homogeneous (>= HOMOGENEITY_THRESHOLD share one style), consensus
       in this run is largely uninformative and Appendix 3 says so.

Formula and tuning constants are the canonical location per §5.3.

Inputs:
  --overlap        overlap.json (produced by overlap_analysis.py)
  --holdings       holdings.json (optional; funds[].total_aum + funds[].style
                   for A2 aggregate-position and A3 style labels)
  --fundamentals   fundamentals.json (optional; per-ticker adv USD for A2)
  --out            crowding_signals.json

Output schema — crowding_signals.json:
{
  "n_signals": 100,
  "homogeneity": {
    "labelled": true,
    "dominant_style": "growth",
    "dominant_share": 0.82,
    "is_homogeneous": true,
    "style_distribution": {"growth": 8, "blend": 1},
    "n_funds": 9
  },
  "signals": [
    {"ticker": "AAPL",
     "consensus_raw": 1.95,
     "consensus_weighted": 1.40,
     "style_diversity": 0.25,
     "n_distinct_styles": 2,
     "crowding_discount": 0.18,
     "days_to_liquidate": 3.4,
     "crowding_label": "liquidity-inclusive",
     "signal": 1.15,
     "is_high_crowding": false},
    ...
  ]
}
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Canonical tuning constants — do not duplicate elsewhere.
# Tuning notes: starting defaults, may be calibrated later.
_AVG_WEIGHT_THRESHOLD = 0.02    # below this, no crowding discount applies
_WEIGHT_RANGE = 0.08            # range to full discount: at avg_weight = 10%, full discount
_FUND_DENOMINATOR = 5.0         # 5+ funds at moderate weight starts to suggest crowding
_MAX_DISCOUNT = 0.60            # cap crowding discount at 60%

# A2 days-to-liquidate constants (v0.3) — starting defaults, calibrate later.
_DTL_FULL = 10.0               # days_to_liquidate at/above which liq amplifier saturates
_LIQ_WEIGHT = 0.50            # max fractional uplift to crowding_raw from full illiquidity

# A3 style-diversity constants (v0.3).
# A fully style-homogeneous consensus retains STYLE_MIN_FACTOR of its weight;
# a fully style-diverse consensus retains 1.0.
_STYLE_MIN_FACTOR = 0.50
# Input-set homogeneity: dominant style share at/above which the run's
# consensus is flagged "largely uninformative" (Appendix 3 payload).
_HOMOGENEITY_THRESHOLD = 0.80

# Coarse style vocabulary (must match Stage 1a fund-style inference / A3).
_KNOWN_STYLES = {
    "value", "growth", "blend", "income_dividend",
    "sector_specific", "small_mid_cap", "region_tilt_non_us",
}


@dataclass
class CrowdingResult:
    ticker: str
    consensus_raw: float
    consensus_weighted: float
    style_diversity: Optional[float]
    n_distinct_styles: Optional[int]
    crowding_discount: float
    days_to_liquidate: Optional[float]
    crowding_label: str         # "liquidity-inclusive" | "NAV-only"
    signal: float               # consensus_weighted * (1 - crowding_discount)
    is_high_crowding: bool      # True when crowding_discount >= 0.30


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def style_diversity_factor(
    holder_styles: Optional[list[str]],
    n_funds_holding: int,
) -> tuple[Optional[float], Optional[int], float]:
    """Return (diversity, n_distinct_styles, consensus_factor).

    diversity in [0, 1]: 0 when all holders share one style, ->1 when many
    distinct styles. consensus_factor maps that onto [STYLE_MIN_FACTOR, 1].
    When styles are unavailable, returns (None, None, 1.0) — no weighting.
    """
    styles = [s for s in (holder_styles or []) if s]
    if not styles or n_funds_holding < 2:
        # No style info, or a single holder (consensus carries no info anyway).
        return None, None, 1.0
    n_distinct = len(set(styles))
    diversity = (n_distinct - 1) / max(n_funds_holding - 1, 1)
    diversity = _clamp(diversity, 0.0, 1.0)
    factor = _STYLE_MIN_FACTOR + (1.0 - _STYLE_MIN_FACTOR) * diversity
    return round(diversity, 4), n_distinct, factor


def compute(
    ticker: str,
    n_funds_holding: int,
    avg_weight: float,
    adv_usd: Optional[float] = None,
    aggregate_position_usd: Optional[float] = None,
    holder_styles: Optional[list[str]] = None,
) -> CrowdingResult:
    """
    Compute the consensus-with-crowding-discount signal for one ticker.

    Args:
        ticker: stock ticker
        n_funds_holding: number of funds in the universe holding this ticker
        avg_weight: mean weight across funds where the ticker is held (decimal, e.g. 0.05)
        adv_usd: average daily traded value in USD (A2 exit-liquidity); None -> NAV-only
        aggregate_position_usd: Σ fund_AUM × weight (A2); None -> NAV-only
        holder_styles: style labels of the funds holding the ticker (A3)
    """
    consensus_raw = math.log(1 + n_funds_holding)

    # A3: style-diversity weighting of consensus.
    diversity, n_distinct, style_factor = style_diversity_factor(
        holder_styles, n_funds_holding
    )
    consensus_weighted = consensus_raw * style_factor

    # Base (v0.2) NAV-relative crowding.
    crowding_raw = (
        max(0.0, (avg_weight - _AVG_WEIGHT_THRESHOLD) / _WEIGHT_RANGE)
        * (n_funds_holding / _FUND_DENOMINATOR)
    )

    # A2: fold days-to-liquidate into the discount when liquidity data exists.
    days_to_liquidate: Optional[float] = None
    crowding_label = "NAV-only"
    if (adv_usd and adv_usd > 0
            and aggregate_position_usd is not None and aggregate_position_usd > 0):
        days_to_liquidate = aggregate_position_usd / adv_usd
        liq = _clamp(days_to_liquidate / _DTL_FULL, 0.0, 1.0)
        crowding_raw = crowding_raw * (1.0 + _LIQ_WEIGHT * liq)
        crowding_label = "liquidity-inclusive"

    crowding_discount = min(crowding_raw, _MAX_DISCOUNT)
    signal = consensus_weighted * (1 - crowding_discount)

    return CrowdingResult(
        ticker=ticker,
        consensus_raw=round(consensus_raw, 4),
        consensus_weighted=round(consensus_weighted, 4),
        style_diversity=diversity,
        n_distinct_styles=n_distinct,
        crowding_discount=round(crowding_discount, 4),
        days_to_liquidate=round(days_to_liquidate, 4) if days_to_liquidate is not None else None,
        crowding_label=crowding_label,
        signal=round(signal, 4),
        is_high_crowding=crowding_discount >= 0.30,
    )


def _fund_maps(holdings: dict) -> tuple[dict[str, float], dict[str, str]]:
    """Build fund_id -> total_aum and fund_id -> style maps from holdings.json.

    Only non-rejected funds are considered. total_aum is optional (recommended,
    not required, at extraction); funds without it are simply absent from the
    AUM map, which downgrades their tickers to NAV-only.
    """
    aum_by_fund: dict[str, float] = {}
    style_by_fund: dict[str, str] = {}
    for f in holdings.get("funds", []):
        if f.get("rejected"):
            continue
        fid = f.get("fund_id")
        if not fid:
            continue
        aum = f.get("total_aum")
        if isinstance(aum, (int, float)) and aum > 0:
            aum_by_fund[fid] = float(aum)
        style = f.get("style")
        # `style` may be a single label or a list; take the first known label.
        if isinstance(style, list):
            style = next((s for s in style if s in _KNOWN_STYLES), None)
        if isinstance(style, str) and style in _KNOWN_STYLES:
            style_by_fund[fid] = style
    return aum_by_fund, style_by_fund


def homogeneity_report(style_by_fund: dict[str, str], n_funds: int) -> dict:
    """Run-level style concentration over the input set of funds (A3)."""
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
    dominant_style, dominant_count = max(dist.items(), key=lambda kv: kv[1])
    dominant_share = dominant_count / total if total else 0.0
    return {
        "labelled": True,
        "dominant_style": dominant_style,
        "dominant_share": round(dominant_share, 4),
        "is_homogeneous": dominant_share >= _HOMOGENEITY_THRESHOLD,
        "style_distribution": dict(sorted(dist.items(), key=lambda kv: -kv[1])),
        "n_funds": n_funds,
    }


def _adv_by_ticker(fundamentals: dict) -> dict[str, float]:
    """Extract adv USD per ticker from fundamentals.json (A2 exit-liquidity)."""
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
    ap.add_argument("--holdings", help="holdings.json (A2 fund AUM + A3 fund styles). "
                                       "Optional: absent -> NAV-only, style-unlabelled.")
    ap.add_argument("--fundamentals", help="fundamentals.json (A2 per-ticker adv USD). "
                                           "Optional: absent -> NAV-only.")
    ap.add_argument("--out", required=True, help="Output crowding_signals.json path")
    args = ap.parse_args()

    overlap = json.loads(Path(args.overlap).read_text(encoding="utf-8"))
    rows = overlap.get("overlap", [])

    aum_by_fund: dict[str, float] = {}
    style_by_fund: dict[str, str] = {}
    n_funds = 0
    if args.holdings:
        holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
        aum_by_fund, style_by_fund = _fund_maps(holdings)
        n_funds = sum(1 for f in holdings.get("funds", []) if not f.get("rejected"))

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

        # A2: aggregate position $ across holders that disclose AUM. If no
        # holder discloses AUM, aggregate is None -> NAV-only fallback.
        aggregate_position_usd: Optional[float] = None
        if aum_by_fund:
            acc = 0.0
            any_aum = False
            for fid in held_by:
                aum = aum_by_fund.get(fid)
                w = weights_by_fund.get(fid)
                if aum is not None and isinstance(w, (int, float)):
                    acc += aum * w
                    any_aum = True
            if any_aum:
                aggregate_position_usd = acc

        # A3: styles of the funds holding this ticker.
        holder_styles = [style_by_fund[fid] for fid in held_by if fid in style_by_fund]

        result = compute(
            ticker=ticker,
            n_funds_holding=int(r.get("n_funds_holding", 0)),
            avg_weight=float(r.get("avg_weight", 0.0)),
            adv_usd=adv_by_ticker.get(ticker),
            aggregate_position_usd=aggregate_position_usd,
            holder_styles=holder_styles or None,
        )
        signals.append({
            "ticker": result.ticker,
            "consensus_raw": result.consensus_raw,
            "consensus_weighted": result.consensus_weighted,
            "style_diversity": result.style_diversity,
            "n_distinct_styles": result.n_distinct_styles,
            "crowding_discount": result.crowding_discount,
            "days_to_liquidate": result.days_to_liquidate,
            "crowding_label": result.crowding_label,
            "signal": result.signal,
            "is_high_crowding": result.is_high_crowding,
        })

    out = {
        "n_signals": len(signals),
        "homogeneity": homogeneity,
        "signals": signals,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Crowding signals: {len(signals)} -> {out_path} "
          f"(homogeneous={homogeneity['is_homogeneous']}, "
          f"dominant_style={homogeneity['dominant_style']})")


if __name__ == "__main__":
    main()
