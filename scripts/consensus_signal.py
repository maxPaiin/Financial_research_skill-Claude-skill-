"""
Stage 2f-ii (v0.4 B4): consensus signal v2.

C measures what independent institutions collectively hold at or above their
benchmark weight. It rises monotonically with agreement, it depends on no
LLM-inferred label, and it does not penalise position size. (v0.33's C fell as
more funds agreed and moved with label order and price drift — F1, F3, F6.)

Definitions (references/consensus_signal.md, spec Appendix A):

  Similarity    S_fg = cos(x_f, x_g) in [0, 1], S_ff = 1, where x_f is fund f's
                vector of kept US weights.
  Fund weights  u_f = 1 / sum_g S_fg;  N_eff_run = sum_f u_f;  w_f = u_f / N_eff_run.
                Funds that hold the same names share one opinion's weight; a
                fund unlike the others keeps a whole one. 1 <= N_eff_run <= n.
  Vote          for fund f and stock i with disclosed weight w, common floor tau
                and single-issuer cap L = 10%:
                  w < tau                                     -> no vote (below_floor)
                  basis active and i in f's proxy top-10 at b:
                      w >= min(b, L)                          -> vote (active)
                      otherwise                               -> no vote (anchored)
                  otherwise                                   -> vote (presence)
  Consensus     c_share_i = sum_f w_f v_fi;  opinions_i = c_share_i * N_eff_run
  Bands         majority: c_share >= 1/2 and n_votes >= 2;  plural: n_votes >= 2;
                single: n_votes = 1;  none: n_votes = 0 (not ranked)
  Anchored core n_votes = 0, n_holders >= ceil(N / 2), at least one anchored basis

Every threshold is definitional (a majority is half of the independent opinion,
and needs two voting funds so one dissimilar fund cannot be a majority alone)
or regulatory (L = 10%, the single-issuer ceiling of SFC UT Code 7.1 and UCITS
Art. 52(2)). Nothing here is fitted.

This script reads holdings.json and, optionally, benchmark_weights.json — and
nothing else: no fund labels inferred at Stage 1a, no macro or sector files, no
reader-facing notice, no exit-liquidity data (I9; enforced by tests).

Usage:
  consensus_signal.py --holdings holdings.json [--benchmark-weights benchmark_weights.json]
                      [--vote-basis active|presence] [--vote-floor common|none]
                      --out consensus.json

--vote-basis presence reproduces holding-based consensus (DEC-1's alternative);
--vote-floor none disables the common floor — both for sensitivity runs only.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_holdings import (  # noqa: E402
    common_vote_floor, cosine_similarity, fund_order_key, is_accepted, us_sleeve_vector,
)

VERSION = "0.4"
SINGLE_ISSUER_CAP = 0.10        # L: SFC UT Code 7.1 / UCITS Art. 52(2)
MAJORITY_SHARE = 0.5            # half of the independent opinion
MIN_VOTERS_FOR_MAJORITY = 2     # one fund alone is never a majority
BANDS = ("majority", "plural", "single", "none")
BAND_ORDER = {b: i for i, b in enumerate(BANDS)}
BASES = ("active", "presence", "anchored", "below_floor")
_EPS = 1e-12


# --- Independence weights ----------------------------------------------------

def similarity(vectors: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Full symmetric matrix of cosines; S_ff = 1 by definition."""
    fids = list(vectors)
    s: dict[str, dict[str, float]] = {f: {} for f in fids}
    for i, f in enumerate(fids):
        s[f][f] = 1.0
        for g in fids[i + 1:]:
            c = cosine_similarity(vectors[f], vectors[g])
            s[f][g] = s[g][f] = c
    return s


def independence(s: dict[str, dict[str, float]],
                 fids: Optional[list[str]] = None) -> tuple[dict[str, float], float, dict[str, float]]:
    """(u, N_eff_run, omega) over `fids` (default: all funds in `s`)."""
    fids = list(s) if fids is None else list(fids)
    u = {f: 1.0 / sum(s[f][g] for g in fids) for f in fids}
    n_eff = sum(u.values())
    omega = {f: (u[f] / n_eff if n_eff else 0.0) for f in fids}
    return u, n_eff, omega


def marginal_contributions(s: dict[str, dict[str, float]]) -> dict[str, float]:
    """N_eff_run - N_eff_run(F without f): how much independent opinion f adds."""
    fids = list(s)
    _, n_all, _ = independence(s, fids)
    out = {}
    for f in fids:
        rest = [g for g in fids if g != f]
        out[f] = n_all - (independence(s, rest)[1] if rest else 0.0)
    return out


# --- Votes and bands ------------------------------------------------------------

def vote(weight: float, tau: Optional[float], basis: str,
         benchmark_weight: Optional[float]) -> tuple[int, str]:
    """(v_fi, basis) for one held position — spec Appendix A, rule by rule."""
    if tau is not None and weight < tau - _EPS:
        return 0, "below_floor"
    if basis == "active" and benchmark_weight is not None:
        if weight >= min(benchmark_weight, SINGLE_ISSUER_CAP) - _EPS:
            return 1, "active"
        return 0, "anchored"
    return 1, "presence"


def band(c_share: float, n_votes: int) -> str:
    if n_votes >= MIN_VOTERS_FOR_MAJORITY and c_share >= MAJORITY_SHARE - _EPS:
        return "majority"
    if n_votes >= 2:
        return "plural"
    if n_votes == 1:
        return "single"
    return "none"


# --- The run ------------------------------------------------------------------

