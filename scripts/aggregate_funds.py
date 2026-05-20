"""
Stage 2 helper: Aggregate per-stock data to fund level.

Light rewrite from v1: reuses weighted_avg(), reshapes output for v0.2
Layer 2 contract (no strategy scores — single ranking only).
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict


def weighted_avg(values_with_weights: list[tuple]) -> float | None:
    """Weighted average ignoring None values; return None if no valid data."""
    pairs = [(v, w) for v, w in values_with_weights if v is not None and w is not None]
    if not pairs:
        return None
    total_w = sum(w for _, w in pairs)
    if total_w == 0:
        return None
    return round(sum(v * w for v, w in pairs) / total_w, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True)
    ap.add_argument("--scores", required=True, help="scores_per_stock.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))["stocks"]

    fund_aggregates = []

    for fund in holdings.get("funds", []):
        if fund.get("rejected"):
            continue

        fund_holdings = fund.get("holdings_us", [])
        fq_pairs = []
        industry_weights: dict[str, float] = defaultdict(float)
        contributors = []

        for h in fund_holdings:
            tkr = h.get("ticker_normalized") or h.get("ticker_raw", "")
            sc = scores.get(tkr)
            if sc is None or sc.get("status") != "ok":
                continue
            w = h.get("weight", 0.0)
            fq = sc.get("fundamental_quality_score")
            fq_pairs.append((fq, w))
            ind = sc.get("industry") or "other"
            industry_weights[ind] += w
            contributors.append({
                "ticker": tkr,
                "weight": w,
                "fundamental_quality_score": fq,
                "roe_5y_avg": sc.get("roe_5y_avg"),
            })

        ranked = sorted(
            [c for c in contributors if c["fundamental_quality_score"] is not None],
            key=lambda c: (c["fundamental_quality_score"] or 0) * c["weight"],
            reverse=True,
        )

        max_industry = max(industry_weights.items(), key=lambda kv: kv[1], default=(None, 0))

        fund_aggregates.append({
            "fund_id": fund.get("fund_id"),
            "fund_name": fund.get("fund_name"),
            "issuer": fund.get("issuer"),
            "asof": fund.get("asof"),
            "n_holdings_scored": len(contributors),
            "weighted_fundamental_quality": weighted_avg(fq_pairs),
            "industry_breakdown": dict(sorted(industry_weights.items(), key=lambda kv: -kv[1])),
            "max_industry": max_industry[0],
            "max_industry_weight": round(max_industry[1], 4),
            "top_contributors": ranked[:5],
            "top_draggers": list(reversed(ranked[-5:])) if len(ranked) >= 5 else [],
        })

    out = {"funds": fund_aggregates}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(f"Aggregated {len(fund_aggregates)} funds -> {args.out}")


if __name__ == "__main__":
    main()
