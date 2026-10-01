# Exit Liquidity and the Currency Gate

This file explains the exit-liquidity measure and the currency gate that protects it. It is
a reader — no executable rules. The canonical code is `scripts/crowding_signal.py`; the
overlay check that uses it is in `scripts/coherence_audit.py`.

The consensus signal — what the funds collectively hold, and how much each fund's opinion
counts — is no longer here. See [`consensus_signal.md`](./consensus_signal.md).

---

## Contents

1. [What changed in v0.4](#what-changed-in-v04)
2. [Days-to-liquidate](#days-to-liquidate)
3. [The currency gate: exclude, never convert (v0.32 G1)](#the-currency-gate-exclude-never-convert-v032-g1)
4. [Thin US exposure: warn, do not re-weight (v0.32 G2)](#thin-us-exposure-warn-do-not-re-weight-v032-g2)
5. [The input review and the style distribution](#the-input-review-and-the-style-distribution)
6. [What it cannot show](#what-it-cannot-show)

---

## What changed in v0.4

v0.3 folded crowding into the rank as a discount on the consensus signal. That discount
measured **NAV weight — conviction — rather than exit risk**: its weight term saturated at a
10% average weight, which is also the single-issuer ceiling, and its liquidity term could only
add to it (F2). A mega-cap held by seven funds at 8% with less than a tenth of a day to
liquidate took the maximum 60% discount.

v0.4 (DEC-4) takes crowding **out of the rank**. Position size no longer lowers a stock's
rank. What remains is the one crowding question the factsheets can answer — how long would
these holders need to sell — and it feeds the coherence overlay as a demotion-only risk check
(`exit_liquidity`, see `coherence_overlay.md`).

## Days-to-liquidate

```
aggregate_position_usd = sum over holders reporting AUM in USD of (fund_AUM × weight_in_fund)
days_to_liquidate      = aggregate_position_usd / ADV_usd
is_exit_crowded        = days_to_liquidate >= 10
```

- The formula assumes **every holder exits at once** — the tail-risk framing.
- **10 days is a round, uncalibrated line** separating days from weeks. There is no backtest
  to fit it against, and it is labelled as such wherever it appears.
- Each ticker is labelled `liquidity-inclusive` (AUM and ADV available) or
  `no-liquidity-data` (either missing). A missing figure is never a guess and never a verdict:
  the overlay records it as insufficient data, and the tier does not move.
- An exit-crowded stock is **demoted one display tier** by the overlay and its card carries
  a HIGH CROWDING flag. Its rank never changes.

## The currency gate: exclude, never convert (v0.32 G1)

`days_to_liquidate` divides an AUM-derived numerator by a USD denominator. ADV is always USD;
a fund's AUM is whatever the factsheet reports. An HKD-reporting fund would overstate
days-to-liquidate by roughly 7.8× — silently. This matters disproportionately here because the
target input is the **Hong Kong distribution channel**, where HKD-denominated share classes
are routine.

The gate is in `fund_aum_map()`:

- A fund's `total_aum` enters the map **only if `currency == "USD"`**.
- A non-USD or `null` currency means the fund is **omitted from the AUM map** — nothing else.
  Its holdings still count in full toward overlap and consensus; only its AUM is in unknown
  units.
- A ticker whose holders all fall outside the map has no liquidity data, and says so.

**No FX conversion exists anywhere in this codebase, by design.** Converting would require an
FX source, a rate-date policy and a new provenance path — three new failure modes to repair a
metric that already degrades cleanly. **Units are either identical or the input is set aside
and labelled; there is no third path**, and an unstated currency is never assumed to be USD.
The same rule governs every ratio in the pipeline: EDGAR ratios are built from same-unit pairs
(ratios are dimensionless), never converted.

## Thin US exposure: warn, do not re-weight (v0.32 G2)

The viability gate is binary: ≥5 US holdings **and** ≥20% US weight. Funds whose kept US
weight falls in **20–35%** are flagged `thin_us_exposure` at Stage 1b and reported in Layer 1,
Layer 2 and Appendix 3. They are not rejected and their votes are not down-weighted: a vote is
about a position, not about how much of the fund is in US equity.

## The input review and the style distribution

`crowding_signals.json` also carries the input review that Layer 2 and Appendix 3 report —
the currency census (`input_review.currency`) and the thin-exposure report
(`input_review.thin_us_exposure`) — and the input set's fund-style distribution
(`homogeneity`). The style labels are LLM-inferred and are **display only** since v0.4: they
enter no number. How independent the funds are is measured from their holdings instead
(`N_eff_run`, `consensus_signal.md` §4).

## What it cannot show

> Seven to eleven Hong Kong–distributed funds are too small to crowd US large caps; global
> crowding cannot be measured from factsheets.

State that sentence once, in the report's framing section. Days-to-liquidate here measures
what **these holders alone** would take to unwind, using only those that report AUM in USD.
It says nothing about how crowded a name is across the global market.