def compute(holdings: dict, benchmark_weights: Optional[dict] = None,
            vote_basis: str = "active", vote_floor: str = "common") -> dict:
    """consensus.json content (spec §7.3)."""
    if vote_basis not in ("active", "presence"):
        raise ValueError(f"vote_basis must be active or presence, not {vote_basis!r}")
    if vote_floor not in ("common", "none"):
        raise ValueError(f"vote_floor must be common or none, not {vote_floor!r}")

    funds = sorted((f for f in holdings.get("funds", []) if is_accepted(f)),
                   key=lambda f: fund_order_key(f["fund_id"]))
    fids = [f["fund_id"] for f in funds]
    vectors = {f["fund_id"]: us_sleeve_vector(f) for f in funds}
    bench = benchmark_weights or {}

    if vote_floor == "common":
        tau, tau_set_by = common_vote_floor(funds)
    else:
        tau, tau_set_by = None, []

    s = similarity(vectors) if fids else {}
    u, n_eff, omega = independence(s) if fids else ({}, 0.0, {})
    marginal = marginal_contributions(s) if fids else {}

    coverage = {b: 0 for b in BASES}
    per_stock: dict[str, dict] = {}
    for fid in fids:
        record = bench.get(fid) or {}
        top10 = (record.get("top10") or {}) if record.get("proxy") else {}
        for ticker, weight in sorted(vectors[fid].items()):
            v, basis = vote(weight, tau, vote_basis, top10.get(ticker))
            coverage[basis] += 1
            entry = per_stock.setdefault(ticker, {"ticker": ticker, "votes": []})
            entry["votes"].append({
                "fund_id": fid, "weight": round(weight, 6),
                "benchmark_weight": top10.get(ticker), "basis": basis, "vote": v,
            })

    n_funds = len(fids)
    stocks = []
    for ticker, entry in per_stock.items():
        votes = entry["votes"]
        n_votes = sum(v["vote"] for v in votes)
        c_share = sum(omega[v["fund_id"]] * v["vote"] for v in votes)
        counts = {b: 0 for b in BASES}
        for v in votes:
            counts[v["basis"]] += 1
        stocks.append({
            "ticker": ticker,
            "n_holders": len(votes),
            "n_votes": n_votes,
            "c_share": round(c_share, 6),
            "opinions": round(c_share * n_eff, 6),
            "band": band(c_share, n_votes),
            "vote_basis_counts": counts,
            "votes": votes,
        })
    stocks.sort(key=lambda r: (BAND_ORDER[r["band"]], -r["c_share"], r["ticker"]))

    anchored_core = sorted(
        r["ticker"] for r in stocks
        if r["n_votes"] == 0 and r["n_holders"] >= math.ceil(n_funds / 2)
        and r["vote_basis_counts"]["anchored"] >= 1
    )

    return {
        "version": VERSION,
        "vote_basis": vote_basis,
        "n_funds": n_funds,
        "n_eff_run": round(n_eff, 6),
        "vote_floor": tau,
        "vote_floor_set_by": tau_set_by,
        "single_issuer_cap": SINGLE_ISSUER_CAP,
        "funds": [{
            "fund_id": fid,
            "u": round(u[fid], 6),
            "omega": round(omega[fid], 6),
            "marginal_contribution": round(marginal[fid], 6),
            "benchmark_proxy": (bench.get(fid) or {}).get("proxy"),
            "proxy_quality": (bench.get(fid) or {}).get("proxy_quality"),
        } for fid in fids],
        "similarity": {f: {g: round(s[f][g], 6) for g in fids[i + 1:]}
                       for i, f in enumerate(fids[:-1])},
        "vote_basis_coverage": coverage,
        "stocks": stocks,
        "anchored_core": anchored_core,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 2f-ii: consensus signal v2")
    ap.add_argument("--holdings", required=True, help="holdings.json after Stage 1b-d")
    ap.add_argument("--benchmark-weights", help="benchmark_weights.json (Stage 2f-i). "
                                                "Absent -> every vote is a presence vote.")
    ap.add_argument("--vote-basis", choices=("active", "presence"), default="active",
                    help="active (default, DEC-1) or presence (holding-based, sensitivity)")
    ap.add_argument("--vote-floor", choices=("common", "none"), default="common",
                    help="common (default) or none (sensitivity runs only)")
    ap.add_argument("--out", required=True, help="Output consensus.json")
    args = ap.parse_args()

    holdings = json.loads(Path(args.holdings).read_text(encoding="utf-8"))
    bench = None
    if args.benchmark_weights and Path(args.benchmark_weights).exists():
        bench = json.loads(Path(args.benchmark_weights).read_text(encoding="utf-8"))
    out = compute(holdings, bench, args.vote_basis, args.vote_floor)

    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    bands = {b: sum(1 for r in out["stocks"] if r["band"] == b) for b in BANDS}
    tau = out["vote_floor"]
    print(f"Consensus ({out['vote_basis']} votes) -> {path}")
    print(f"  funds {out['n_funds']} | independent opinions N_eff {out['n_eff_run']:.2f} | "
          f"common floor {f'{tau:.2%}' if tau is not None else 'off'}"
          + (f" (set by {', '.join(out['vote_floor_set_by'])})" if out['vote_floor_set_by'] else ""))
    print("  bands: " + ", ".join(f"{b} {n}" for b, n in bands.items()))
    print("  vote bases: " + ", ".join(f"{b} {n}" for b, n in out["vote_basis_coverage"].items()))
    if out["anchored_core"]:
        print(f"  benchmark-anchored core: {', '.join(out['anchored_core'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
