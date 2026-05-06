"""
Stage 7: Build ranking tables.

Outputs rankings.json with:
  - stocks_by_growth        (top N by growth_score)
  - stocks_by_risk          (ascending, lowest risk first)
  - funds_by_growth_strategy
  - funds_by_conservative_strategy
  - funds_by_risk_avoidance_strategy
"""

import json
import argparse
from pathlib import Path


RISK_TIER_ORDER = {"very_low": 1, "low": 2, "medium": 3, "high": 4, "very_high": 5}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--top-n", type=int, default=20)
    args = ap.parse_args()

    wd = Path(args.work_dir)
    scores = json.loads((wd / "scores_strategies.json").read_text(encoding="utf-8"))["stocks"]
    fund_scores = json.loads((wd / "fund_scores.json").read_text(encoding="utf-8"))["funds"]
    risk_report = json.loads((wd / "risk_report.json").read_text(encoding="utf-8"))

    # Stocks by growth_score (top N)
    stocks = [r for r in scores.values() if r.get("status") == "ok"]
    by_growth = sorted(stocks, key=lambda r: -(r.get("growth_score") or 0))[:args.top_n]

    # Stocks by risk (ascending — safest first)
    by_risk = sorted(
        risk_report["stock_risk"],
        key=lambda r: (RISK_TIER_ORDER.get(r["risk_tier"], 99), r["ticker"]),
    )[:args.top_n]

    # Funds by each strategy
    def by_strat(name):
        return sorted(
            fund_scores,
            key=lambda f: -(f.get("strategy_scores", {}).get(name) or 0),
        )

    rankings = {
        "stocks_by_growth": [
            {
                "ticker": s["ticker"],
                "industry": s.get("industry"),
                "growth_score": s.get("growth_score"),
                "neutral_total_score": s.get("neutral_total_score"),
                "strategy_scores": s.get("strategy_scores"),
            }
            for s in by_growth
        ],
        "stocks_by_risk": by_risk,
        "funds_by_growth_strategy": by_strat("growth"),
        "funds_by_conservative_strategy": by_strat("conservative"),
        "funds_by_risk_avoidance_strategy": by_strat("risk_avoidance"),
    }

    out = wd / "rankings.json"
    out.write_text(json.dumps(rankings, indent=2, ensure_ascii=False, default=str))
    print(f"Rankings written to {out}")
    print(f"  Top growth stock:        {by_growth[0]['ticker']} ({by_growth[0].get('growth_score'):.1f})" if by_growth else "  (no stocks)")
    print(f"  Top conservative fund:   {rankings['funds_by_conservative_strategy'][0]['fund_name']}" if rankings['funds_by_conservative_strategy'] else "")


if __name__ == "__main__":
    main()