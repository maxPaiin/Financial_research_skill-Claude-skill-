# Consensus Signal Reference (v0.4)

The consensus side of the ranking: what it measures, what counts as a vote, how funds are
weighted by independence, how bands work, and what it cannot see. It is a reader for Claude
and humans. The canonical code is `scripts/consensus_signal.py`; the benchmark side is
`scripts/benchmark_weights.py` and `scripts/providers/benchmark_map.py`.

## Contents

1. [What consensus means here](#1-what-consensus-means-here)
2. [Why it was rebuilt](#2-why-it-was-rebuilt)
3. [Inputs, and what it never reads](#3-inputs-and-what-it-never-reads)
4. [Fund independence: similarity, weights, N_eff](#4-fund-independence-similarity-weights-n_eff)
5. [The vote rule](#5-the-vote-rule)
6. [Consensus share, opinions and bands](#6-consensus-share-opinions-and-bands)
7. [The benchmark-anchored core](#7-the-benchmark-anchored-core)
8. [How the ranking uses it](#8-how-the-ranking-uses-it)
9. [Worked examples](#9-worked-examples)
10. [Sensitivity switches](#10-sensitivity-switches)
11. [Limitations](#11-limitations)
12. [What the tests enforce](#12-what-the-tests-enforce)

---

## 1. What consensus means here

State it in the report's framing section exactly once:

> Consensus here means what these funds collectively hold at or above their benchmark weight
> (or, where no benchmark data exists, above the common disclosure floor), adjusted for how
> similar the funds are to one another. It is not a quality stamp and not evidence of future
> returns.

A fund that holds a stock at its benchmark weight has expressed no view on it — the index
holds it. A fund that holds it above benchmark weight has chosen to. v0.4 counts the choices,
and weights each fund by how much independent opinion it adds.

## 2. Why it was rebuilt

v0.33's consensus axis `C` was measured on the run's own holdings and failed in five ways
(findings in the v0.4 update specification):

- **It did not rise with agreement (F1).** In a single-mandate run a stock held by one fund
  scored `C = 0.64`, by two `0.47`, by seven `0.49` — the crowding discount, which penalised
  NAV weight, outran the consensus it discounted.
- **LLM-inferred style labels moved it (F3).** The first known label of a list decided a
  fund's style, so label order changed Tier A membership in 99.7% of simulated runs.
- **A vote meant "appears in the disclosed list" (F4).** Disclosure depth differs between
  factsheets, and a top-10 position at or below benchmark weight still counted as conviction.
- **No measure of independent opinion (F5).** Two share classes of one fund were two votes;
  homogeneity was a binary flag.
- **Price drift moved it with no trading (F6).** Weights drift with prices and `C` penalised
  weight.

v0.4 keeps nothing of that computation. The v0.33 formulas survive only in
`scripts/dev/legacy_v033.py`, for side-by-side comparison.

## 3. Inputs, and what it never reads

- `holdings.json` — accepted funds after identical share classes are merged (B1), each with
  its kept US rows and its `scope_summary.disclosure_floor` (B2).
- `benchmark_weights.json` (optional) — per fund, the proxy ETF of the benchmark printed on
  its factsheet and that proxy's top-10 weights (B3).

It reads **nothing else**: no fund-style labels (they are LLM-inferred, I9), no macro or
sector files, no reader-facing notice, no exit-liquidity data. Tests grep the script for
each of these.

## 4. Fund independence: similarity, weights, N_eff

Let `x_f` be fund f's vector of kept US weights. Then:

```
S_fg       = cos(x_f, x_g)  in [0, 1],   S_ff = 1
u_f        = 1 / sum_g S_fg              (raw weight)
N_eff_run  = sum_f u_f                   (independent opinions in the run)
omega_f    = u_f / N_eff_run             (normalised weight; sums to 1)
```

- `1 <= sum_g S_fg <= n`, so `1/n <= u_f <= 1` and `1 <= N_eff_run <= n`.
- With equicorrelated funds (`S_fg = rho` for all f != g), `N_eff_run = n / (1 + (n-1)·rho)`.
  Seven funds at `rho = 0.6` amount to 1.52 independent opinions.
- A fund unlike the others keeps a whole opinion's weight; funds that hold the same names
  share one.
- **Marginal contribution** of fund f is `N_eff_run − N_eff_run(F without f)`: the
  independent opinion the run loses if f is removed. Appendix 3 names the lowest one as the
  upload to replace with a dissimilar fund.
- Exact duplicates (cosine ≥ 0.999 and the same `asof`) are merged before this step (B1):
  0.999 means numerical identity, not a tuned threshold.

## 5. The vote rule

For fund f and stock i with disclosed weight `w`:

| Step | Condition | Vote | Basis |
|---|---|---|---|
| 1 | `w < tau` | no | `below_floor` |
| 2 | active basis, i is in f's proxy top-10 at weight `b`, `w >= min(b, 10%)` | yes | `active` |
| 3 | active basis, i is in f's proxy top-10 at weight `b`, `w < min(b, 10%)` | no | `anchored` |
| 4 | otherwise (not in the top-10, no proxy, or presence basis) | yes | `presence` |

- **`tau`, the common vote floor**, is the largest `disclosure_floor` among accepted funds —
  the smallest weight the shallowest-disclosing fund reports. A position below it cannot be a
  vote, because that fund could not have disclosed it; counting it would reward deeper
  disclosure, not conviction. The fund(s) that set it are reported.
- **`L = 10%`** is the single-issuer ceiling for HK-authorised and UCITS funds (SFC UT Code
  7.1, UCITS Art. 52(2)). A benchmark weight above it is unreachable, so a fund at the cap
  holds as much as it may — that is a vote.
- **No proxy** — the factsheet prints no benchmark, the benchmark is not in the proxy table,
  or its top holdings could not be read — means presence votes for that fund. Layer 1 and
  Layer 2 say which funds those are.

## 6. Consensus share, opinions and bands

```
c_share_i  = sum_f omega_f · v_fi        (share of independent opinion voting for i)
opinions_i = sum_f u_f · v_fi = c_share_i · N_eff_run
```

| Band | Condition |
|---|---|
| majority | `c_share >= 1/2` **and** at least 2 voting funds |
| plural | at least 2 voting funds, not majority |
| single | exactly 1 voting fund |
| none | no voting fund — never ranked |

`omega` is fixed for the run and non-negative, so `c_share` never falls when a vote is added
— the property v0.33 lacked. Requiring two voting funds for a majority stops one dissimilar
fund with `omega >= 1/2` from being a majority on its own.

## 7. The benchmark-anchored core

A stock is in the anchored core when **no fund votes for it**, **at least ⌈N/2⌉ funds hold
it**, and at least one holding is `anchored`. These are the index heavyweights every fund
owns at or below benchmark weight. They are listed in Layer 3's "Benchmark-anchored core
holdings" section and not ranked.

DEC-1's consequence, stated plainly: in a sector-benchmarked run (US or global technology
funds) NVDA / AAPL / MSFT-type names whose benchmark weight exceeds the 10% cap are usually
anchored — every fund holds them, at or below the capped weight. Under the presence basis
(section 10) they would rank in the majority band. Both counts appear on every card.

## 8. How the ranking uses it

`build_rankings.py` orders eligible stocks (passed the screen, quality-scored, at least one
vote) by **(band, −Q'', −c_share, ticker)** and ranks up to 15. Consensus decides which band a
name sits in; confidence-shrunk quality orders names inside a band. There is no weighted sum
and no weight written down (DEC-2) — none could be calibrated, because there is no backtest.
Fewer than five eligible names raises `warning: few_eligible`; Claude tells the user and
offers a presence-basis rerun. There is no automatic fallback.

## 9. Worked examples

**Share classes and a dissimilar fund.** Funds A and B hold identical portfolios; C holds
nothing they hold. `S = [[1, 1, 0], [1, 1, 0], [0, 0, 1]]`, so `u = (0.5, 0.5, 1)`,
`N_eff_run = 2`, `omega = (0.25, 0.25, 0.5)`. A stock only A and B vote for has
`c_share = 0.5` and two voters: majority. A stock only C votes for has `c_share = 0.5` and
one voter: single.

**A benchmark-heavy name.** Fund F's benchmark proxy (IXN) holds NVDA at 14%. F holds NVDA at
9%: `9% < min(14%, 10%)`, so the holding is `anchored` — no vote. A fund at 10% would vote:
it holds the most it may.

**Below the floor.** One fund discloses only its top 10, the smallest at 3.2%; so
`tau = 3.2%`. Another fund's 2.5% position in a small-cap is `below_floor` — the first fund
could not have shown a 2.5% position even if it held one.

**Seven similar funds.** Seven growth funds with pairwise similarity 0.6 amount to
`7 / (1 + 6·0.6) = 1.52` independent opinions. A name all seven vote for has
`c_share = 1.0` and 1.52 opinions — a majority, but of a small body of independent opinion,
which Layer 2 and Appendix 3 say in so many words.

## 10. Sensitivity switches

`consensus_signal.py` (run in phase P3) takes two switches, both for sensitivity runs only:

- `--vote-basis presence` — every position above the floor is a vote (holding-based
  consensus, DEC-1's alternative). No position is anchored and the anchored core is empty.
- `--vote-floor none` — no common floor; every disclosed position can vote.

## 11. Limitations

- **Top-N disclosure.** Only disclosed positions can vote. The common floor makes funds
  comparable, at the cost of ignoring a deep-disclosing fund's smaller positions.
- **Proxy approximations.** A proxy ETF is not the benchmark: IXN tracks S&P Global 1200 IT
  rather than MSCI ACWI IT, XLK is a capped index, and only the proxy's top 10 are read, so a
  stock outside them is a presence vote even if the benchmark holds it.
- **ETF `asof` versus fund `asof`.** Proxy weights are fetched at run time; fund weights are
  as of the factsheet date, typically 30–60 days earlier.
- **The 10% cap simplification.** It ignores the UCITS 5/10/40 aggregate limit (positions
  above 5% may not total more than 40% of NAV), so a fund held below a heavy benchmark weight
  by that rule rather than by choice still reads as anchored.
- **Cosine on top-N vectors.** Similarity is computed on disclosed US rows only: two funds
  with identical top-10s and different tails look identical.
- **Near-duplicates share weight only approximately.** Exact duplicates are merged (B1). When
  a near-duplicate pair overlaps other funds, the sharing is approximate: with `S_AB = 0.5`,
  duplicating A raises A's combined weight from 0.50 to about 0.62.
- **Price drift.** Weights drift with prices, so a position can cross the floor or its
  benchmark weight without a trade. That residual effect is disclosed in the methodology,
  not hidden in a continuous penalty.
- **A small sample.** Seven to eleven funds; no statistical significance is claimed.

## 12. What the tests enforce

`tests/test_v04_consensus.py`: the duplicate and equicorrelated closed forms (to 1e-9), the
bounds over 1,000 random inputs, monotonicity, the F1 regression end to end, the band
boundary, every vote-rule branch including the cap, the anchored core, both sensitivity
switches, and two structural tests — `TestConsensusIgnoresStyle` (I9) and
`TestNoLegacyWeights` (I4).
