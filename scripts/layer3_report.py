"""
Stage 3c/d: Generate layer3_ranked_advice.md from rankings.json.

The honest framing paragraph and per-stock rationale cards are injected
by Claude (LLM steps) before this script writes the final structure.
This script assembles the template and the methodology section.

v0.31 (E0.3 / E3.3): tiers stop being a pure display slice. The rank slice
(A = 1-5, B = 6-10, C = 11-15) is the STARTING POINT; the coherence overlay may
then move a stock DOWN one tier. Rank order itself never changes — a stock
ranked #3 whose macro and sector logic contradict each other is still #3, shown
in Tier B, with the contradiction named on its card. Passing no --coherence
file yields the pre-overlay report.

v0.4 (B8):
- Cards follow the v0.4 template: the consensus band and the independent
  opinions behind it, how each holder voted, exit liquidity, quality and its
  confidence, and "Rank" (there is no composite any more).
- Every card field comes from rankings.json except the days-to-liquidate line
  and the HIGH CROWDING flag, which come from crowding_signals.json via
  --crowding. The flag appears only on an exit-crowded stock.
- A "Benchmark-anchored core holdings" section lists the names most funds hold
  only at benchmark weight; they are not ranked.
- An empty tier is announced only when its rank slice had stocks and the
  overlay demoted every one of them; a slice with no ranked stock prints nothing.
"""

import json
import argparse
from pathlib import Path
from typing import Optional

from paths import work_dir

_DISCLAIMER = Path(__file__).resolve().parents[1] / "assets" / "disclaimer.md"
_TIER_SLICES = {"A": (1, 5), "B": (6, 10), "C": (11, 15)}
_BAND_LABELS = {"majority": "Majority consensus", "plural": "Plural consensus",
                "single": "Single-fund conviction"}

_METHODOLOGY = """## Methodology disclosure

- **Universe**: HKMA-approved global funds distributed through HK private banking channels; identical share classes of one fund count once
- **Filter**: US exchange-listed equities only — SEC's exchange file must list the ticker on Nasdaq, NYSE or CBOE. ADRs are included; OTC lines and home-market lines are excluded, and every dropped row is disclosed in Layer 1 with its reason. A non-US ISIN alone never excludes a US-listed share
- **Quality screen**: ROE persistence (>= 3 positive years in 5), debt sanity (D/E < 5.0), earnings continuity (no 3 consecutive negative NI years), minimum data availability (>= 2 of 3 key metrics at confidence >= 0.4). ROE and D/E are left undefined, never sign-flipped, when equity is zero or negative
- **Consensus band (v0.4)**: a fund votes for a stock when it holds it above the common disclosure floor ({floor_text}) and, where the top-10 of its benchmark's proxy ETF is known, at or above that stock's benchmark weight capped at the 10% single-issuer limit. A position at or below benchmark weight is "benchmark-anchored" — what the index holds, not a choice — and is not a vote; a fund without a benchmark proxy casts presence votes. Votes are weighted by how independent the funds are: funds holding the same names share one opinion's weight, so this run's {n_funds} funds amount to {n_eff_run:.2f} independent opinions. A stock's consensus share is the weighted share of opinion that votes for it. **Majority**: at least half of the independent opinion and at least two voting funds; **plural**: two or more voting funds; **single**: one. Fund-style labels, macro and price data never enter it
- **Ranking (v0.4)**: an ordering, not a weighted sum — consensus band first, then confidence-shrunk quality Q'', then the consensus share, then the ticker. No weight is written down, because none could be calibrated (there is no backtest). Up to 15 names are ranked; a name no fund votes for is not
- **Confidence-shrinkage on quality (v0.3)**: Q'' = c·Q + (1 − c)·10, where Q is the stock's ROE percentile and c the confidence of its ROE data (EDGAR 0.9, yfinance 0.5; v0.34: the ROE points only, not unrelated fill-ins). Unverifiable quality is pulled toward a low-but-non-zero anchor, so it cannot float a stock up its band; Q'' is not re-percentiled, so the penalty moves the stock's absolute position. Uncertainty is treated as a quality defect, not a neutral state
- **Exit liquidity (v0.4)**: days-to-liquidate = (Σ AUM × weight over the holders that report AUM in USD) / average daily traded value — how many trading days those holders would need to sell together. It no longer affects rank. At 10 days or more (a round, uncalibrated line) the coherence overlay moves the stock down one display tier and its card carries a HIGH CROWDING flag. A stock without the inputs is marked as having no liquidity data
- **Reporting-currency exclusion (v0.32)**: only funds that report AUM in USD enter the days-to-liquidate aggregate. Average daily traded value is always USD, so admitting an AUM reported in HKD or JPY would overstate days-to-liquidate by roughly the exchange rate. A fund reporting in another currency, or not stating one, is **excluded from that aggregate** (its holdings still count in full toward overlap and consensus). **No FX conversion is performed anywhere in this pipeline**, and an unstated currency is never assumed to be USD
- **Macro/expectations source policy (v0.3)**: macro facts are primary-first — central-bank/official sources fetched by directed URL (Fed, ECB, BoJ + official statistics); open web search is reserved for the secondary/news layer. Every factual sentence in the appendices must be corroborated by >= 2 independent primary-tier sources (a HARD inclusion gate, not a soft discount) and carries per-sentence attribution. A claim traceable only to a low-trust source cannot obtain primary-tier corroboration and is therefore never written. This curated source policy is disclosed because filtering sources is itself a stance
- **Provider routing**: EDGAR (confidence 0.9; us-gaap and ifrs-full filings, ratios in the issuer's reporting currency) → yfinance fallback field by field (confidence 0.5)
- **Passed but unscored (v0.34)**: a stock that clears the screen with fewer than two defined ROE years (a trailing-only record, or equity at or below zero in most years) has no quality percentile and is not ranked; Layer 2 names each one, with its reason, under "Passed the screen but could not be scored"
- **Sample size**: {n_funds} HKMA-approved funds — this is a small sample; results are NOT statistically significant{coherence_methodology}

## Important caveats

- Sample size of {n_funds} funds is small; rankings are not statistically significant
- Top-N disclosure in fund factsheets introduces 30–60 day staleness, and only disclosed positions can vote
- HK distribution-channel bias is not corrected; rankings reflect that bias, not the global equity market
- Benchmark weights come from a proxy ETF's top-10 holdings — an approximation of the benchmark, at the ETF's own date
- Price moves change disclosed weights without any trade, so a position can cross the floor or its benchmark weight between factsheets
- A fund with a thin US sleeve (20–35% of AUM) votes on its positions like any other; such funds are flagged in Layer 1 and Layer 2
- This is a filter and ranking tool, not an alpha-generation or portfolio construction tool
"""

