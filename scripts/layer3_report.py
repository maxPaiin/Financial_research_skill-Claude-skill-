"""
Stage 3c/d: Generate layer3_ranked_advice.md from rankings.json.

The honest framing paragraph and per-stock rationale cards are injected
by Claude (LLM steps) before this script writes the final structure.
This script assembles the template and the methodology section.

v0.31 (E0.3 / E3.3): tiers stop being a pure display slice. The rank slice
(A = 1-5, B = 6-10, C = 11-15) is the STARTING POINT; the coherence overlay may
then move a stock DOWN one tier. Rank order itself never changes — a stock
ranked #3 whose macro and sector logic contradict each other is still #3, shown
in Tier B, with the contradiction named on its card. Rank stays a purely
quantitative, traceable product of the composite; tier carries the qualitative
judgment, and the two can be read apart. Passing no --coherence file yields
exactly the v0.3 report.
"""

import json
import argparse
from pathlib import Path
from typing import Optional


_DISCLAIMER = Path(__file__).resolve().parents[1] / "assets" / "disclaimer.md"

_METHODOLOGY = """## Methodology disclosure

- **Universe**: HKMA-approved global funds distributed through HK private banking channels
- **Filter**: US-listed equities only (ADRs included; non-US primary listings excluded)
- **Quality screen**: ROE persistence (>= 3 positive years in 5), debt sanity (D/E < 5.0), earnings continuity (no 3 consecutive negative NI years), minimum data availability (>= 2 of 3 key metrics at confidence >= 0.4)
- **Ranking signal**: 50% fundamental quality + 50% consensus-with-crowding-discount (weights fixed at 50/50)
- **Confidence-shrinkage on quality (v0.3)**: the quality half is low-anchor shrunk — Q'' = c·Q + (1 − c)·10, where c is the stock's data confidence. Quality built from low-confidence (yfinance) data is pulled toward a low-but-non-zero anchor (10), so unverifiable numbers cannot float a stock to mid-pack. Applied to the quality half only (its confidence is a real per-source difference); NOT applied to the consensus half (whose "confidence" is staleness, roughly uniform within a run). Q'' is deliberately NOT re-percentiled, so the penalty moves a stock's absolute position. Uncertainty is treated as a quality defect, not a neutral state.
- **Crowding = exit-crowdedness (v0.3)**: the crowding discount folds in days-to-liquidate = (Σ fund_AUM × weight) / average-daily-traded-value, assuming simultaneous exit by all holders. Each crowding figure is labelled liquidity-inclusive (AUM + ADV available) or NAV-only (fell back to the pure-weight discount when AUM/ADV were missing).
- **Consensus = style-diversity-weighted (v0.3)**: consensus is weighted by the style diversity of the holders, so cross-style agreement counts for more than same-mandate funds buying the same names. **Stratified sampling was abandoned** for two reasons: (1) the sample (7–11 funds) is too small to stratify — style cells would hold 1–2 funds; (2) full stratified analysis exceeds this tool's processing/token budget. The replacement is diversity-weighting plus a run-level homogeneity warning (see Appendix 3).
- **Macro/expectations source policy (v0.3)**: macro facts are primary-first — central-bank/official sources fetched by directed URL (Fed, ECB, BoJ + official statistics); open web search is reserved for the secondary/news layer. Every factual sentence in the appendices must be corroborated by >= 2 independent primary-tier sources (a HARD inclusion gate, not a soft discount) and carries per-sentence attribution. A claim traceable only to a low-trust source cannot obtain primary-tier corroboration and is therefore never written. This curated source policy is disclosed because filtering sources is itself a stance.
- **Provider routing**: EDGAR (confidence 0.9) → yfinance fallback (confidence 0.5)
- **Sample size**: {n_funds} HKMA-approved funds — this is a small sample; results are NOT statistically significant{coherence_methodology}

## Important caveats

- Sample size of {n_funds} funds is small; rankings are not statistically significant
- Top-N disclosure in fund prospectuses introduces 30–60 day staleness
- HK distribution-channel bias is not corrected; rankings reflect that bias, not the global equity market
- Consensus among same-style funds is largely tautological; see the homogeneity warning in Appendix 3
- This is a filter and ranking tool, not an alpha-generation or portfolio construction tool
"""

