"""
Stage 3a-bis: coherence audit — the v0.31 overlay (Part E).

WHAT THIS IS. A bolt-on that asks one question per ranked stock: do the macro
factors (E2.1), the sector operating logic (E2.2), and the price action (E2.3)
tell the same story? Where they contradict each other, the stock's picture is
incoherent; incoherence is uncertainty; and in this tool uncertainty is a
quality defect (v0.3 §0 premise 2). The stock is shown one tier lower with the
contradiction named — it does NOT move in the ranking.

v0.4 (B7, DEC-4): a fourth, optional check — EXIT LIQUIDITY. Crowding left the
rank; it returns here as a risk. When the funds' USD-reporting holders would
need 10 or more trading days of average volume to sell a position
(crowding_signals.json `is_exit_crowded`), the verdict is `risk`, and a risk
demotes exactly like a contradiction: one tier, never more, rank untouched.

v0.4 (D3): a fifth, optional check — CONSENSUS FLOW. When an earlier factsheet
snapshot was supplied (consensus_flow.json), a stock in the MAJORITY band that
the funds are UNWINDING — at least two trimmed it beyond price drift, net of
their independence weights — is a contradiction: the consensus the rank rests
on is being sold. Everything else is coherent or insufficient data.

WHAT IT MAY NOT DO (the invariants that make it non-destructive):
  * `rankings.json` is READ-ONLY. Composite scores, Q'', C and rank order are
    written by 3a and never rewritten here. This script's only output is the
    `coherence.json` side-car.
  * DEMOTION-ONLY. There is no configuration under which a stock moves up a
    tier. That is what makes the overlay reversible: delete this stage and the
    pipeline still runs and produces the v0.3 report, unchanged.
  * At most ONE tier of demotion per stock (A->B, B->C, C is the floor), no
    matter how many pairs contradict. Multiple contradictions are all named in
    the commentary but do not compound — a bounded overlay cannot de-facto
    reorder the report.
  * MISSING DATA IS NOT A VERDICT. An unmapped sector ETF or a sparse macro
    read yields "insufficient data" with the tier unchanged: it must not
    masquerade as coherence, and it must not be punished as a contradiction
    (which would let data gaps drive tiering).

WHY NOT A THIRD SCORING AXIS. `0.4·Q + 0.4·C + 0.2·Macro` was rejected: the
weight cannot be calibrated (the backtest was removed in v0.2, so there is no
mechanism to validate 15% vs 25% — writing a number down would be exactly the
false precision the honesty framing exists to prevent), and it would break the
locked 50/50 split.

Inputs:
  --rankings       rankings.json (READ-ONLY)
  --macro          macro_factors.json   — structured E2.1 fields written by
                   Claude at M1 (extracted from the existing M1 corpus; no new
                   sources are fetched for this)
  --sector-logic   sector_logic.json    — E2.2 three universal questions,
                   instantiated per industry bucket by Claude
  --etf            etf_relative_strength.json from etf_relative_strength.py
  --crowding       crowding_signals.json (v0.4 B7) — days-to-liquidate per
                   ticker; absent -> the exit-liquidity check does not run and
                   every record is exactly what it was without it
  --flow           consensus_flow.json (v0.4 D3) — absent -> the consensus-flow
                   check does not run, likewise
  --out            coherence.json

Every input except --rankings is optional; each absent input degrades the
affected pairs to "insufficient data", never to a verdict.

Output schema — coherence.json:
{
  "n_records": 15, "n_demoted": 3, "n_insufficient": 2,
  "records": [
    {"ticker": "AAPL", "rank": 1, "industry": "technology",
     "base_tier": "A", "tier": "B", "tier_delta": -1,
     "factors": {"macro": {...}, "sector_logic": {...}, "etf": {...}},
     "verdicts": [{"pair": "macro_vs_sector", "verdict": "contradiction",
                   "statement": "..."}, ...,
                  {"pair": "exit_liquidity", "verdict": "risk", "statement": "..."},
                  {"pair": "consensus_flow", "verdict": "contradiction", "statement": "..."}],
     "contradictions": ["..."],
     "risks": ["..."],
     "divergence_flag": {"divergence": "negative", "explanation_required": true},
     "insufficient_data": [...],
     "commentary": "..."}
  ]
}
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Optional

# --- Controlled vocabularies (canonical; mirrored in references/coherence_overlay.md)

POLICY_RATE_DIRECTIONS = {"tightening", "on_hold", "easing"}
INFLATION_TRENDS = {"rising", "stable", "falling"}
CAPITAL_SENSITIVITY = {"high", "medium", "low"}

# Sector-logic sub-answer directions (E2.2 — the three universal questions).
_INPUT_DIRECTIONS = {"easing": 1, "neutral": 0, "tightening": -1}
_PRICING_DIRECTIONS = {"expanding": 1, "neutral": 0, "compressing": -1}
_ROC_DIRECTIONS = {"improving": 1, "neutral": 0, "deteriorating": -1}

# Verdict vocabulary.
COHERENT = "coherent"
CONTRADICTION = "contradiction"
RISK = "risk"                    # v0.4 B7: exit liquidity
INSUFFICIENT = "insufficient_data"
NOT_APPLICABLE = "not_applicable"

_TIER_ORDER = ["A", "B", "C"]
_MAX_DEMOTION = 1   # E3.2 cap — one tier per stock, never more.


# --- E2.1 macro ------------------------------------------------------------

def macro_stance(macro: Optional[dict]) -> tuple[str, list[str]]:
    """Collapse the structured M1 fields into one directional stance.

    Returns (stance, notes). stance ∈ {tightening, easing, neutral,
    insufficient_data}. On-hold policy with rising inflation reads as
    tightening: the real-rate path is the transmission channel, not the
    headline decision.
    """
    if not isinstance(macro, dict):
        return INSUFFICIENT, ["no macro_factors.json supplied"]

    rate = (macro.get("policy_rate_direction") or "").strip().lower()
    infl = (macro.get("inflation_trend") or "").strip().lower()

    notes: list[str] = []
    if rate not in POLICY_RATE_DIRECTIONS:
        notes.append("policy_rate_direction missing or outside the vocabulary")
    if infl not in INFLATION_TRENDS:
        notes.append("inflation_trend missing or outside the vocabulary")
    if rate not in POLICY_RATE_DIRECTIONS and infl not in INFLATION_TRENDS:
        return INSUFFICIENT, notes

    if rate == "tightening" or (rate == "on_hold" and infl == "rising"):
        return "tightening", notes
    if rate == "easing" and infl != "rising":
        return "easing", notes
    return "neutral", notes


# --- E2.2 sector logic -----------------------------------------------------

def logic_direction(sector: Optional[dict]) -> tuple[str, list[str]]:
    """Net direction of a sector's operating logic from the three answers.

    The three universal questions replace the physical supply-chain triad
    (upstream resources / trade spread / investment return), which produces
    confident nonsense on software, financial and consumer names:
      1. input side      — what constrains the inputs?
      2. output side     — how much pricing power is there?
      3. capital         — what is the return on capital deployed?
    Each carries a direction; the net of the three is the sector's logic
    direction. Requires at least two answered directions to return a verdict.
    """
    if not isinstance(sector, dict):
        return INSUFFICIENT, ["no sector logic recorded for this industry"]

    def _dir(key: str, table: dict[str, int]) -> Optional[int]:
        block = sector.get(key)
        raw = (block.get("direction") if isinstance(block, dict) else block) or ""
        return table.get(str(raw).strip().lower())

    parts = {
        "input_constraint": _dir("input_constraint", _INPUT_DIRECTIONS),
        "pricing_power": _dir("pricing_power", _PRICING_DIRECTIONS),
        "return_on_capital": _dir("return_on_capital", _ROC_DIRECTIONS),
    }
    answered = {k: v for k, v in parts.items() if v is not None}
    notes = [f"{k} not answered" for k, v in parts.items() if v is None]

    if len(answered) < 2:
        return INSUFFICIENT, notes or ["fewer than two of the three questions answered"]

    score = sum(answered.values())
    if score >= 2:
        return "expansionary", notes
    if score <= -2:
        return "contractionary", notes
    return "neutral", notes


def capital_sensitivity(sector: Optional[dict]) -> Optional[str]:
    if not isinstance(sector, dict):
        return None
    raw = str(sector.get("capital_sensitivity") or "").strip().lower()
    return raw if raw in CAPITAL_SENSITIVITY else None


# --- E3.1 pairwise coherence ----------------------------------------------

def verdict_macro_vs_sector(
    stance: str,
    direction: str,
    sensitivity: Optional[str],
    industry: Optional[str],
) -> tuple[str, str]:
    """Does the macro read point the same way as the sector's operating logic?"""
    if stance == INSUFFICIENT or direction == INSUFFICIENT:
        return INSUFFICIENT, "Macro stance or sector logic unavailable; pair not judged."
    if stance == "neutral" or direction == "neutral":
        return COHERENT, "Macro stance and sector logic are not in opposition."
    if sensitivity == "low":
        return NOT_APPLICABLE, (
            f"{industry or 'this sector'} is rated low-sensitivity to the policy-rate "
            "path, so the macro read carries no directional expectation for it."
        )

    if stance == "tightening" and direction == "expansionary":
        return CONTRADICTION, (
            f"The central-bank read is tightening, but the {industry or 'sector'} "
            "operating logic is expansionary and depends on capital that is getting "
            "more expensive."
        )
    if stance == "easing" and direction == "contractionary":
        return CONTRADICTION, (
            f"The central-bank read is easing, yet the {industry or 'sector'} "
            "operating logic is contracting — the macro tailwind is not reaching the "
            "sector's inputs, pricing or returns."
        )
    return COHERENT, "Macro stance and sector logic point the same way."


