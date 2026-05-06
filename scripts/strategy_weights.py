"""
Stage 4: Apply the three strategy-specific weight schemes (Growth /
Conservative / Risk-avoidance) to per-stock scores. See
references/strategy_weights.md for rationale.

Reads scores_per_stock.json, writes scores_strategies.json (same shape with
a `strategy_scores` field appended per stock).
"""

import json
import argparse
from pathlib import Path


def safe(v, default=None):
    return v if v is not None else default


def growth_strategy(rec):
    ind = safe(rec.get("industry_score"))
    grw = safe(rec.get("growth_score"))
    qv = safe(rec.get("quality_value_score"))
    mom = rec.get("momentum_score")
    if None in (ind, grw, qv):
        return None
    base = 0.20 * ind + 0.60 * grw + 0.20 * qv
    if mom is not None:
        base += 0.10 * mom
    return round(base, 2)


def conservative_strategy(rec):
    ind = safe(rec.get("industry_score"))
    grw = safe(rec.get("growth_score"))
    qv = safe(rec.get("quality_value_score"))
    if None in (ind, grw, qv):
        return None
    return round(0.30 * ind + 0.20 * grw + 0.50 * qv, 2)


def risk_avoidance_strategy(rec, fund_industry_concentration: float):
    ind = safe(rec.get("industry_score"))
    grw = safe(rec.get("growth_score"))
    qv = safe(rec.get("quality_value_score"))
    if None in (ind, grw, qv):
        return None
    base = 0.40 * ind + 0.10 * grw + 0.50 * qv
    if fund_industry_concentration > 0.30:
        excess = fund_industry_concentration - 0.30
        penalty = min(excess * 100, 20)
        base -= penalty
    return round(max(base, 0), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True, help="scores_per_stock.json")
    ap.add_argument("--out", required=True, help="scores_strategies.json")
    ap.add_argument("--concentration-map", default=None,
                    help="Optional path to JSON mapping ticker -> fund_industry_concentration. "
                         "If absent, treats concentration as 0 (no penalty applied at this stage).")
    args = ap.parse_args()

    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))

    if args.concentration_map and Path(args.concentration_map).exists():
        conc_map = json.loads(Path(args.concentration_map).read_text(encoding="utf-8"))
    else:
        conc_map = {}

    for tkr, rec in scores["stocks"].items():
        if rec.get("status") != "ok":
            rec["strategy_scores"] = None
            continue
        conc = conc_map.get(tkr, 0.0)
        rec["strategy_scores"] = {
            "growth": growth_strategy(rec),
            "conservative": conservative_strategy(rec),
            "risk_avoidance": risk_avoidance_strategy(rec, conc),
        }
        rec["industry_concentration_at_fund_level"] = conc

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(scores, indent=2, ensure_ascii=False, default=str))
    print(f"Strategy scores written to {args.out}")


if __name__ == "__main__":
    main()