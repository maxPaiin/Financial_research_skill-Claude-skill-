"""
Stage 3a: the ranking — up to 15 names, three display tiers.

v0.4 (B5, DEC-2): the ranking is an ORDERING OF KEYS, not a weighted sum.
No weight is written down anywhere, because none could be calibrated (the
backtest was removed in v0.2). Each eligible stock is ordered by

    (consensus band, -Q'', -c_share, ticker)

  band     majority < plural < single, from consensus.json (consensus_signal.py):
           what independent funds collectively hold at or above benchmark weight
  Q''      low-anchor confidence-shrunk quality, c*Q + (1-c)*Q_LOW (v0.3 A4)
  c_share  the consensus share itself, within a band and a quality tie
  ticker   last, so the same inputs always give the same order (I10)

so quality orders names inside each consensus band, and consensus decides which
band a name sits in. The v0.3 50/50 composite is retired; a copy lives only in
scripts/dev/legacy_v033.py, for side-by-side comparison.

Eligible: passed the quality screen, has a quality score, and has at least one
qualifying vote (n_votes >= 1). Names nobody votes for are not ranked; those a
majority of funds hold only at benchmark weight are reported as the
benchmark-anchored core instead (DEC-3).

Low-anchor shrinkage (v0.3 A4, unchanged): Q'' = c*Q + (1-c)*Q_LOW with
c = quality_confidence, the confidence of the stock's ROE points (v0.34 A5).
Q_LOW must stay > 0: Q_LOW = 0 degenerates to the rejected multiplicative form.
Q'' is NOT re-percentiled, so the penalty moves a stock's absolute position.

Tiers stay display slices of rank: A = 1-5, B = 6-10, C = 11-15. Fewer than five
eligible names sets warning "few_eligible"; there is no automatic fallback —
the user is offered a rerun with --vote-basis presence (SKILL.md).

This stage reads scores_per_stock.json, consensus.json and overlap.json (display
fields only). It reads no top-down or price input of any kind, which is what
lets those stages run after it (enforced by TestRankingReadsNoMacro).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

RANKING_METHOD = "v0.4-consensus-bands"
_TOP_N = 15
_TIER_BREAKS = [5, 10, 15]   # A: ≤5, B: ≤10, C: ≤15
_MIN_ELIGIBLE = 5
BAND_ORDER = {"majority": 0, "plural": 1, "single": 2}

# A4 (v0.3) low-anchor confidence shrinkage — canonical location.
# Q_LOW MUST stay > 0 (=0 degenerates to the rejected multiplicative form).
# Tunable *toward* 0 for more conservatism, never to 0.
_Q_LOW = 10.0
# Fallback confidence when a stock carries no quality_confidence. Treated as
# the yfinance baseline (0.5) so missing-confidence stocks are shrunk, not
# trusted at face value (premise 2: uncertainty is a quality defect).
_DEFAULT_CONFIDENCE = 0.5

_DISPLAY_FROM_SCORES = ("industry", "roe_5y_avg", "ev_ebitda", "debt_equity", "is_adr",
                        "data_confidence", "data_asof", "market_cap", "adv")
_DISPLAY_FROM_OVERLAP = ("n_funds_holding", "held_by", "avg_weight", "max_weight",
                         "sum_of_weights", "weights_by_fund")


def low_anchor_shrink(q: float, confidence: Optional[float]) -> float:
    """Q'' = c*Q + (1-c)*Q_LOW. Pulls low-confidence quality toward Q_LOW."""
    c = confidence if confidence is not None else _DEFAULT_CONFIDENCE
    c = max(0.0, min(1.0, float(c)))
    return round(c * q + (1.0 - c) * _Q_LOW, 2)


def tier(rank: int) -> str:
    if rank <= _TIER_BREAKS[0]:
        return "A"
    if rank <= _TIER_BREAKS[1]:
        return "B"
    return "C"


def sort_key(c: dict) -> tuple:
    """(band, -Q'', -c_share, ticker) — the whole ranking rule."""
    return (BAND_ORDER[c["band"]], -c["q_shrunk"], -c["c_share"], c["ticker"])


def rank(scores_data: dict, consensus: dict, overlap_data: dict) -> dict:
    """rankings.json content (spec §7.5)."""
    stocks = scores_data.get("stocks", {})
    by_ticker = {r["ticker"]: r for r in consensus.get("stocks", [])}
    overlap_by_ticker = {r["ticker"]: r for r in overlap_data.get("overlap", [])}

    candidates = []
    for ticker, s in stocks.items():
        q = s.get("fundamental_quality_score")
        con = by_ticker.get(ticker)
        if s.get("status") != "ok" or q is None or not con:
            continue
        if con.get("n_votes", 0) < 1 or con.get("band") not in BAND_ORDER:
            continue
        ov = overlap_by_ticker.get(ticker, {})
        candidates.append({
            "ticker": ticker,
            "name": ov.get("name"),
            "band": con["band"],
            "c_share": con["c_share"],
            "opinions": con.get("opinions"),
            "n_votes": con["n_votes"],
            "n_holders": con.get("n_holders"),
            "vote_basis_counts": con.get("vote_basis_counts"),
            "q_raw": q,
            "q_shrunk": low_anchor_shrink(q, s.get("quality_confidence")),
            "quality_confidence": s.get("quality_confidence"),
            "roe_years": s.get("roe_years"),
            "roe_source": s.get("roe_source"),
            **{k: s.get(k) for k in _DISPLAY_FROM_SCORES},
            **{k: ov.get(k) for k in _DISPLAY_FROM_OVERLAP},
        })

    candidates.sort(key=sort_key)
    ranked = candidates[:_TOP_N]
    ordered = []
    for i, c in enumerate(ranked, start=1):
        ordered.append({"rank": i, "tier": tier(i), **c})

    anchored = consensus.get("anchored_core") or []
    return {
        "ranking_method": RANKING_METHOD,
        "vote_basis": consensus.get("vote_basis"),
        "n_funds": consensus.get("n_funds"),
        "n_eff_run": consensus.get("n_eff_run"),
        "vote_floor": consensus.get("vote_floor"),
        "n_eligible": len(candidates),
        "n_ranked": len(ordered),
        "warning": "few_eligible" if len(candidates) < _MIN_ELIGIBLE else None,
        "anchored_core": anchored,
        # Display detail for the anchored-core section; nothing here is ranked.
        "anchored_core_detail": [{
            "ticker": t,
            "name": overlap_by_ticker.get(t, {}).get("name"),
            "n_holders": by_ticker.get(t, {}).get("n_holders"),
            "vote_basis_counts": by_ticker.get(t, {}).get("vote_basis_counts"),
            "screen_status": (stocks.get(t) or {}).get("status", "not screened in"),
            "industry": (stocks.get(t) or {}).get("industry"),
        } for t in anchored],
        "ranked": ordered,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", required=True, help="scores_per_stock.json from compute_scores")
    ap.add_argument("--consensus", required=True, help="consensus.json from consensus_signal")
    ap.add_argument("--overlap", required=True, help="overlap.json (display fields only)")
    ap.add_argument("--out", required=True, help="Output rankings.json")
    args = ap.parse_args()

    out = rank(
        json.loads(Path(args.scores).read_text(encoding="utf-8")),
        json.loads(Path(args.consensus).read_text(encoding="utf-8")),
        json.loads(Path(args.overlap).read_text(encoding="utf-8")),
    )
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))

    bands = {b: sum(1 for r in out["ranked"] if r["band"] == b) for b in BAND_ORDER}
    print(f"Ranked {out['n_ranked']} of {out['n_eligible']} eligible "
          f"({', '.join(f'{b} {n}' for b, n in bands.items())}) -> {args.out}")
    if out["anchored_core"]:
        print(f"Benchmark-anchored core (not ranked): {', '.join(out['anchored_core'])}")
    if out["warning"] == "few_eligible":
        print("WARNING few_eligible: fewer than 5 names have a qualifying vote. Tell the "
              "user; offer to rerun P3-P4 with --vote-basis presence.")


if __name__ == "__main__":
    main()
