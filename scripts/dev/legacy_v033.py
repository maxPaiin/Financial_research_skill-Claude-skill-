"""
Dev only (v0.4 B5): the v0.33 ranking, reproduced from a v0.4 work directory.

Never imported by the pipeline — only scripts/dev/compare_rankings.py uses it,
to put the v0.33 and v0.4 rankings of one input set side by side (spec §9).
It carries its own copy of the v0.33 consensus-with-crowding formulas and of
the 50/50 composite, so the pipeline could retire them (B5, B6) without losing
the comparison. The constants below are v0.33's (commit 3f7d89e), uncalibrated
then and uncalibrated now — they live only here (TestNoLegacyWeights).

Differences from a real v0.33 run, all upstream of the formulas: the inputs
are v0.4's — US scope from SEC's exchange file, identical share classes
merged, ROE from real annual series, Q'' shrunk by v0.33's data_confidence.
"""

from __future__ import annotations

import math
from typing import Optional

# --- v0.33 crowding_signal.py constants ---------------------------------------
_AVG_WEIGHT_THRESHOLD = 0.02
_WEIGHT_RANGE = 0.08
_FUND_DENOMINATOR = 5.0
_MAX_DISCOUNT = 0.60
_DTL_FULL = 10.0
_LIQ_WEIGHT = 0.50
_STYLE_MIN_FACTOR = 0.50
_KNOWN_STYLES = {"value", "growth", "blend", "income_dividend",
                 "sector_specific", "small_mid_cap", "region_tilt_non_us"}

# --- v0.33 build_rankings.py constants ----------------------------------------
_QUALITY_WEIGHT = 0.50
_CONSENSUS_WEIGHT = 0.50
_Q_LOW = 10.0
_DEFAULT_CONFIDENCE = 0.5
_TOP_N = 15


def v033_signal(n_funds_holding: int, avg_weight: float, adv_usd: Optional[float],
                aggregate_position_usd: Optional[float],
                holder_styles: Optional[list[str]]) -> float:
    """v0.33 consensus-with-crowding-discount signal for one ticker."""
    consensus_raw = math.log(1 + n_funds_holding)
    styles = [s for s in (holder_styles or []) if s]
    factor = 1.0
    if styles and n_funds_holding >= 2:
        diversity = max(0.0, min(1.0, (len(set(styles)) - 1) / max(n_funds_holding - 1, 1)))
        factor = _STYLE_MIN_FACTOR + (1.0 - _STYLE_MIN_FACTOR) * diversity
    crowding_raw = (max(0.0, (avg_weight - _AVG_WEIGHT_THRESHOLD) / _WEIGHT_RANGE)
                    * (n_funds_holding / _FUND_DENOMINATOR))
    if adv_usd and adv_usd > 0 and aggregate_position_usd and aggregate_position_usd > 0:
        liq = max(0.0, min(1.0, (aggregate_position_usd / adv_usd) / _DTL_FULL))
        crowding_raw *= 1.0 + _LIQ_WEIGHT * liq
    return consensus_raw * factor * (1 - min(crowding_raw, _MAX_DISCOUNT))


def _percentile(value: float, distribution: list[float]) -> float:
    n_below = sum(1 for v in distribution if v < value)
    n_equal = sum(1 for v in distribution if v == value)
    return round(100.0 * (n_below + 0.5 * n_equal) / len(distribution), 2)


def _fund_maps(holdings: dict) -> tuple[dict[str, float], dict[str, str]]:
    """USD-only AUM and v0.33's first-known style label, over accepted funds."""
    aum, style = {}, {}
    for f in holdings.get("funds", []):
        if f.get("rejected") or f.get("merged_into") or not f.get("fund_id"):
            continue
        a = f.get("total_aum")
        if f.get("currency") == "USD" and isinstance(a, (int, float)) and a > 0:
            aum[f["fund_id"]] = float(a)
        s = f.get("style")
        if isinstance(s, list):
            s = next((x for x in s if x in _KNOWN_STYLES), None)
        if isinstance(s, str) and s in _KNOWN_STYLES:
            style[f["fund_id"]] = s
    return aum, style


def legacy_rank(scores: dict, overlap: dict, holdings: dict) -> dict:
    """{"ranked": [...], "n_passed_universe": n} the way v0.33 ranked."""
    aum, style = _fund_maps(holdings)
    rows = {r["ticker"]: r for r in overlap.get("overlap", [])}
    candidates = []
    for ticker, s in scores.get("stocks", {}).items():
        q = s.get("fundamental_quality_score")
        row = rows.get(ticker)
        if s.get("status") != "ok" or q is None or row is None:
            continue
        held = row.get("held_by") or []
        weights = row.get("weights_by_fund") or {}
        agg = sum(aum[f] * weights.get(f, 0.0) for f in held if f in aum) or None
        signal = v033_signal(int(row.get("n_funds_holding", 0)), float(row.get("avg_weight", 0)),
                             s.get("adv"), agg, [style[f] for f in held if f in style] or None)
        c = s.get("data_confidence")
        c = max(0.0, min(1.0, float(c if c is not None else _DEFAULT_CONFIDENCE)))
        candidates.append({"ticker": ticker, "q_shrunk": round(c * q + (1 - c) * _Q_LOW, 2),
                           "signal": signal})
    signals = [c["signal"] for c in candidates]
    for c in candidates:
        c["composite_score"] = round(_QUALITY_WEIGHT * c["q_shrunk"]
                                     + _CONSENSUS_WEIGHT * _percentile(c["signal"], signals), 2)
    candidates.sort(key=lambda c: (-c["composite_score"], c["ticker"]))
    top = candidates[:_TOP_N]
    for i, c in enumerate(top, start=1):
        c["rank"] = i
    return {"ranked": top, "n_passed_universe": len(candidates)}
