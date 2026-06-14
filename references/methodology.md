# Methodology Reference

This file explains what the financial-research skill does, why, and what it does not do.
It is a reader for humans and other LLMs. It contains no executable rules.

All formulas, weights, and thresholds quoted here reference their canonical source in code.

---

## What the skill does

Given 7–11 HKMA-approved global fund prospectus PDFs distributed through Hong Kong private
banking channels (Standard Chartered HK, Citi HK, and similar), the skill:

1. Extracts US-listed equity holdings from each fund prospectus (v0.3: pdfplumber table
   recovery + LLM normalisation; a coarse fund `style` is inferred per fund).
2. Screens stocks for fundamental quality (PASS/FAIL only — see `references/quality_screen.md`).
3. Ranks the passed universe by a composite signal (fixed 50/50) combining **low-anchor
   confidence-shrunk** fundamental quality and a **style-diversity-weighted,
   exit-liquidity-aware** consensus-with-crowding-discount (see `references/crowding_signal.md`).
4. Produces the top 15 ranked stocks with rationale cards and an honest framing section.
5. Adds central-bank-anchored macro and per-stock scenario appendices, and an over-consensus
   / fund-style remediation appendix (v0.3 — see `references/macro_appendix.md`).
6. Outputs the layered markdown checkpoints and a final English-only PDF; checkpoints are
   copied to the user-visible outputs directory.

## v0.3 design premises (locked)

- **Conservative-by-design.** A defensible starting point biased toward what can be verified.
- **Uncertainty is a quality defect, not a neutral state.** Low-confidence quality is pulled
  toward a low (but non-zero) anchor, not shrunk to the median — see `build_rankings.py` A4.
- **Consensus is not alpha.** Crowding is rebuilt to carry exit-liquidity risk (days-to-
  liquidate) and consensus is weighted by holder style-diversity, not raw count.
- **Primary sources outrank secondary.** Macro facts are central-bank/official, gated by a
  hard ≥2-primary-tier corroboration rule with per-sentence attribution.
- **Honesty about method is part of the product.** Every selection bias, data fallback, and
  source-filtering rule is disclosed in the report.

## What the skill is NOT

- **Not an alpha-generation tool.** The starting universe is a distribution-preference set,
  not the global equity market.
- **Not a portfolio construction tool.** Output is a ranked watchlist, not allocation weights.
- **Not a backtest engine.** No historical simulation is performed (removed in v0.2).
- **Not a global equity tool.** US-listed equities only (ADRs included).
- **Not a bilingual tool.** All output files are English-only.
- **Not a three-strategies tool.** One ranking, three display tiers (A/B/C), no parallel strategies.

## Known biases (must be disclosed in every report)

1. **HK distribution-channel bias.** Funds cluster around well-known large-caps sellable
   to HK retail/private clients.
2. **Top-N disclosure lag.** Fund prospectuses typically disclose only top-10 to top-20
   holdings, 30–60 days stale.
3. **Small sample size.** 7–11 funds is statistically small; no claim of significance is made.
4. **Survivorship in the fund universe.** Failed funds and their losing picks are absent.

## Why these choices

v1 attempted to be all things and over-claimed alpha. v0.2 narrows scope to what is honestly
defensible: "here are the best US stocks held in your purchasable HK fund universe, with caveats."
Removing the backtest removes the largest source of false confidence and token cost.