def verdict_sector_vs_etf(
    direction: str,
    rs_state: str,
    industry: Optional[str],
) -> tuple[str, str]:
    """Is the sector's price behaviour consistent with the logic claimed for it?"""
    if direction == INSUFFICIENT or rs_state in (INSUFFICIENT, "", None):
        return INSUFFICIENT, "Sector logic or sector-ETF relative strength unavailable."
    if direction == "neutral" or rs_state == "inline":
        return COHERENT, "Sector logic and sector-ETF relative strength are not in opposition."

    if direction == "expansionary" and rs_state == "lagging":
        return CONTRADICTION, (
            f"The {industry or 'sector'} operating logic is expansionary, but its "
            "sector ETF is lagging SPY across the fixed 3M/6M/12M windows."
        )
    if direction == "contractionary" and rs_state == "outperforming":
        return CONTRADICTION, (
            f"The {industry or 'sector'} operating logic is contracting, yet its "
            "sector ETF is outperforming SPY across the fixed 3M/6M/12M windows."
        )
    return COHERENT, "Sector logic and sector-ETF relative strength agree."


def verdict_macro_vs_etf(
    stance: str,
    rs_state: str,
    sensitivity: Optional[str],
    industry: Optional[str],
) -> tuple[str, str]:
    """Is the sector trading consistently with the central-bank-derived narrative?

    Only capital-sensitive sectors carry a directional expectation from the
    policy path; for the rest the pair is not applicable rather than coherent,
    so the record does not imply agreement that was never tested.
    """
    if stance == INSUFFICIENT or rs_state in (INSUFFICIENT, "", None):
        return INSUFFICIENT, "Macro stance or sector-ETF relative strength unavailable."
    if sensitivity is None:
        return INSUFFICIENT, "Sector capital-sensitivity not recorded; pair not judged."
    if stance == "neutral" or sensitivity == "low" or rs_state == "inline":
        return NOT_APPLICABLE, (
            "No directional expectation links this macro read to this sector's "
            "relative strength."
        )

    if stance == "tightening" and rs_state == "outperforming":
        return CONTRADICTION, (
            f"Policy is tightening while the capital-sensitive {industry or 'sector'} "
            "ETF outperforms SPY — the sector is priced against the central-bank read."
        )
    if stance == "easing" and rs_state == "lagging":
        return CONTRADICTION, (
            f"Policy is easing while the capital-sensitive {industry or 'sector'} ETF "
            "lags SPY — the sector is priced against the central-bank read."
        )
    return COHERENT, "Sector relative strength is consistent with the central-bank read."