# v0.31 (E3.3 / E4): stated ONCE here, never repeated per card. Only emitted
# when the overlay actually ran — a report that did not run the audit must not
# claim it did.
_COHERENCE_METHODOLOGY = """
- **Coherence overlay (v0.31)**: after ranking, each stock is audited for whether three readings tell the same story — (i) the macro factors extracted from the M1 central-bank corpus (policy-rate direction, inflation trend), (ii) the sector operating logic, expressed as three universal questions instantiated per industry (what constrains the inputs / how much pricing power / what return on capital deployed), and (iii) sector-ETF relative strength versus SPY over fixed 3M/6M/12M windows. A material contradiction between any pair moves the stock **down exactly one display tier** (A→B, B→C; C is the floor) and the contradiction is named on its card.
- **The overlay never alters rank or the composite.** `rankings.json` is read-only to it; the composite weights stay 50/50 and the overlay is not a third scoring axis (its weight could not be calibrated — there is no backtest to calibrate against, and inventing a weight would be the false precision this report exists to avoid). Rank remains a purely quantitative product of the composite; tier carries the qualitative judgment, so "ranked #3 by the composite, demoted to B because X contradicts Y" stays legible and auditable. Removing the overlay reproduces the pre-overlay report exactly.
- **Overlay limitations (must be read with the tiers)**: the coherence verdict is a **qualitative judgment, not a calibrated model**, and is deliberately unweighted. ETF relative strength is **context, not confirmation** — sector ETFs carry their own crowding dynamics, and price agreeing with a thesis is never treated as evidence for it. Macro readings are **directional summaries of central-bank material, not forecasts**. The overlay can only **lower** confidence in a name; it never raises one. Stocks whose sector has no ETF mapping or whose macro read is too sparse are recorded as **"insufficient data" with the tier unchanged** — a data gap is never allowed to pass as coherence, nor to be punished as a contradiction.
- **Divergence is not a defect.** A stock diverging sharply from its sector ETF may be exactly where the alpha is; divergence produces a flag and a required explanation on the card, not a mechanical penalty."""

# v0.3 (D3): the HK-distribution-channel bias is stated ONCE in the opening
# framing section, not repeated on every card. High-crowding cards still carry
# their own per-card warning (kept), and the crowding figure is labelled
# liquidity-inclusive / NAV-only (A2 disclosure).
_CARD_TEMPLATE = """### #{rank}   {ticker}   {name}

**Held by:** {n_funds_holding} of {total_funds} funds ({pct:.0%}){crowding_flag}

**Avg weight where held:** {avg_weight:.2%}  |  **Max weight:** {max_weight:.2%}  |  **asof:** {asof}

**Crowding:** {crowding_label}{dtl_note}

**Quality screen:** PASS  |  **Confidence:** {confidence}
- ROE 5y avg: {roe_avg}
- EV/EBITDA: {ev_ebitda}
- Debt/Equity: {de}

**Composite rank:** {rank} of {n_passed}   |   **Tier:** {tier}{tier_note}{adr_note}
{coherence_block}
**Rank rationale:**
{rationale}
"""

# E3.3: the per-card coherence line carries only THIS stock's contradiction.
# The overlay's rules and limitations live once in the methodology section.
_COHERENCE_BLOCK = "\n**Coherence:** {commentary}\n"

_CROWDING_FLAG = (
    "\n\n> ⚠ HIGH CROWDING — multiple funds hold large positions; "
    "vulnerable to coordinated unwind."
)


def fmt_metric(val, fmt=".2f", suffix="") -> str:
    if val is None:
        return "n/a"
    return f"{val:{fmt}}{suffix}"


def coherence_index(coherence: Optional[dict]) -> dict[str, dict]:
    """ticker -> coherence record. Empty when the overlay did not run."""
    if not isinstance(coherence, dict):
        return {}
    return {r["ticker"]: r for r in coherence.get("records", []) if r.get("ticker")}


def displayed_tier(stock: dict, record: Optional[dict]) -> str:
    """Tier actually shown: the rank slice, possibly demoted by the overlay.

    The overlay's own `demote()` already clamps to demotion-only and one tier;
    this only falls back to the rank slice when no record exists.
    """
    base = stock.get("tier") or "C"
    if not record:
        return base
    return record.get("tier") or base


