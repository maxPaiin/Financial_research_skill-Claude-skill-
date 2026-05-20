# Honest Framing Reference

This file provides the template and rationale for the Honest Framing section that
appears at the top of Layer 3 (`layer3_ranked_advice.md`) and in the PDF.

It is a reader — Claude generates the actual prose at Stage 3c by filling in the
actual run numbers and following this template.

---

## What to include (mandatory, per §7.3.2)

The framing paragraph must explicitly state all four biases from §1.4 of Iteration_0.2v.md,
with the specific numbers from this run:

1. **HK distribution-channel bias** — funds are a curated subset chosen for sellability to
   HK retail/private clients, clustered around well-known large-caps.

2. **Top-N disclosure lag** — fund prospectuses typically disclose only top-10 to top-20
   holdings; disclosure dates run 30–60 days behind. The analysis reflects a partial, stale
   snapshot.

3. **Small sample size** — this run analyzed N funds (fill with actual number). This is
   statistically small. No ranking result should be interpreted as statistically significant.

4. **Survivorship in the fund universe** — the analyzed funds are operating funds. Failed
   funds and their losing picks are not in the input.

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

This report is AI-generated and must not be used as investment advice.
See the Disclaimer for the full legal statement.
```

## Where the framing must appear

- Layer 3 markdown: at the top, before any ranked content.
- PDF: as Section 3 (after cover and front disclaimer), before executive summary.
- Per-stock cards: each card ends with "Bias note: This rank reflects HK distribution
  channel preference. It is not a market-wide alpha signal."