# --- v0.4 B7: exit liquidity -------------------------------------------------

def verdict_exit_liquidity(signal: Optional[dict]) -> tuple[str, str]:
    """risk when the USD-reporting holders would need >= 10 days to exit."""
    dtl = (signal or {}).get("days_to_liquidate")
    if not isinstance(dtl, (int, float)):
        return INSUFFICIENT, (
            "Exit liquidity: no days-to-liquidate figure — no holder reports AUM in "
            "USD, or no average daily volume.")
    n_usd = (signal or {}).get("n_usd_aum_holders")
    n_all = (signal or {}).get("n_holders")
    who = (f"the {n_usd} of {n_all} holders that report AUM in USD" if n_usd and n_all
           else "the holders that report AUM in USD")
    if signal.get("is_exit_crowded"):
        return RISK, (
            f"Exit liquidity: {who} would need {dtl:.1f} trading days of average volume "
            "to sell their positions together — at or above the 10-day line (an "
            "uncalibrated threshold). Holders reporting in other currencies are not "
            "counted.")
    return COHERENT, (
        f"Exit liquidity: {who} would need {dtl:.1f} trading days to sell together — "
        "below the 10-day line.")


# --- v0.4 D3: consensus flow --------------------------------------------------

def verdict_consensus_flow(band: Optional[str], flow: Optional[dict]) -> tuple[str, str]:
    """contradiction when a majority-consensus name is being unwound."""
    state = (flow or {}).get("state")
    if state in (None, "insufficient"):
        return INSUFFICIENT, (
            "Consensus flow: fewer than two funds disclose this stock in both factsheet "
            "snapshots — no flow reading.")
    n, added, trimmed = flow.get("n_comparable"), flow.get("n_added"), flow.get("n_trimmed")
    counts = f"{added} added, {trimmed} trimmed beyond price drift, of {n} comparable funds"
    if band == "majority" and state == "unwinding":
        return CONTRADICTION, (
            f"Consensus flow: a majority consensus that the funds are unwinding ({counts}) — "
            "the agreement the rank rests on is being sold.")
    return COHERENT, f"Consensus flow: {state} ({counts})."