# v0.4 D3: emitted only when the consensus-flow check ran (coherence.json says so).
_FLOW_METHODOLOGY = """
- **Consensus flow (v0.4, this run)**: an earlier factsheet snapshot of the same funds was supplied, so the overlay also asked whether each fund's weights moved more than price drift and weight rounding explain. A stock in the majority band that two or more funds trimmed beyond both is a contradiction — the agreement its rank rests on is being sold — and drops one tier under the same cap. A fund's own NAV prices its return only for a USD share class; otherwise its benchmark proxy ETF or SPY does. Two snapshots show net change only; the rank never reads the flow."""

# v0.31 (E3.3 / E4): stated ONCE here, never repeated per card. Only emitted
# when the overlay actually ran — a report that did not run the audit must not
# claim it did.
_COHERENCE_METHODOLOGY = """
- **Coherence overlay (v0.31)**: after ranking, each stock is audited for whether three readings tell the same story — (i) the macro factors extracted from the M1 central-bank corpus (policy-rate direction, inflation trend), (ii) the sector operating logic, expressed as three universal questions instantiated per industry (what constrains the inputs / how much pricing power / what return on capital deployed), and (iii) sector-ETF relative strength versus SPY over fixed 3M/6M/12M windows. A material contradiction between any pair moves the stock **down exactly one display tier** (A→B, B→C; C is the floor) and the contradiction is named on its card. Since v0.4 the overlay also checks exit liquidity: an exit-crowded stock is a risk, demoted the same single tier, however many checks fail.
- **The overlay never alters rank.** `rankings.json` is read-only to it, and it is not a scoring axis (its weight could not be calibrated — there is no backtest to calibrate against, and inventing a weight would be the false precision this report exists to avoid). Rank remains a purely quantitative ordering; tier carries the qualitative judgment, so "ranked #3, demoted to B because X contradicts Y" stays legible and auditable. Removing the overlay reproduces the pre-overlay report exactly.
- **Overlay limitations (must be read with the tiers)**: the coherence verdict is a **qualitative judgment, not a calibrated model**, and is deliberately unweighted. ETF relative strength is **context, not confirmation** — sector ETFs carry their own crowding dynamics, and price agreeing with a thesis is never treated as evidence for it. Macro readings are **directional summaries of central-bank material, not forecasts**. The overlay can only **lower** confidence in a name; it never raises one. Stocks whose sector has no ETF mapping or whose macro read is too sparse are recorded as **"insufficient data" with the tier unchanged** — a data gap is never allowed to pass as coherence, nor to be punished as a contradiction.
- **Divergence is not a defect.** A stock diverging sharply from its sector ETF may be exactly where the alpha is; divergence produces a flag and a required explanation on the card, not a mechanical penalty."""

