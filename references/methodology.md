# Methodology Reference

This file explains what the financial-research skill does, why, and what it does not do.
It is a reader for humans and other LLMs. It contains no executable rules.

All formulas, weights, and thresholds quoted here reference their canonical source in code.

---

## What the skill does

Given 7–11 HKMA-approved global fund prospectus PDFs distributed through Hong Kong private
banking channels (Standard Chartered HK, Citi HK, and similar), the skill:

1. Extracts US-listed equity holdings from each fund prospectus.
2. Screens stocks for fundamental quality (PASS/FAIL only — see `references/quality_screen.md`).
3. Ranks the passed universe by a composite signal combining fundamental quality and
   consensus-with-crowding-discount (see `references/crowding_signal.md`).
4. Produces the top 15 ranked stocks with rationale cards and an honest framing section.
5. Outputs three layered markdown files and a final English-only PDF.

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
