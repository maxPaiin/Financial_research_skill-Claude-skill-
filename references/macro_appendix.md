# Macro & Expectations Appendices Reference (v0.3, amended by v0.31 and v0.33)

This file specifies the v0.3 web-retrieval subsystem and the three report
appendices it feeds. It is a reader for Claude and humans — the macro stages
(M1, M2) are performed by Claude in-conversation, not by a script. The only
scripts involved are `check_checkpoints.py` (deterministic gate) and
`build_report.py` (renders the appendix `.md` files into the PDF).

> **v0.31 amendment (E0.2) — M1 moves earlier.** M1 now runs **after Stage 2d**
> (post-screen, pre-rank) instead of after 3a, and its sector scope is anchored
> to the **post-screen universe's industries** (`passed_industries` in
> `screen_results.json`) instead of the top-15's. Reason: the coherence overlay
> lets macro inform tiering, so macro must exist before ranking — and the top-15
> is *produced by* ranking, which makes the old anchor circular. The screened
> universe is bounded (a few dozen names across a limited set of industries), so
> the cost-control intent of the original scoping rule is preserved.
> **This is a pure sequencing move: M1's internal logic, its sources, the
> directed-fetch policy and the C2 hard gate below are unchanged.** M2 stays
> after ranking, scoped to the final 15.

> **v0.33 amendment (H2.4) — M1 gains a facet, not a scope.** Alongside the
> macro read, M1 also records, **for the same sector scope it already covers**,
> the **expectations environment and sentiment cycle** of each industry: is the
> group's expectations bar elevated, where is it in the optimism/pessimism cycle.
> Same sources, same C2 hard gate, same per-sentence attribution — **no new
> retrieval scope and no per-stock retrieval.** This facet feeds the v0.33
> Important Notice (`references/important_notice.md`) via `macro_checkpoint.md`.
> **It must not be written into `macro_factors.json`**: that file is the
> coherence overlay's input, and anything placed there can move a display tier,
> which the notice may never do.

> **Premise carried from v0.3 §0:** primary sources outrank secondary; one-hand
> data outranks news; central-bank output *is* the macro view and is the most
> manipulation-resistant source available. Honesty about the source policy is
> part of the product.

---

## M1 — Macro fetch (central-bank-anchored, directed-fetch) → `macro_checkpoint.md`

**Backbone (primary tier — all free & public, fetched by directed URL, never by
open search):**

- **Fed** — FOMC statements & minutes, Summary of Economic Projections (incl.
  the dot plot), Beige Book, semiannual Monetary Policy Report.
- **ECB** — monetary policy decisions & statements, Economic Bulletin,
  Eurosystem staff macroeconomic projections, monetary policy meeting accounts.
- **BoJ** — Outlook for Economic Activity and Prices (展望レポート), Tankan
  (短観), monetary policy statements.
- Plus official statistical releases as needed (BLS, BEA, Eurostat, e-Stat …).

**Supplement (use only if publicly retrievable; never a prerequisite):**
Reuters, WSJ, BlackRock public commentary (e.g. BlackRock Investment Institute),
Fitch public rating commentary. Sell-side research (Citi/JPM/Nomura/…) is mostly
paywalled — best-effort only.

**Scope to the screened universe's industries — not a generic global macro dump.**
Read `passed_industries` from `screen_results.json` (v0.31: the post-screen
universe, available immediately after Stage 2d) to determine which sectors are
actually in play, then analyse the macro **and aggregate market-demand** picture
*for those sectors specifically*. This honours the per-industry Appendix-2
requirement and is cheaper than a generic survey because it bounds retrieval to
the sectors in play.

**Also emit the structured fields (v0.31 E2.1) — do not re-fetch anything.**
Inflation trajectory and the policy-rate path are already in the corpus above.
Alongside `macro_checkpoint.md`, extract them into `macro_factors.json` so the
coherence overlay can compare against them:

```json
{
  "asof": "2026-08-01",
  "policy_rate_direction": "tightening | on_hold | easing",
  "inflation_trend": "rising | stable | falling",
  "sources": {
    "policy_rate_direction": ["Fed FOMC statement 2026-07-29", "Reuters"],
    "inflation_trend": ["BLS CPI release 2026-07-14", "Fed SEP 2026-06"]
  }
}
```

**Also record the expectations/sentiment facet (v0.33 H2.4) — again, no new
fetching.** For each industry already in scope, note whether the group's
**expectations bar** is elevated (is a beat the market's default assumption?) and
where the group sits in the **sentiment cycle** (optimism / pessimism after a run
of performance). Both are group-level readings only — never per company — and
both are subject to the C2 hard gate: two independent primary-tier sources or the
statement is not written. Keep them in `macro_checkpoint.md`, **not** in
`macro_factors.json`. Stage H1 turns them into the per-stock Important Notice;
full spec: `references/important_notice.md`.

The **C2 hard gate below applies unchanged** to any of this carried into the
report. A direction that cannot clear the gate is left out — the overlay then
records "insufficient data" and leaves the tier alone, which is the correct
outcome. Full overlay spec: `references/coherence_overlay.md`.

---

## C2 — Source integrity: primary-first + cross-source corroboration HARD gate

No blacklist is maintained. Integrity is enforced structurally:

1. **Primary-first at the retrieval layer.** Use **directed-fetch** for the
   primary tier (known central-bank / official URLs). Reserve open `web_search`
   for the **secondary/news layer only**. This confines the contamination
   surface to the secondary layer.
2. **Corroboration is a HARD inclusion gate, not a soft discount.** Any factual
   statement in the macro/expectations appendices may be written **only if
   corroborated by ≥2 independent sources within the primary tier** (central
   banks / official statistics / Reuters / WSJ / BlackRock / Fitch). A claim
   traceable only to a low-trust platform cannot obtain primary-tier
   corroboration → it auto-fails the gate and is **not written**.
3. **Per-sentence attribution.** Every factual sentence carries its source(s)
   in brackets, e.g. `... rates held at 4.25–4.50%. [Fed FOMC; Reuters]`. The
   deterministic gate (`check_checkpoints.py`) requires at least one bracketed
   citation in each macro/expectations checkpoint.
4. **Commentary/opinion** is subject to the same gate; do not adopt commentary
   from outside the primary tier.
5. **Disclose the method.** The source-selection policy (primary-first, the
   hard corroboration gate, and that it structurally excludes uncorroborated
   low-trust material) is disclosed in the report's methodology section.

**Semantic boundary (state it in the disclosure).** Under the hard gate a
low-trust source's *unique* claim never enters — regardless of truth. But if the
same claim is independently reported by a primary-tier source, it appears
**attributed to the primary source**. So "not adopted" holds in the strong
sense — *a low-trust source is never the sole basis for any fact in the report* —
and not in the weaker sense that a fact it happened to report can never appear.

---

## C3 — Appendix 1+2 (bundled): per-stock scenario expectations, macro-driven → `expectations_checkpoint.md`

For **each of the 15 ranked stocks**: a **Best / Average / Worst** expectation,
each with **reasons**.

- **Drive scenarios from the macro view**, not price targets alone. Best/avg/worst
  are bull/base/bear scenarios whose drivers come from the M1 macro + sector
  picture, so the per-stock view is coherent with the macro view.
- **Weave, don't bolt on.** Each scenario must reference the *specific* named
  holding and its Layer-2 evidence (quality-screen outcome, ROE / leverage,
  crowding & liquidity label) and sit against the watchlist's *sector
  concentration*. Macro flows **forward** into the scenarios; the scenarios loop
  **back** to the named stocks and their screened fundamentals.
- **Analyst target dispersion is one anchor only**, not the conclusion. yfinance
  `targetHighPrice / targetMeanPrice / targetLowPrice` + `numberOfAnalystOpinions`
  may anchor the range, but they are lagging consensus and must not *be* the
  scenarios.
- **Guardrail.** Scenarios are illustrative, not predictions; "not investment
  advice" applies (see `assets/disclaimer.md`).

Required markers (checked deterministically): the words **Best**, **Average**,
**Worst** and at least one bracketed source citation.

---

## C4 — Appendix 3: over-consensus / false-theme warning + fund-style remediation → `appendix3_consensus_warning.md`

1. **Over-consensus & crowded-trade tail-risk warning** (ties to A2): crowded
   names face larger forced-selling pressure in a tail event; restate the 30–60
   day staleness caveat. Use the days-to-liquidate figures from
   `crowding_signals.json`.
2. **False-theme / homogeneity warning** (ties to A3): if the input set is
   style-homogeneous (`homogeneity.is_homogeneous` in `crowding_signals.json`),
   the consensus signal is largely tautological and uninformative — say so
   prominently.
3. **Remediation — which fund styles to add.** Using the Stage 1a style
   distribution (`homogeneity.style_distribution`), identify thin/missing style
   buckets and tell the user what to add. Concrete pattern:
   > "Your input is 8 growth/tech funds. To obtain cross-style confirmation, add
   > a value fund, a dividend/income fund, a small/mid-cap fund, and a non-US-
   > tilted global fund."
4. **Thin-US-exposure caveat (v0.32 G2)** — sits alongside the homogeneity
   warning, because it is the same false-consensus problem seen from the
   *exposure* angle rather than the *style* angle. Read
   `input_review.thin_us_exposure` in `crowding_signals.json`. Where accepted
   funds are flagged thin, say that the consensus signal partly rests on
   marginal US sleeves and should be read as weaker still — naming the funds and
   their US weight. State explicitly that their votes were **not** down-weighted,
   so the reader knows the caveat is not already priced into the score.
   **Where no accepted fund is thin, omit this caveat entirely** rather than
   printing an empty one.

A homogeneous input produces a populated Appendix 3 naming specific
under-represented styles; a diverse input produces a correspondingly milder
version.

---

## Stage 1a — reporting currency (v0.32 G1.1, required field)

Alongside `fund_name`, `asof` and the holdings table, extract the currency the
fund reports `total_aum` in, normalised to an **ISO-4217** code (`USD`, `HKD`,
`EUR`, `JPY`, …). If the factsheet does not state one, write **`currency:
null`** — do not guess, and **never default to USD**. A bare `$` is ambiguous
(USD / HKD / SGD / AUD) and a bare `¥` is ambiguous (JPY / CNY); both count as
unstated. Only USD-reporting funds enter the days-to-liquidate aggregate; the
rest are excluded and labelled, never FX-converted. See
`references/crowding_signal.md` §G1.

## Stage 1a — fund-style inference (shared dependency of A3 and Appendix 3)

At extraction, infer a coarse style label per fund — one or more of
`{value, growth, blend, income_dividend, sector_specific, small_mid_cap,
region_tilt_non_us}` — from fund-name keywords, stated benchmark, and the fund's
own top-holdings profile. Persist it as `style` on each fund record in
`holdings.json` (a single label or a list). This single inference feeds both the
style-diversity-weighted consensus (A3, in `crowding_signal.py`) and the
remediation in Appendix 3. The style vocabulary is mirrored as `_KNOWN_STYLES`
in `crowding_signal.py` — keep the two in sync.

---

## Checkpoint discipline (D4/D5)

- M1 writes `macro_checkpoint.md` **and `macro_factors.json`** (v0.31); M2 writes
  `expectations_checkpoint.md`; Appendix 3 is written to
  `appendix3_consensus_warning.md`; **Stage H1 writes
  `important_notice_checkpoint.md`** (v0.33). Stage 3a-bis writes the
  `coherence.json` side-car, which the gate checks for the overlay's invariants
  when present.
- `check_checkpoints.py <work_dir>` is the deterministic gate (required sections,
  per-sentence attribution, percent-range sanity, D3 no-per-card-bias). Reserve
  LLM review for genuine judgment: rationale quality, framing accuracy, and the
  C2 corroboration decision (the script cannot judge whether two sources are
  genuinely independent).
- `build_report.py` copies every present checkpoint `.md` to
  `/mnt/user-data/outputs` (the work dir is ephemeral). The closing chat message
  points the user there and makes no false-persistence claim.
