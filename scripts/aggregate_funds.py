"""
Stage 5: Aggregate per-stock scores up to fund level using actual holding
weights. For each fund, produce industry/growth/quality_value/3-strategy
composite scores plus top contributors / draggers.
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict


def weighted_avg(values_with_weights):
    """Weighted average ignoring None values; return None if no valid data."""
    pairs = [(v, w) for v, w in values_with_weights if v is not None and w is not None]
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w == 0:
        return None
    return round(sum(v * w for v, w in pairs) / total_w, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True)
    ap.add_argument("--scores", required=True, help="scores_strategies.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))["stocks"]

    fund_aggregates = []

    for fund in holdings.get("funds", []):
        fund_holdings = fund.get("holdings", [])

        # Collect per-stock score, weight tuples
        ind_pairs, grw_pairs, qv_pairs = [], [], []
        gr_pairs, co_pairs, ra_pairs = [], [], []
        contributors = []
        industry_weights = defaultdict(float)

        for h in fund_holdings:
            tkr_norm = h.get("ticker_normalized") or h["ticker"]
            # Fall back to looking up by raw ticker too
            sc = scores.get(tkr_norm) or scores.get(h["ticker"])
            if sc is None or sc.get("status") != "ok":
                continue
            w = h.get("weight", 0)

            ind_pairs.append((sc.get("industry_score"), w))
            grw_pairs.append((sc.get("growth_score"), w))
            qv_pairs.append((sc.get("quality_value_score"), w))
            ss = sc.get("strategy_scores") or {}
            gr_pairs.append((ss.get("growth"), w))
            co_pairs.append((ss.get("conservative"), w))
            ra_pairs.append((ss.get("risk_avoidance"), w))

            industry_weights[sc.get("industry") or "other"] += w

            contributors.append({
                "ticker": tkr_norm,
                "weight": w,
                "neutral_total_score": sc.get("neutral_total_score"),
                "growth_strategy_score": ss.get("growth"),
                "conservative_strategy_score": ss.get("conservative"),
                "risk_avoidance_strategy_score": ss.get("risk_avoidance"),
            })

        # Top contributors and draggers (by neutral score × weight)
        ranked = sorted(
            [c for c in contributors if c["neutral_total_score"] is not None],
            key=lambda c: c["neutral_total_score"] * c["weight"],
            reverse=True,
        )
        top5 = ranked[:5]
        bottom5 = ranked[-5:][::-1] if len(ranked) >= 5 else ranked[::-1]

        # Industry concentration
        max_industry = max(industry_weights.items(), key=lambda kv: kv[1]) if industry_weights else (None, 0)
        max_ind_name, max_ind_weight = max_industry

        agg = {
            "fund_id": fund.get("fund_id"),
            "fund_name": fund.get("fund_name"),
            "fund_type": fund.get("fund_type"),
            "currency": fund.get("currency"),
            "n_holdings_scored": len(contributors),
            "industry_score": weighted_avg(ind_pairs),
            "growth_score": weighted_avg(grw_pairs),
            "quality_value_score": weighted_avg(qv_pairs),
            "strategy_scores": {
                "growth": weighted_avg(gr_pairs),
                "conservative": weighted_avg(co_pairs),
                "risk_avoidance": weighted_avg(ra_pairs),
            },
            "industry_breakdown": dict(sorted(industry_weights.items(), key=lambda kv: -kv[1])),
            "max_industry": max_ind_name,
            "max_industry_weight": round(max_ind_weight, 4),
            "max_industry_breach_30pct": max_ind_weight > 0.30,
            "top_contributors": top5,
            "top_draggers": bottom5,
        }
        fund_aggregates.append(agg)

    out = {"funds": fund_aggregates}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"Aggregated {len(fund_aggregates)} funds → {args.out}")


if __name__ == "__main__":
    main()