# v0.4 card (spec Appendix C). The HK-bias note is stated ONCE in the framing
# section (v0.3 D3), never per card; the HIGH CROWDING flag is per card.
_CARD_TEMPLATE = """### #{rank}   {ticker}   {name}

**Consensus:** {band_label} — {opinions:.1f} of {n_eff_run:.1f} independent opinions (share {c_share:.0%})
- Votes: {n_votes} of {n_funds} funds ({n_active} active, {n_presence} presence) | benchmark-anchored holders: {n_anchored} | below common floor ({floor_text}): {n_below}

**Holdings:** held by {n_holders} of {n_funds} funds | avg weight where held {avg_weight:.2%} | max {max_weight:.2%} | asof {asof}

**Exit liquidity:** {dtl_text}{exit_flag}

**Quality screen:** PASS | **Quality confidence:** {quality_confidence}
- ROE avg: {roe_avg} ({roe_years} fiscal years; {roe_source})
- EV/EBITDA: {ev_ebitda} | Debt/Equity: {de}

**Rank:** {rank} of {n_eligible} | **Tier:** {tier}{tier_note}{adr_note}
{coherence_block}
**Rank rationale:**
{rationale}
"""

# E3.3: the per-card coherence line carries only THIS stock's contradiction.
# The overlay's rules and limitations live once in the methodology section.
_COHERENCE_BLOCK = "\n**Coherence:** {commentary}\n"

