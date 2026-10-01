# Methodology Reference

This file explains what the financial-research skill does, why, and what it does not do.
It is a reader for humans and other LLMs. It contains no executable rules.

All formulas, weights, and thresholds quoted here reference their canonical source in code.

---

## What the skill does

Given 7–11 HKMA-approved global fund prospectus PDFs distributed through Hong Kong private
banking channels (Standard Chartered HK, Citi HK, and similar), the skill:

1. Extracts each fund's holdings and keeps only securities SEC's exchange file lists on
   Nasdaq, NYSE or CBOE (v0.34; ADRs included), merging identical share classes of one fund
   (v0.4). A coarse fund `style` may be inferred per fund, for display only.
2. Screens stocks for fundamental quality (PASS/FAIL only — see `references/quality_screen.md`).
3. **Ranks by institutional consensus (v0.4):** a fund votes for a stock it holds above the
   common disclosure floor and at or above the stock's benchmark weight (capped at 10%);
   funds are weighted by how independent they are; each stock gets a consensus band —
   majority, plural or single. Eligible stocks are ordered by **band, then low-anchor
   confidence-shrunk quality Q'', then consensus share, then ticker** — an ordering, not a
   weighted sum (see `references/consensus_signal.md`).
4. Produces up to 15 ranked stocks with rationale cards and an honest framing section, and
   lists separately the benchmark-anchored core — names most funds hold only at benchmark
   weight.
5. Audits each ranked stock for coherence between the macro read, the sector operating logic
   and sector-relative price action, and for exit liquidity (v0.4), and **demotes** (never
   promotes) the display tier by one where a pair contradicts or the stock is exit-crowded
   (v0.31 — see `references/coherence_overlay.md`).
6. Adds central-bank-anchored macro and per-stock scenario appendices, and an over-consensus
   / fund-style remediation appendix (v0.3 — see `references/macro_appendix.md`).
7. Appends a per-stock **Important Notice** on the expectations environment and sentiment
   cycle — the two factors the ranking structurally cannot measure — evidenced at sector
   level and attributed per stock (v0.33 — see `references/important_notice.md`). It enters
   no score, rank or tier.
8. Outputs the layered markdown checkpoints and a final English-only PDF; checkpoints are
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

Note on the v0.3 premises below: the third — consensus carrying risk information — is now
met differently. v0.4 measures consensus as votes weighted by fund independence, and moves
exit liquidity out of the rank into the overlay (see the v0.4 section).

## v0.31 additions (coherence overlay)

- **Incoherence is uncertainty, and uncertainty is a quality defect.** This is premise 2
  extended to a new axis: when the macro read, the sector logic and the price action
  contradict each other, that stock's picture is incoherent and its display tier drops.
- **Non-destructive by construction.** The overlay is **demotion-only**, capped at one tier,
  and `rankings.json` is read-only to it. Deleting Stage 3a-bis reproduces the v0.3 report
  exactly — reversibility as a hard property, not an aspiration.
- **Judgment stays separable from the score.** Rank remains a purely quantitative product of
  the composite; tier carries the qualitative judgment. "Ranked #3, demoted to B because X
  contradicts Y" is auditable in a way that folding macro into the score could never be.
- **No uncalibrated weight is written.** A `0.2·Macro` third axis was rejected: with no
  backtest there is no way to validate the weight, and inventing one would be false
  precision. The 50/50 split stays locked.
- **Price is a divergence detector, never confirmation.** Momentum confirmation is
  pro-cyclical, and consensus already is; stacking them would point both the wrong way
  together in a de-rating. Only *contradiction* is acted on.
- **Deferred on purpose.** Industry policy and company-level supply-chain mapping remain out
  of scope — supplier relationships are absent from EDGAR's structured data and are the
  highest fabrication risk in the proposal.

## v0.32 (defect patch — currency integrity + input-review warnings)

v0.32 adds no capability. It closes a currency-unit hole that v0.3's days-to-liquidate
metric silently opened, and adds two warnings the existing gates do not produce. The
composite weights, `Q''`, `C`, rank order, the viability thresholds and the v0.31 overlay
are all untouched.

- **Unlabelled distortion is the thing to prevent.** `currency` was in the `holdings.json`
  schema but was never validated, never read and never converted. Before v0.3 that was
  harmless: the only AUM-dependent check compared a weight sum to a fraction, so the
  currency cancelled. Days-to-liquidate removed the cancellation — an HKD-reporting fund
  overstates it by roughly 7.8×, silently. The distortion is at least directionally
  conservative (over-penalisation, not false optimism), but it is still *unlabelled*, and
  unlabelled distortion is exactly what this skill's honesty framing exists to prevent.
- **Exclude rather than convert.** Non-USD and unstated AUM is set aside, not FX-converted.
  Conversion would need an FX source, a rate-date policy and a new provenance path — three
  new failure modes to repair a metric that already has a well-defined NAV-only fallback.
  Units are either identical or the input is set aside and labelled; there is no third path.
- **Never default an absent field to the convenient value.** An unstated currency is
  recorded as `null` and treated exactly as non-USD. Defaulting to USD is precisely the
  silent assumption this patch removes — and a bare `$` is ambiguous (USD/HKD/SGD/AUD), so
  it counts as unstated too.
- **Warn where re-weighting would overreach.** A fund with 20–35% US exposure votes as
  loudly in the consensus as a 95%-US fund. Exposure-weighting the consensus would alter
  `C`, whose definition is locked — so v0.32 flags the fund and says so in three places
  instead. A defect patch corrects; it does not redefine a signal.
