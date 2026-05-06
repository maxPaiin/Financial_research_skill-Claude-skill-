"""
Stage 6: Cross-fund overlap & risk analysis.

Outputs:
  1. Overlap matrix (which stocks appear in multiple funds, with weights).
  2. Industry concentration flags (per fund: industries > 30%).
  3. Per-stock risk rating (5 tiers based on volatility, beta, concentration).
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict


def risk_tier(volatility_proxy, beta, n_funds_holding, max_holding_weight):
    """Heuristic: combines volatility, beta, and how concentrated this stock is.
    Returns one of: very_low, low, medium, high, very_high."""
    score = 0   # higher = more risky

    # Volatility proxy: |6m return| as a rough liquidity/dispersion indicator.
    # Real implementation would use rolling stdev — left as TODO.
    if volatility_proxy is not None:
        if abs(volatility_proxy) > 0.30:
            score += 2
        elif abs(volatility_proxy) > 0.15:
            score += 1

    if beta is not None:
        if beta > 1.5:
            score += 2
        elif beta > 1.2:
            score += 1
        elif beta < 0.5:
            score -= 1

    # Concentration: stocks in many funds at high weight = systemic risk if user holds multiple funds
    if n_funds_holding >= 4 and max_holding_weight > 0.05:
        score += 1

    tiers = ["very_low", "low", "medium", "high", "very_high"]
    idx = max(0, min(len(tiers) - 1, score + 2))
    return tiers[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holdings", required=True)
    ap.add_argument("--market", required=True, help="market.json for beta/volatility")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    market = json.loads(Path(args.market).read_text(encoding="utf-8"))["stocks"]

    universe = holdings.get("unique_universe", [])
    funds = holdings.get("funds", [])

    # 1. Overlap matrix
    overlap_rows = []
    for u in universe:
        if u["n_funds_holding"] >= 2:
            overlap_rows.append({
                "ticker": u["ticker"],
                "name": u.get("name"),
                "n_funds_holding": u["n_funds_holding"],
                "held_by": u["held_by"],
                "weights_by_fund": u["weights_by_fund"],
                "max_weight": u["max_weight"],
                "avg_weight": u["avg_weight"],
            })
    overlap_rows.sort(key=lambda r: (-r["n_funds_holding"], -r["max_weight"]))

    # 2. Industry concentration per fund
    fund_industry_flags = []
    for fund in funds:
        ind_weights = defaultdict(float)
        for h in fund.get("holdings", []):
            tkr = h.get("ticker_normalized") or h["ticker"]
            mkt_rec = market.get(tkr) or market.get(h["ticker"])
            ind = (mkt_rec.get("industry") if mkt_rec else None) or "unknown"
            ind_weights[ind] += h.get("weight", 0)
        breaches = [(i, round(w, 4)) for i, w in ind_weights.items() if w > 0.30]
        breaches.sort(key=lambda kv: -kv[1])
        fund_industry_flags.append({
            "fund_id": fund.get("fund_id"),
            "fund_name": fund.get("fund_name"),
            "industry_weights": dict(sorted(ind_weights.items(), key=lambda kv: -kv[1])),
            "breaches_30pct": breaches,
            "is_breached": len(breaches) > 0,
        })

    # 3. Per-stock risk rating
    stock_risk = []
    for u in universe:
        tkr = u["ticker"]
        mkt = market.get(tkr, {})
        tier = risk_tier(
            volatility_proxy=mkt.get("past_6m_return"),
            beta=mkt.get("beta"),
            n_funds_holding=u["n_funds_holding"],
            max_holding_weight=u["max_weight"],
        )
        stock_risk.append({
            "ticker": tkr,
            "name": u.get("name"),
            "industry": mkt.get("industry"),
            "beta": mkt.get("beta"),
            "past_6m_return": mkt.get("past_6m_return"),
            "n_funds_holding": u["n_funds_holding"],
            "max_holding_weight": u["max_weight"],
            "risk_tier": tier,
        })

    # 4. Concentration map for strategy_weights step (per stock: what's the
    #    highest single-industry weight in any fund holding this stock?)
    concentration_map = {}
    for r in overlap_rows + [{"ticker": u["ticker"], "held_by": u["held_by"]} for u in universe]:
        tkr = r["ticker"]
        max_conc = 0.0
        for fid in r.get("held_by", []):
            for f in fund_industry_flags:
                if f["fund_id"] == fid:
                    if f["industry_weights"]:
                        max_conc = max(max_conc, max(f["industry_weights"].values()))
        concentration_map[tkr] = round(max_conc, 4)

    out = {
        "overlap": overlap_rows,
        "n_overlap_stocks": len(overlap_rows),
        "fund_industry_flags": fund_industry_flags,
        "stock_risk": stock_risk,
        "concentration_map": concentration_map,
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))

    # Also write the concentration map separately so strategy_weights.py can use it
    Path(args.out).parent.joinpath("concentration_map.json").write_text(
        json.dumps(concentration_map, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Risk report written to {args.out}")
    print(f"  {len(overlap_rows)} stocks held by 2+ funds")
    print(f"  {sum(1 for f in fund_industry_flags if f['is_breached'])}/{len(fund_industry_flags)} funds with industry > 30%")


if __name__ == "__main__":
    main()