"""
Stage 3: Compute per-stock scores using the formulas in
references/scoring_playbook.md.

Inputs:
  market.json — output of fetch_market_data.py
  macro.json  — output of fetch_macro_data.py

Output:
  scores_per_stock.json — per-stock industry/growth/quality_value/momentum scores.
"""

import sys
import json
import argparse
import statistics
from pathlib import Path
from collections import defaultdict


def percentile(value, distribution):
    """Return percentile rank of value within distribution (0..100). Skip Nones."""
    cleaned = [x for x in distribution if x is not None]
    if not cleaned or value is None:
        return None
    cleaned.sort()
    below = sum(1 for x in cleaned if x < value)
    return int(round(below / len(cleaned) * 100))


# ---------- Industry score ----------

def macro_score(industry, inflation, rate_change, fx_regime):
    score = 0
    if industry in {"commodity", "trading", "materials", "energy"}:
        if (inflation or 0) > 0.025:
            score += 1
    if industry in {"financial", "banks", "insurance"}:
        if (rate_change or 0) > 0:
            score += 1
    if industry in {"export", "auto", "semiconductors_jp"}:
        if fx_regime == "weak_jpy":
            score += 1
    return score   # 0..3


def industry_score(macro, trend, relative_strength):
    score = 0
    score += macro * 20
    if trend is not None and trend > 0:
        score += 30
    if relative_strength is not None and relative_strength > 0:
        score += 50
    else:
        score += 10
    return min(score, 100)


# ---------- Growth score ----------

def value_score(pe, industry_pe_dist):
    if pe is None:
        return None
    p = percentile(pe, industry_pe_dist)
    return None if p is None else 100 - p


def revision_pct(eps_t, eps_t_minus_1):
    if eps_t is None or eps_t_minus_1 is None or eps_t_minus_1 == 0:
        return None
    return (eps_t - eps_t_minus_1) / abs(eps_t_minus_1)


def revision_score(rev):
    if rev is None:
        return 50   # neutral when missing
    if rev > 0.10:
        return 100
    elif rev > 0.05:
        return 85
    elif rev > 0:
        return 70
    elif rev > -0.05:
        return 40
    else:
        return 20


# ---------- Quality & Value score ----------

def ev_score(ev_ebitda, industry_dist):
    if ev_ebitda is None or ev_ebitda <= 0:
        return None
    p = percentile(ev_ebitda, [x for x in industry_dist if x and x > 0])
    return None if p is None else 100 - p


def roe_score(roe, industry_dist):
    if roe is None:
        return None
    return percentile(roe, industry_dist)


# ---------- Momentum (optional) ----------

def momentum_score(ret_6m, universe_dist):
    if ret_6m is None:
        return None
    return percentile(ret_6m, universe_dist)


# ---------- Composite ----------

def safe_blend(*pairs):
    """Weighted average, dropping None components and renormalizing weights."""
    total_w = sum(w for v, w in pairs if v is not None)
    if total_w == 0:
        return None
    return sum(v * w for v, w in pairs if v is not None) / total_w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", required=True)
    ap.add_argument("--macro", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    market = json.loads(Path(args.market).read_text(encoding="utf-8"))
    macro = json.loads(Path(args.macro).read_text(encoding="utf-8"))

    stocks = market["stocks"]

    # Build industry-level distributions for percentile calcs
    by_industry_pe = defaultdict(list)
    by_industry_ev = defaultdict(list)
    by_industry_roe = defaultdict(list)
    universe_6m_returns = []

    for s in stocks.values():
        if s.get("status") != "ok":
            continue
        ind = s.get("industry") or "other"
        if s.get("pe") is not None and s["pe"] > 0:
            by_industry_pe[ind].append(s["pe"])
        if s.get("ev_ebitda") is not None and s["ev_ebitda"] > 0:
            by_industry_ev[ind].append(s["ev_ebitda"])
        if s.get("roe") is not None:
            by_industry_roe[ind].append(s["roe"])
        if s.get("past_6m_return") is not None:
            universe_6m_returns.append(s["past_6m_return"])

    inflation = macro.get("inflation_yoy")
    rate_change = macro.get("interest_rate_yoy_change")
    fx_regime = macro.get("fx_regime", "normal")
    index_return = market.get("index_return_12m")

    out = {"as_of": macro.get("as_of"), "stocks": {}}

    for tkr, s in stocks.items():
        rec = {"ticker": tkr, "industry": s.get("industry")}

        if s.get("status") != "ok":
            rec["status"] = "unscored"
            rec["reason"] = s.get("reason", "data_missing")
            out["stocks"][tkr] = rec
            continue

        ind = s.get("industry") or "other"
        # Industry score
        m = macro_score(ind, inflation, rate_change, fx_regime)
        etf_ret = s.get("industry_etf_return_12m")
        rs = (etf_ret - index_return) if (etf_ret is not None and index_return is not None) else None
        ind_sc = industry_score(m, etf_ret, rs)

        # Growth score
        v_sc = value_score(s.get("pe"), by_industry_pe.get(ind, []))
        rev = revision_pct(s.get("eps_estimate_t"), s.get("eps_estimate_t_minus_1"))
        r_sc = revision_score(rev)
        grw_sc = safe_blend((v_sc, 0.5), (r_sc, 0.5))

        # Quality & Value
        ev_sc = ev_score(s.get("ev_ebitda"), by_industry_ev.get(ind, []))
        roe_sc = roe_score(s.get("roe"), by_industry_roe.get(ind, []))
        qv_sc = safe_blend((ev_sc, 0.5), (roe_sc, 0.5))

        # Momentum
        mom_sc = momentum_score(s.get("past_6m_return"), universe_6m_returns)

        # Neutral total (pre-strategy)
        total = safe_blend((ind_sc, 0.30), (grw_sc, 0.30), (qv_sc, 0.40))

        rec.update({
            "status": "ok",
            "industry_score": ind_sc,
            "growth_score": grw_sc,
            "quality_value_score": qv_sc,
            "momentum_score": mom_sc,
            "neutral_total_score": total,
            # Raw inputs preserved for audit
            "raw": {
                "pe": s.get("pe"),
                "pbr": s.get("pbr"),
                "ev_ebitda": s.get("ev_ebitda"),
                "roe": s.get("roe"),
                "eps_revision": rev,
                "industry_etf_return_12m": etf_ret,
                "index_return_12m": index_return,
                "relative_strength": rs,
                "past_6m_return": s.get("past_6m_return"),
                "macro_tilt": m,
            },
        })
        out["stocks"][tkr] = rec

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))

    n_ok = sum(1 for r in out["stocks"].values() if r.get("status") == "ok")
    n_unsc = len(out["stocks"]) - n_ok
    print(f"Scored {n_ok} stocks ok, {n_unsc} unscored.")


if __name__ == "__main__":
    main()