- **Cheap feedback beats strict filtering.** The Stage 0 regional advisory fires before the
  expensive Stage 1a parse but decides nothing: a blocking name-heuristic would falsely
  reject exactly the edge cases the Stage 1c gate handles correctly. A false advisory costs
  one sentence of noise; a false rejection discards a valid input.

## v0.33 (Important Notice — the measurement boundary, made explicit and sourced)

v0.33 adds no capability and changes no number. It names two things the framework is blind
to and gives the reader the evidence to supply them.

- **The quality axis is backward-looking, so the expectations bar is invisible to it.** The
  5-year-average ROE percentile measures profitability that has already occurred. A company
  that has beaten for eight consecutive quarters — with three years of growth already in the
  price — and a company with identical ROE that nobody expects anything from receive the
  *same* `Q`. A4's low-anchor shrinkage sharpens this, since it rewards verifiable historical
  data while expectations are by nature unverifiable. `EV/EBITDA` cannot substitute: it is a
  screen gate only, never scored, and absolute rather than relative to the stock's own range.
- **Unquantifiable here means it must not be quantified here.** The backtest was removed in
  v0.2, so nothing exists to calibrate "the market is overheated" against. A sentiment score
  would be the same false precision the overlay refused when it declined a `0.2·Macro` axis —
  and a valuation tilt would systematically demote semiconductor/AI names, precisely the
  names the HK distribution channel surfaces most. A sourced notice is the only truthful form.
- **Outermost by construction, not by compromise.** The notice reads the results; it does not
  produce them. It never enters `Q''`, `C`, the composite, `rankings.json` or `coherence.json`,
  and it is not a fourth coherence input. Removing it leaves every rank, tier and score
  bit-for-bit identical — v0.31's reversibility property, one layer further out.
- **Wording precision must match evidence granularity.** Sector-level evidence narrated as a
  stock-level verdict is the same defect the C2 gate exists to prevent: the claim exceeds what
  was actually retrieved. "This group is in an elevated-expectations environment" is
  supportable; "this stock is overpriced" is not, and no amount of hedging makes it so.
- **The gate is never relaxed for the softest-looking section.** Single-stock sentiment
  assertions read fluently and are trivially invented — they are the highest-fabrication-risk
  content in this skill. Admitting single-source claims "because it is only a notice" would
  make it the one low-standard region in the report. Thin evidence produces an explicit
  not-found statement, which is itself information: the reader learns which groups are
  well-covered and which are not.
- **Risk awareness is part of understanding markets, not a disclaimer.** The section is
  written constructively. Its argument — *Tier A means highest-ranked on the measurable
  dimensions, and precisely for that reason such a name is more likely already fully priced* —
  is a claim about how to read the ranking, not an escape clause, and it is stated once at
  the section head under the same discipline that states the HK-bias once (D3).
- **Presenting evidence does not create a capability.** The tool still has no regime
  detection, and the notice says so — because adding sources is exactly what would tempt a
  reader to conclude otherwise.

## v0.34 (corrections)

v0.34 adds no capability. It makes the data reaching the ranking match what the method claims:
EDGAR actually answers (its ticker map had pointed at a URL that does not exist), IFRS and
non-USD filers are read in their reporting currency, ratios never mix units, negative equity
never yields a ratio, a stock that passes the screen but cannot be scored is disclosed rather
than dropped, and the US listing is decided by SEC's exchange file rather than by a ticker's
format. Every correction and the evidence behind it is in `CHANGELOG.md`.

## v0.4 (consensus signal v2)

- **A vote is a choice, not a holding.** A fund holding a stock at its benchmark weight has
  expressed no view — the index holds it. A vote requires a position above the common
  disclosure floor and, where the benchmark's proxy top-10 is known, at or above the
  benchmark weight capped at the 10% single-issuer limit.
- **Agreement must count for more, never less.** Votes are weighted by fund independence
  (`omega_f = u_f / N_eff_run`, `u_f = 1 / sum_g S_fg`), which is fixed per run, so adding a
  vote can only raise a stock's consensus share. v0.33's measure fell as more funds agreed.
- **No label the model inferred may move a rank.** Fund-style labels are display only;
  independence is measured from the holdings themselves (`N_eff_run`).
- **Ordering, not weighting.** The ranking is (band, Q'', consensus share, ticker). The 50/50
  composite is retired; no weight is written down because none could be calibrated.
- **Crowding is a risk to name, not a score to subtract.** Days-to-liquidate (USD-reporting
  holders only) moves to the overlay as a demotion-only check; position size no longer lowers
  a rank. Seven to eleven funds cannot crowd a US large cap by themselves, and the report says
  so once.
- **The anchored core is shown, not hidden.** Names every fund holds only at benchmark weight
  are listed in their own section — they are what the index holds, not what the managers chose.

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
5. **Consensus counts positions, not exposure (v0.32, v0.4).** A fund whose US sleeve is
   20–35% of AUM votes on its positions like any other fund; its weight in the consensus
   depends on how independent its holdings are, not on its US share. Such funds are flagged.
6. **Exit-liquidity coverage is currency-limited (v0.32).** Only USD-reporting funds enter
   the days-to-liquidate aggregate, so a HKD-heavy input set leaves more stocks without a
   liquidity figure — a stated gap, never a silently converted number.
7. **Benchmark weights are approximated (v0.4).** A proxy ETF's top-10 stands in for the
   benchmark, at the ETF's own date; a fund without a proxy casts presence votes. See
   `consensus_signal.md` §11.

## Why these choices

v1 attempted to be all things and over-claimed alpha. v0.2 narrows scope to what is honestly
defensible: "here are the best US stocks held in your purchasable HK fund universe, with caveats."
Removing the backtest removes the largest source of false confidence and token cost.