# --- E3.2 adjustment -------------------------------------------------------

def demote(base_tier: str, delta: int) -> str:
    """Apply a (non-positive) tier delta. C is the floor; promotion impossible.

    A positive delta is clamped to 0 rather than honoured — the demotion-only
    guarantee is enforced here rather than trusted to callers.
    """
    tier = base_tier if base_tier in _TIER_ORDER else "C"
    steps = min(0, int(delta))                      # never promote
    steps = max(-_MAX_DEMOTION, steps)              # never drop more than one tier
    idx = min(len(_TIER_ORDER) - 1, _TIER_ORDER.index(tier) - steps)
    return _TIER_ORDER[idx]


def tier_from_rank(rank: int) -> str:
    if rank <= 5:
        return "A"
    if rank <= 10:
        return "B"
    return "C"


def audit_stock(
    row: dict,
    macro: Optional[dict],
    sector_logic: dict,
    etf_data: dict,
    crowding: Optional[dict] = None,
    flow: Optional[dict] = None,
) -> dict:
    """Produce one coherence record for one ranked stock. Pure function.

    `crowding` maps ticker -> crowding_signals.json row; None means the
    exit-liquidity check did not run (the record then carries no such verdict).
    `flow` maps ticker -> consensus_flow.json stock row, with the same rule.
    """
    ticker = row.get("ticker")
    rank = int(row.get("rank") or 0)
    industry = row.get("industry")
    base_tier = row.get("tier") or tier_from_rank(rank)

    stance, macro_notes = macro_stance(macro)
    sector = (sector_logic or {}).get("industries", {}).get(industry or "")
    direction, logic_notes = logic_direction(sector)
    sensitivity = capital_sensitivity(sector)

    sector_rs = (etf_data or {}).get("sectors", {}).get(industry or "") or {}
    stock_rs = (etf_data or {}).get("stocks", {}).get(ticker or "") or {}
    rs_state = sector_rs.get("rs_state") or INSUFFICIENT

    pairs = [
        ("macro_vs_sector", verdict_macro_vs_sector(stance, direction, sensitivity, industry)),
        ("sector_vs_etf", verdict_sector_vs_etf(direction, rs_state, industry)),
        ("macro_vs_etf", verdict_macro_vs_etf(stance, rs_state, sensitivity, industry)),
    ]
    if crowding is not None:
        pairs.append(("exit_liquidity", verdict_exit_liquidity(crowding.get(ticker or ""))))
    if flow is not None:
        pairs.append(("consensus_flow",
                      verdict_consensus_flow(row.get("band"), flow.get(ticker or ""))))
    verdicts = [
        {"pair": name, "verdict": verdict, "statement": statement}
        for name, (verdict, statement) in pairs
    ]

    contradictions = [v["statement"] for v in verdicts if v["verdict"] == CONTRADICTION]
    risks = [v["statement"] for v in verdicts if v["verdict"] == RISK]

    insufficient: list[str] = []
    if stance == INSUFFICIENT:
        insufficient += [f"macro: {n}" for n in (macro_notes or ["unavailable"])]
    if direction == INSUFFICIENT:
        insufficient += [f"sector logic ({industry}): {n}" for n in (logic_notes or ["unavailable"])]
    if rs_state == INSUFFICIENT:
        insufficient.append(
            f"ETF relative strength: {sector_rs.get('note') or 'unavailable'}"
        )

    # E3.2: one tier down if ANY pair contradicts or the exit-liquidity check
    # finds a risk (B7); capped at one regardless of how many do. Insufficient
    # data never moves the tier in either direction — and a missing liquidity
    # figure is reported in its own verdict, not as a gap in the three readings.
    tier_delta = -1 if (contradictions or risks) else 0
    tier = demote(base_tier, tier_delta)

    # E2.3: divergence is a flag plus a REQUIRED explanation, never a mechanical
    # penalty — a stock diverging from its sector may be exactly where the alpha
    # is. It does not feed tier_delta.
    divergence = stock_rs.get("divergence")
    divergence_flag = None
    if divergence in ("positive", "negative"):
        divergence_flag = {
            "divergence": divergence,
            "excess_mean_vs_sector_etf": stock_rs.get("excess_mean"),
            "excess_vs_etf": stock_rs.get("excess_vs_etf"),
            "etf": stock_rs.get("etf"),
            "explanation_required": True,
        }

    return {
        "ticker": ticker,
        "rank": rank,
        "industry": industry,
        "base_tier": base_tier,
        "tier": tier,
        "tier_delta": tier_delta,
        "factors": {
            "macro": {
                "stance": stance,
                "policy_rate_direction": (macro or {}).get("policy_rate_direction"),
                "inflation_trend": (macro or {}).get("inflation_trend"),
                "sources": (macro or {}).get("sources"),
                "notes": macro_notes,
            },
            "sector_logic": {
                "industry": industry,
                "logic_direction": direction,
                "capital_sensitivity": sensitivity,
                "answers": sector,
                "notes": logic_notes,
            },
            "etf": {
                "sector": sector_rs or None,
                "stock": stock_rs or None,
            },
        },
        "verdicts": verdicts,
        "contradictions": contradictions,
        **({"risks": risks} if crowding is not None else {}),
        "divergence_flag": divergence_flag,
        "insufficient_data": insufficient,
        "commentary": _commentary(contradictions + risks, insufficient, divergence_flag,
                                  tier, base_tier),
    }