def build_layer3_md(
    rankings: dict,
    n_funds: int,
    honest_framing: str,
    rationale_cards: dict[str, str],
    coherence: Optional[dict] = None,
) -> str:
    ranked = rankings.get("ranked", [])
    n_passed = rankings.get("n_passed_universe", len(ranked))
    by_ticker = coherence_index(coherence)

    lines = ["# Layer 3: Ranked Watchlist", ""]

    lines += ["## What this analysis is and is not", ""]
    lines += [honest_framing, ""]

    # Tier sections. Grouping uses the DISPLAYED tier (post-overlay); ordering
    # within a tier stays by rank, which the overlay never touches.
    for tier_name in ("A", "B", "C"):
        tier_stocks = sorted(
            (s for s in ranked
             if displayed_tier(s, by_ticker.get(s.get("ticker"))) == tier_name),
            key=lambda s: s.get("rank", 0),
        )
        if not tier_stocks:
            continue
        lines += [f"## Tier {tier_name}", ""]
        demoted_in = [
            s for s in tier_stocks
            if (by_ticker.get(s.get("ticker")) or {}).get("tier_delta", 0) < 0
        ]
        if demoted_in:
            lines += [
                "> Demoted into this tier by the coherence overlay (rank unchanged): "
                + ", ".join(
                    f"{s['ticker']} (#{s.get('rank')}, from Tier "
                    f"{by_ticker[s['ticker']]['base_tier']})"
                    for s in demoted_in
                )
                + ".",
                "",
            ]
        for s in tier_stocks:
            tkr = s["ticker"]
            crowding_flag = _CROWDING_FLAG if s.get("is_high_crowding") else ""
            adr_note = "\n\n> ADR — fundamentals sourced from 20-F or yfinance fallback." \
                if s.get("is_adr") else ""
            crowding_label = s.get("crowding_label") or "NAV-only"
            dtl = s.get("days_to_liquidate")
            dtl_note = f"  |  Days-to-liquidate (all-holders): {dtl:.1f}" \
                if isinstance(dtl, (int, float)) else ""

            record = by_ticker.get(tkr)
            shown_tier = displayed_tier(s, record)
            tier_note = ""
            coherence_block = ""
            if record:
                if record.get("tier_delta", 0) < 0:
                    tier_note = (
                        f"  (demoted from {record['base_tier']} by the coherence "
                        "overlay; rank unchanged)"
                    )
                coherence_block = _COHERENCE_BLOCK.format(
                    commentary=record.get("commentary", "").strip()
                )

            card = _CARD_TEMPLATE.format(
                rank=s["rank"],
                ticker=tkr,
                name=s.get("name") or "",
                n_funds_holding=s.get("n_funds_holding", 0),
                total_funds=n_funds,
                pct=(s.get("n_funds_holding", 0) / max(n_funds, 1)),
                crowding_flag=crowding_flag,
                avg_weight=s.get("avg_weight", 0),
                max_weight=s.get("max_weight", 0),
                asof=s.get("data_asof") or "n/a",
                crowding_label=crowding_label,
                dtl_note=dtl_note,
                confidence=fmt_metric(s.get("data_confidence")),
                roe_avg=fmt_metric(s.get("roe_5y_avg"), ".1%") if s.get("roe_5y_avg") else "n/a",
                ev_ebitda=fmt_metric(s.get("ev_ebitda")),
                de=fmt_metric(s.get("debt_equity")),
                n_passed=n_passed,
                tier=shown_tier,
                tier_note=tier_note,
                coherence_block=coherence_block,
                adr_note=adr_note,
                rationale=rationale_cards.get(tkr, "_Rationale generated by Claude in Step 3b._"),
            )
            lines += [card, ""]

    lines += [_METHODOLOGY.format(
        n_funds=n_funds,
        coherence_methodology=_COHERENCE_METHODOLOGY if by_ticker else "",
    )]

    # Disclaimer
    try:
        disc = _DISCLAIMER.read_text(encoding="utf-8")
    except Exception:
        disc = "_See assets/disclaimer.md_"
    lines += ["## Disclaimer", "", disc]

    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rankings", required=True)
    ap.add_argument("--n-funds", type=int, required=True)
    ap.add_argument("--framing", required=True, help="Path to honest_framing.txt written by Claude")
    ap.add_argument("--rationale-dir", help="Directory with per-ticker rationale .txt files")
    ap.add_argument("--coherence", help="coherence.json from Stage 3a-bis (v0.31). "
                                        "Optional: absent -> pure rank-slice tiers (v0.3 output).")
    ap.add_argument("--out", default="/home/claude/work/layer3_ranked_advice.md")
    args = ap.parse_args()

    rankings = json.loads(Path(args.rankings).read_text(encoding="utf-8"))
    honest_framing = Path(args.framing).read_text(encoding="utf-8")

    coherence = None
    if args.coherence:
        p = Path(args.coherence)
        if p.exists():
            coherence = json.loads(p.read_text(encoding="utf-8"))
        else:
            print(f"NOTE: {p.name} not found — falling back to pure rank-slice tiers.")

    rationale_cards: dict[str, str] = {}
    if args.rationale_dir:
        for f in Path(args.rationale_dir).glob("*.txt"):
            rationale_cards[f.stem.upper()] = f.read_text(encoding="utf-8").strip()

    md = build_layer3_md(rankings, args.n_funds, honest_framing, rationale_cards, coherence)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    n_demoted = (coherence or {}).get("n_demoted", 0)
    print(f"Layer 3 report written to {args.out}"
          + (f" ({n_demoted} tier demotion(s) applied; ranks unchanged)" if coherence else ""))


if __name__ == "__main__":
    main()
