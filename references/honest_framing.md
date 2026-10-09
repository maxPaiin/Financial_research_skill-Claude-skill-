# Honest Framing Reference

This file provides the template and rationale for the Honest Framing section that
appears at the top of Layer 3 (`layer3_ranked_advice.md`) and in the PDF.

It is a reader — Claude generates the actual prose at Stage 3c by filling in the
actual run numbers and following this template.

---

## Contents

1. [What to include (mandatory)](#what-to-include-mandatory)
2. [What to prohibit (no exceptions)](#what-to-prohibit-no-exceptions)
3. [Template (Claude fills in the bracketed fields)](#template-claude-fills-in-the-bracketed-fields)
4. [Where the framing must appear](#where-the-framing-must-appear)

## What to include (mandatory)

The framing paragraph must explicitly state all four biases below, with the specific
numbers from this run, **plus the three v0.3 disclosures**:

1. **HK distribution-channel bias** — funds are a curated subset chosen for sellability to
   HK retail/private clients, clustered around well-known large-caps. **State this ONCE
   here** (v0.3 D3 — it is no longer repeated on every ranked card).

2. **Top-N disclosure lag** — fund prospectuses typically disclose only top-10 to top-20
   holdings; disclosure dates run 30–60 days behind. The analysis reflects a partial, stale
   snapshot.

3. **Small sample size** — this run analyzed N funds (fill with actual number). This is
   statistically small. No ranking result should be interpreted as statistically significant.

4. **Survivorship in the fund universe** — the analyzed funds are operating funds. Failed
   funds and their losing picks are not in the input.

**v0.3 additions (also mandatory in the framing section):**

5. **Independence of the input set (v0.4, replaces the v0.3 style-homogeneity warning)** —
   state how many independent opinions this run's funds amount to: "This run's [N] funds
   amount to [N_eff] independent opinions." (`n_eff_run` in `rankings.json`). Funds that hold
   the same names share one opinion's weight, so a single-mandate input set has an N_eff
   close to 1 and its consensus says little; point to Appendix 3, which names the upload that
   adds least. State this number **once**, here.

6. **Stratification-abandoned note** — state that stratified sampling was abandoned for two
   reasons: the sample (7–11 funds) is too small to stratify meaningfully (style cells would
   hold 1–2 funds), and full stratified analysis exceeds the tool's processing/token budget.
   The replacement is independence weighting of the funds (N_eff, v0.4); fund-style labels are
   shown for context only and enter no number.

7. **Source-selection-method disclosure** — state that macro/expectations facts come only
   from a fixed source whitelist and use a cross-source corroboration HARD gate (≥2
   whitelisted sources per fact, per-sentence attribution), which structurally excludes
   uncorroborated low-trust material.
   A curated source policy is itself a stance and must be transparent.

**v0.4 additions (mandatory, each stated ONCE in the framing section — never per card):**

8. **What consensus means here** — use this sentence: "Consensus here means what these funds
   collectively hold at or above their benchmark weight (or, where no benchmark data exists,
   above the common disclosure floor), adjusted for how similar the funds are to one another.
   It is not a quality stamp and not evidence of future returns."

9. **What exit liquidity cannot show** — use this sentence: "Seven to eleven Hong
   Kong–distributed funds are too small to crowd US large caps; global crowding cannot be
   measured from factsheets."

10. **This run's N_eff** — item 5's sentence, with the run's own numbers.

## What to prohibit (no exceptions)

- No prose may claim the ranking is "alpha" or "alpha-generating."
- No prose may claim statistical significance for any result.
- No prose may promise a particular return or outcome.
- No prose may use language that could be interpreted as investment advice.

## Template (Claude fills in the bracketed fields)

```
This report analyzes [N] HKMA-approved global funds distributed through Hong Kong private
banking channels ([list issuer names]). The analysis covers [P] unique US-listed equities,
of which [P_pass] passed the quality screen and [15] are ranked below.

Before reading the ranked watchlist, please note the following limitations:

1. HK distribution-channel bias. These funds are selected for suitability for HK
   retail and private banking clients, not for global equity breadth. They cluster
   heavily toward well-known large-caps. Rankings reflect this preference set.

2. Data staleness. Fund prospectuses disclose only top-[N_top] holdings, with
   reporting dates approximately [X] days behind the analysis date. The holdings
   picture is partial and may not reflect recent portfolio changes.

3. Small sample. [N] funds is a statistically small sample. Consensus signals
   (a stock held by 6 of [N] funds) carry no statistical significance.

4. Survivorship. Only operating funds appear in the input. Defunct funds and
   their holdings are absent, which may bias results toward more established
   large-cap names.

5. Consensus. Consensus here means what these funds collectively hold at or
   above their benchmark weight (or, where no benchmark data exists, above the
   common disclosure floor), adjusted for how similar the funds are to one
   another. It is not a quality stamp and not evidence of future returns.
   This run's [N] funds amount to [N_eff] independent opinions.

6. Crowding. Seven to eleven Hong Kong–distributed funds are too small to crowd
   US large caps; global crowding cannot be measured from factsheets.

This report is AI-generated and must not be used as investment advice.
See the Disclaimer for the full legal statement.
```

## Where the framing must appear

- Layer 3 markdown: at the top, before any ranked content.
- PDF: as Section 3 (after cover and front disclaimer), before executive summary.
- **Per-stock cards do NOT repeat the bias note (v0.3 D3).** The HK-bias statement lives
  once, here in the framing section. The only per-card warnings retained are the
  high-crowding warning (on high-crowding stocks) and the ADR note. Optionally, a single
  one-line per-tier footer is allowed.