def _commentary(
    contradictions: list[str],
    insufficient: list[str],
    divergence_flag: Optional[dict],
    tier: str,
    base_tier: str,
) -> str:
    """The plain-language line the rationale card carries for this stock.

    No "Coherence:" prefix — the card template supplies the label, and 3b reads
    it from the `commentary` key.
    """
    parts: list[str] = []
    if contradictions:
        parts.append(
            f"demoted {base_tier}->{tier} (rank unchanged). " + " ".join(contradictions)
        )
    elif insufficient:
        parts.append(
            "insufficient data to judge — tier unchanged. "
            + "; ".join(insufficient) + "."
        )
    else:
        parts.append("macro read, sector logic and sector-relative price action agree.")

    if divergence_flag:
        parts.append(
            f"Diverges {divergence_flag['divergence']}ly from its sector ETF "
            f"({divergence_flag.get('etf')}) over the fixed windows — this requires a "
            "stock-specific explanation and is not itself treated as a defect."
        )
    return " ".join(parts)


def audit(
    rankings: dict,
    macro: Optional[dict],
    sector_logic: Optional[dict],
    etf_data: Optional[dict],
    crowding: Optional[dict] = None,
    flow: Optional[dict] = None,
) -> dict:
    by_ticker = ({r["ticker"]: r for r in crowding.get("signals", []) if r.get("ticker")}
                 if isinstance(crowding, dict) else None)
    flow_by_ticker = ({r["ticker"]: r for r in flow.get("stocks", []) if r.get("ticker")}
                      if isinstance(flow, dict) else None)
    records = [
        audit_stock(row, macro, sector_logic or {}, etf_data or {}, by_ticker, flow_by_ticker)
        for row in rankings.get("ranked", [])
    ]
    flow_contradictions = sum(
        1 for r in records for v in r["verdicts"]
        if v["pair"] == "consensus_flow" and v["verdict"] == CONTRADICTION)
    return {
        "generated": date.today().isoformat(),
        "overlay": "coherence overlay (demotion-only, capped at one tier)"
                   + ("; exit-liquidity risk check" if by_ticker is not None else "")
                   + ("; consensus-flow check" if flow_by_ticker is not None else ""),
        "benchmark": (etf_data or {}).get("benchmark"),
        "windows": (etf_data or {}).get("windows"),
        "n_records": len(records),
        "n_demoted": sum(1 for r in records if r["tier_delta"] < 0),
        "n_insufficient": sum(1 for r in records if r["insufficient_data"]),
        "n_divergence_flags": sum(1 for r in records if r["divergence_flag"]),
        "n_exit_liquidity_risks": sum(1 for r in records if r.get("risks")),
        **({"n_flow_contradictions": flow_contradictions} if flow_by_ticker is not None else {}),
        "records": records,
    }