_EXIT_FLAG = (
    "\n\n> ⚠ HIGH CROWDING — exit-crowded: the holders that report AUM in USD would "
    "need {dtl:.1f} trading days of average volume to sell together (10 or more, an "
    "uncalibrated line)."
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


def crowding_index(crowding: Optional[dict]) -> Optional[dict[str, dict]]:
    """ticker -> crowding_signals.json row; None when the file was not given."""
    if not isinstance(crowding, dict):
        return None
    return {r["ticker"]: r for r in crowding.get("signals", []) if r.get("ticker")}


def displayed_tier(stock: dict, record: Optional[dict]) -> str:
    """Tier actually shown: the rank slice, possibly demoted by the overlay.

    The overlay's own `demote()` already clamps to demotion-only and one tier;
    this only falls back to the rank slice when no record exists.
    """
    base = stock.get("tier") or "C"
    if not record:
        return base
    return record.get("tier") or base


def _dtl_text(sig: Optional[dict], crowding_given: bool) -> tuple[str, str]:
    """(exit-liquidity text, HIGH CROWDING flag or "")."""
    if not crowding_given:
        return "not reported (no crowding file was supplied)", ""
    dtl = (sig or {}).get("days_to_liquidate")
    if not isinstance(dtl, (int, float)):
        return ("no days-to-liquidate figure (no holder reports AUM in USD, or no "
                "average daily volume)"), ""
    n_usd, n_all = (sig or {}).get("n_usd_aum_holders"), (sig or {}).get("n_holders")
    who = (f"the {n_usd} of {n_all} holders that report AUM in USD" if n_usd and n_all
           else "the holders that report AUM in USD")
    flag = _EXIT_FLAG.format(dtl=dtl) if sig.get("is_exit_crowded") else ""
    return f"{dtl:.1f} trading days for {who} to sell together", flag


def _card(s: dict, rankings: dict, n_funds: int, record: Optional[dict],
          sig: Optional[dict], crowding_given: bool, rationale: str) -> str:
    counts = s.get("vote_basis_counts") or {}
    floor = rankings.get("vote_floor")
    dtl_text, exit_flag = _dtl_text(sig, crowding_given)
    tier_note, coherence_block = "", ""
    if record:
        if record.get("tier_delta", 0) < 0:
            tier_note = (f"  (demoted from {record['base_tier']} by the coherence overlay; "
                         "rank unchanged)")
        coherence_block = _COHERENCE_BLOCK.format(commentary=record.get("commentary", "").strip())
    roe_years = s.get("roe_years")
    return _CARD_TEMPLATE.format(
        rank=s["rank"], ticker=s["ticker"], name=s.get("name") or "",
        band_label=_BAND_LABELS.get(s.get("band"), s.get("band") or "n/a"),
        opinions=s.get("opinions") or 0.0, n_eff_run=rankings.get("n_eff_run") or 0.0,
        c_share=s.get("c_share") or 0.0,
        n_votes=s.get("n_votes", 0), n_funds=n_funds,
        n_active=counts.get("active", 0), n_presence=counts.get("presence", 0),
        n_anchored=counts.get("anchored", 0), n_below=counts.get("below_floor", 0),
        floor_text=f"{floor:.1%}" if isinstance(floor, (int, float)) else "off",
        n_holders=s.get("n_holders") or s.get("n_funds_holding", 0),
        avg_weight=s.get("avg_weight") or 0, max_weight=s.get("max_weight") or 0,
        asof=s.get("data_asof") or "n/a",
        dtl_text=dtl_text, exit_flag=exit_flag,
        quality_confidence=fmt_metric(s.get("quality_confidence")),
        roe_avg=fmt_metric(s.get("roe_5y_avg"), ".1%"),
        roe_years=roe_years if roe_years is not None else "n/a",
        roe_source=s.get("roe_source") or "n/a",
        ev_ebitda=fmt_metric(s.get("ev_ebitda")), de=fmt_metric(s.get("debt_equity")),
        n_eligible=rankings.get("n_eligible", len(rankings.get("ranked", []))),
        tier=displayed_tier(s, record), tier_note=tier_note,
        adr_note=("\n\n> ADR — fundamentals from the issuer's annual report on SEC EDGAR "
                  "(US GAAP or IFRS, in its reporting currency) or the yfinance fallback."
                  if s.get("is_adr") else ""),
        coherence_block=coherence_block, rationale=rationale,
    )


def _anchored_section(rankings: dict, n_funds: int) -> list[str]:
    lines = ["## Benchmark-anchored core holdings", ""]
    if rankings.get("vote_basis") == "presence":
        return lines + ["_Not computed: this run counts presence votes (--vote-basis "
                        "presence), so no position is benchmark-anchored._", ""]
    detail = rankings.get("anchored_core_detail") or [
        {"ticker": t} for t in rankings.get("anchored_core") or []]
    if not detail:
        return lines + ["_None this run: no name is held by most funds only at or below "
                        "its benchmark weight._", ""]
    lines += ["These names are held by most funds in the run, but only at or below their "
              "benchmark weight (capped at the 10% single-issuer limit): they are what the "
              "benchmark holds rather than what the managers chose, so no fund votes for "
              "them and they are not ranked. Seeing them is part of reading the watchlist "
              "correctly — a fund that holds them at benchmark weight has expressed no "
              "view on them.", ""]
    lines += ["| Ticker | Name | Held by | Benchmark-anchored holders | Screen |",
              "|---|---|---|---|---|"]
    for d in detail:
        counts = d.get("vote_basis_counts") or {}
        lines += [f"| {d['ticker']} | {d.get('name') or ''} "
                  f"| {d.get('n_holders', 'n/a')} of {n_funds} funds "
                  f"| {counts.get('anchored', 'n/a')} "
                  f"| {d.get('screen_status') or 'n/a'} |"]
    return lines + [""]


def build_layer3_md(
    rankings: dict,
    n_funds: Optional[int],
    honest_framing: str,
    rationale_cards: dict[str, str],
    coherence: Optional[dict] = None,
    crowding: Optional[dict] = None,
) -> str:
    ranked = rankings.get("ranked", [])
    n_funds = n_funds or rankings.get("n_funds") or 0
    by_ticker = coherence_index(coherence)
    signals = crowding_index(crowding)

    lines = ["# Layer 3: Ranked Watchlist", ""]

    lines += ["## What this analysis is and is not", ""]
    lines += [honest_framing, ""]

    if rankings.get("warning") == "few_eligible":
        lines += [f"> Fewer than five names have a qualifying vote this run "
                  f"({rankings.get('n_eligible', len(ranked))} eligible). The watchlist is "
                  "short by construction, not by error; a sensitivity run counting every "
                  "disclosed position (--vote-basis presence) is available on request.", ""]

    # Tier sections. Grouping uses the DISPLAYED tier (post-overlay); ordering
    # within a tier stays by rank, which the overlay never touches.
    for tier_name in ("A", "B", "C"):
        tier_stocks = sorted(
            (s for s in ranked
             if displayed_tier(s, by_ticker.get(s.get("ticker"))) == tier_name),
            key=lambda s: s.get("rank", 0),
        )
        if not tier_stocks:
            # F19: say so only when the slice had stocks and all were demoted.
            lo, hi = _TIER_SLICES[tier_name]
            slice_ranks = [s.get("rank") for s in ranked if lo <= (s.get("rank") or 0) <= hi]
            if slice_ranks:
                lines += [f"## Tier {tier_name}", "",
                          f"_No stock is displayed in Tier {tier_name}: every rank "
                          f"{min(slice_ranks)}–{max(slice_ranks)} name was demoted one tier "
                          "by the overlay (ranks unchanged)._", ""]
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
            card = _card(s, rankings, n_funds, by_ticker.get(tkr),
                         (signals or {}).get(tkr), signals is not None,
                         rationale_cards.get(tkr, "_Rationale generated by Claude in Step 3b._"))
            lines += [card, ""]

    lines += _anchored_section(rankings, n_funds)

    n_eff = rankings.get("n_eff_run")
    floor = rankings.get("vote_floor")
    lines += [_METHODOLOGY.format(
        n_funds=n_funds,
        n_eff_run=n_eff if isinstance(n_eff, (int, float)) else 0.0,
        floor_text=f"{floor:.1%} this run" if isinstance(floor, (int, float)) else "off this run",
        coherence_methodology=(_COHERENCE_METHODOLOGY if by_ticker else "")
        + (_FLOW_METHODOLOGY if by_ticker and "n_flow_contradictions" in (coherence or {})
           else ""),
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
    ap.add_argument("--n-funds", type=int, help="Defaults to rankings.json n_funds.")
    ap.add_argument("--framing", required=True, help="Path to honest_framing.txt written by Claude")
    ap.add_argument("--rationale-dir", help="Directory with per-ticker rationale .txt files")
    ap.add_argument("--coherence", help="coherence.json from Stage 3a-bis (v0.31). "
                                        "Optional: absent -> pure rank-slice tiers.")
    ap.add_argument("--crowding", help="crowding_signals.json (v0.4): days-to-liquidate and "
                                       "the HIGH CROWDING flag on each card.")
    ap.add_argument("--out", default=str(work_dir() / "layer3_ranked_advice.md"),
                    help="Default: the work directory (paths.py).")
    args = ap.parse_args()

    rankings = json.loads(Path(args.rankings).read_text(encoding="utf-8"))
    honest_framing = Path(args.framing).read_text(encoding="utf-8")

    def _optional(path: Optional[str], what: str) -> Optional[dict]:
        if not path:
            return None
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        print(f"NOTE: {p.name} not found — {what}.")
        return None

    coherence = _optional(args.coherence, "falling back to pure rank-slice tiers")
    crowding = _optional(args.crowding, "cards report no exit-liquidity figure")

    rationale_cards: dict[str, str] = {}
    if args.rationale_dir:
        for f in Path(args.rationale_dir).glob("*.txt"):
            rationale_cards[f.stem.upper()] = f.read_text(encoding="utf-8").strip()

    md = build_layer3_md(rankings, args.n_funds, honest_framing, rationale_cards,
                         coherence, crowding)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    n_demoted = (coherence or {}).get("n_demoted", 0)
    print(f"Layer 3 report written to {args.out}"
          + (f" ({n_demoted} tier demotion(s) applied; ranks unchanged)" if coherence else ""))


if __name__ == "__main__":
    main()