def _load(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        print(f"NOTE: {p.name} not found — affected pairs degrade to insufficient data.")
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rankings", required=True, help="rankings.json (READ-ONLY)")
    ap.add_argument("--macro", help="macro_factors.json — structured E2.1 fields from M1")
    ap.add_argument("--sector-logic", help="sector_logic.json — E2.2 per-industry answers")
    ap.add_argument("--etf", help="etf_relative_strength.json from etf_relative_strength.py")
    ap.add_argument("--crowding", help="crowding_signals.json (v0.4 B7) — enables the "
                                       "exit-liquidity risk check")
    ap.add_argument("--flow", help="consensus_flow.json (v0.4 D3) — enables the "
                                   "consensus-flow check")
    ap.add_argument("--out", required=True, help="Output coherence.json (side-car)")
    args = ap.parse_args()

    rankings = json.loads(Path(args.rankings).read_text(encoding="utf-8"))
    out = audit(rankings, _load(args.macro), _load(args.sector_logic), _load(args.etf),
                _load(args.crowding), _load(args.flow))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"Coherence audit: {out['n_records']} records, {out['n_demoted']} demoted, "
        f"{out['n_insufficient']} with insufficient data, "
        f"{out['n_divergence_flags']} divergence flags, "
        f"{out['n_exit_liquidity_risks']} exit-liquidity risks -> {out_path} "
        f"(rankings.json untouched)"
    )


if __name__ == "__main__":
    main()
