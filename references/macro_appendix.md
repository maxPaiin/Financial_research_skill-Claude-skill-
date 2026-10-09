# Macro & Expectations Appendices Reference (v0.3, amended by v0.31, v0.33, v0.4 and v0.41)

This file specifies the v0.3 web-retrieval subsystem and the three report
appendices it feeds. It is a reader for Claude and humans — the macro stages
(M1, M2) are performed by Claude in-conversation, not by a script. The only
scripts involved are `check_checkpoints.py` (deterministic gate) and
`build_report.py` (renders the appendix `.md` files into the PDF).

## Contents

1. [M1 — Macro fetch (central-bank-anchored, search-first) → `macro_checkpoint.md`](#m1--macro-fetch-central-bank-anchored-search-first--macro_checkpointmd)
2. [Retrieval protocol and the source whitelist (v0.41)](#retrieval-protocol-and-the-source-whitelist-v041)
3. [C2 — Source integrity: primary-first + cross-source corroboration HARD gate](#c2--source-integrity-primary-first--cross-source-corroboration-hard-gate)
4. [C3 — Appendix 1+2 (bundled): per-stock scenario expectations, macro-driven → `expectations_checkpoint.md`](#c3--appendix-12-bundled-per-stock-scenario-expectations-macro-driven--expectations_checkpointmd)
5. [C4 — Appendix 3: over-consensus / false-theme warning + input remediation → `appendix3_consensus_warning.md`](#c4--appendix-3-over-consensus--false-theme-warning--input-remediation--appendix3_consensus_warningmd)
6. [Stage 1a — reporting currency (v0.32 G1.1, required field)](#stage-1a--reporting-currency-v032-g11-required-field)
7. [Stage 1a — fund-style inference (shared dependency of A3 and Appendix 3)](#stage-1a--fund-style-inference-shared-dependency-of-a3-and-appendix-3)
8. [Checkpoint discipline (D4/D5)](#checkpoint-discipline-d4d5)

> **v0.31 amendment (E0.2) — M1 moves earlier.** M1 now runs **after Stage 2d**
> (post-screen, pre-rank) instead of after 3a, and its sector scope is anchored
> to the **post-screen universe's industries** (`passed_industries` in
> `screen_results.json`) instead of the top-15's. Reason: the coherence overlay
> lets macro inform tiering, so macro must exist before ranking — and the top-15
> is *produced by* ranking, which makes the old anchor circular. The screened
> universe is bounded (a few dozen names across a limited set of industries), so
> the cost-control intent of the original scoping rule is preserved.
> **This is a pure sequencing move: M1's internal logic, its sources, the
> retrieval policy and the C2 hard gate below are unchanged.** M2 stays
> after ranking, scoped to the final 15.

> **v0.4 amendment (C5) — M1 moves after ranking, scoped to the ranked names.**
> M1 and M1b now run **after Stage 3a and before Stage 3a-bis**, scoped to the
> **industries present in `rankings.json`** (at most 15 stocks); the v0.33 facet uses the
> same scope. This supersedes the v0.31 position: v0.4's ranking reads no macro input at
> all (enforced by `TestRankingReadsNoMacro`), so the rank cannot depend on M1 and there is
> no longer a reason to fetch macro before ranking — and fifteen names span far fewer
> industries than the post-screen universe, so retrieval cost falls. `passed_industries`
> stays in `screen_results.json` for Layer 2's display. M1's sources, retrieval policy
> and two-source gate are unchanged.

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

> **v0.41 amendment — search first, whitelist only.** The v0.3 rule that primary pages are
> fetched from known URLs and never through search is replaced: primary pages are found by
> search and fetched only when the result is on a domain in `references/source_whitelist.json`,
> and every fetched page is logged in `sources_log.json`. See
> [Retrieval protocol and the source whitelist (v0.41)](#retrieval-protocol-and-the-source-whitelist-v041).
> Reason: the skill named no URLs, so Claude built them, and the fetch tool refuses built URLs —
> in some sessions only after a five-minute permission wait.

> **Premise carried from v0.3 §0:** primary sources outrank secondary; one-hand
> data outranks news; central-bank output *is* the macro view and is the most
> manipulation-resistant source available. Honesty about the source policy is
> part of the product.

---

## M1 — Macro fetch (central-bank-anchored, search-first) → `macro_checkpoint.md`

**Backbone (primary tier — all free & public; found by search and fetched only from
whitelisted domains, per the Retrieval protocol below):**

- **Fed** — FOMC statements & minutes, Summary of Economic Projections (incl.
  the dot plot), Beige Book, semiannual Monetary Policy Report.
- **ECB** — monetary policy decisions & statements, Economic Bulletin,
  Eurosystem staff macroeconomic projections, monetary policy meeting accounts.
- **BoJ** — Outlook for Economic Activity and Prices (展望レポート), Tankan
  (短観), monetary policy statements.
- Plus official statistical releases: BLS, BEA, US Census Bureau, Eurostat, e-Stat. The
  closed list is `references/source_whitelist.json`.

**Supplement (use only if publicly retrievable; never a prerequisite):**
Reuters, WSJ, BlackRock public commentary (e.g. BlackRock Investment Institute),
Fitch public rating commentary. Sell-side research (Citi/JPM/Nomura/…) is mostly
paywalled — best-effort only.

**Scope to the ranked names' industries — not a generic global macro dump.**
Read the `industry` of each stock in `rankings.json` (v0.4 C5: M1 runs after 3a; the
phase runner's P4 summary prints the census) to determine which sectors are actually in
play, then analyse the macro **and aggregate market-demand** picture *for those sectors
specifically*. This honours the per-industry Appendix-2 requirement and is cheaper than a
generic survey because it bounds retrieval to the sectors in play.

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

## Retrieval protocol and the source whitelist (v0.41)

`references/source_whitelist.json` is the primary tier: each institution, the domains its pages
live on, and the aliases a citation may start with. Read it before the first search of M1. Six
rules govern every web call in M1, M1b, M2 and H1:

1. **R1 — Never fetch a URL you built.** Fetch only a URL that appeared in a search result, in a
   previous fetch result or in a user message. Do not guess or assemble one, even for a
   well-known official site: the fetch tool refuses such URLs, and in some sessions it first
   waits about five minutes for a permission nobody grants (314 s measured on 2026-10-08; two
   such waits cost a test run 10.5 of its 28 minutes).
2. **R2 — Search first, with the domain in the query** — for example
   `federalreserve.gov FOMC statement September 2026` or `bls.gov CPI August 2026`. Filter the
   result list yourself; do not rely on a search-tool domain filter (it returned HTTP 400 in the
   2026-10-08 test).
3. **R3 — Fetch only whitelisted results.** Fetch a result only if its host is a whitelisted
   domain or a subdomain of one, and its path starts with the listed prefix where there is one
   (`ec.europa.eu/eurostat`). When unsure, run `scripts/source_whitelist.py check <url>`. Other
   results are never fetched and never cited; they may only suggest the next query. A syndicated
   copy of a Reuters story on another site is not Reuters.
4. **R4 — Never retry a failed fetch.** `PROVENANCE_REQUIRED`, `url_not_allowed`, HTTP
   401/403/404, a paywall or an empty page ends that URL for the run; take the next whitelisted
   result or the next query. Reuters and WSJ answered automated fetches with 401 in testing.
5. **R5 — At most three queries per fact.** When two independent whitelisted sources are not
   reached within three queries, the fact is not written (macro) or gets the explicit not-found
   statement (notice). That is the C2 outcome, not a failure.
6. **R6 — Log every fetched page** in `<work>/sources_log.json`: write it at the end of M1 and
   M1b, and append to it at the end of M2 and H1.

   ```json
   {"version": "0.41",
    "fetched": [{"stage": "M1", "url": "https://www.federalreserve.gov/...",
                 "cite_as": "Fed FOMC statement 2026-09-16"}]}
   ```

   The gate (`check_checkpoints.py`) fails the run when a checkpoint cites an institution that
   has no logged page, or when the log holds a URL off the whitelist.

The maintainer edits the whitelist between runs. Never edit it during a run to make a citation
pass.

---

## C2 — Source integrity: primary-first + cross-source corroboration HARD gate

No blacklist is maintained; a closed whitelist is (v0.41). Integrity is enforced
structurally:

1. **Whitelist-only at the retrieval layer (v0.41).** The primary tier is exactly the
   institutions in `references/source_whitelist.json`. Pages are found by search and
   fetched only when the result's URL is on a whitelisted domain (R1–R6 above). A page
   outside the list is never fetched for citation and never cited.
2. **Corroboration is a HARD inclusion gate, not a soft discount.** Any factual
   statement in the macro/expectations appendices may be written **only if
   corroborated by ≥2 independent sources within the primary tier** (the
   institutions in `references/source_whitelist.json`). A claim
   traceable only to a low-trust platform cannot obtain primary-tier
   corroboration → it auto-fails the gate and is **not written**.
3. **Per-sentence attribution.** Every factual sentence carries its source(s)
   in brackets, e.g. `... rates held at 4.25–4.50%. [Fed FOMC; Reuters]`. The
   deterministic gate (`check_checkpoints.py`) requires at least one bracketed
   citation in each macro/expectations checkpoint. Since v0.41 every source named in
   a bracket must start with an alias of a whitelisted institution (`Fed …`, `BLS …`,
   `Reuters …`) whose page is logged in `sources_log.json`; in `macro_checkpoint.md`,
   `expectations_checkpoint.md` and `important_notice_checkpoint.md` square brackets
   are reserved for citations. The same rule covers the `sources` lists in
   `macro_factors.json` and `sector_logic.json`. The run's own data — `Layer 2 …`,
   `SEC EDGAR …`, `yfinance …` — may be cited as evidence about a stock or a sector's
   fundamentals (never in the notice or `macro_factors.json`); it needs no log entry and
   never counts as one of the two primary sources.
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

## C4 — Appendix 3: over-consensus / false-theme warning + input remediation → `appendix3_consensus_warning.md`

**Inputs (v0.4 B8):** from `consensus.json` — `n_eff_run`, each fund's weight `omega` and
`marginal_contribution`; from `crowding_signals.json` — `homogeneity.style_distribution`
(display only) and `input_review.thin_us_exposure`; the days-to-liquidate figures for the
tail-risk paragraph.

1. **Over-consensus & crowded-trade tail-risk warning**: names the funds hold together face
   larger forced-selling pressure in a tail event; restate the 30–60 day staleness caveat.
   Use the days-to-liquidate figures from `crowding_signals.json` (USD-reporting holders
   only), and say plainly that seven to eleven funds cannot crowd a US large cap by
   themselves.
2. **False-theme / independence warning**: report `n_eff_run` against the number of funds.
   When N_eff is close to 1 the funds are, in effect, one opinion, and agreement among them
   carries little information — say so prominently.
3. **Remediation — which upload to change.** Name the fund with the **lowest marginal
   contribution** (it adds least independent opinion for its token cost) and advise:
   **"replace the lowest-contribution fund with a dissimilar one"** — a fund whose holdings
   overlap least with the rest. The style distribution may illustrate what "dissimilar"
   means (for example, a value or income fund in an all-growth set), but it is context, not
   a score. Concrete pattern:
   > "Your 8 funds amount to 1.4 independent opinions. F6 adds least (0.05 of an opinion):
   > replace it with a dissimilar fund — one whose top holdings overlap little with the
   > others, such as a value, dividend or small/mid-cap fund."
4. **Thin-US-exposure caveat (v0.32 G2)** — sits alongside the independence warning.
   Read `input_review.thin_us_exposure` in `crowding_signals.json`. Where accepted funds are
   flagged thin, say that the consensus partly rests on marginal US sleeves — naming the
   funds and their US weight — and that their votes count in full (a vote is about a
   position, not about exposure). **Where no accepted fund is thin, omit this caveat
   entirely** rather than printing an empty one.

An input with N_eff near 1 produces a populated Appendix 3 naming the upload to replace; a
diverse input produces a correspondingly milder version.

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
  when present. M1, M1b, M2 and H1 record every fetched page in `sources_log.json`
  (v0.41, R6).
- `check_checkpoints.py <work_dir>` is the deterministic gate (required sections,
  per-sentence attribution, percent-range sanity, D3 no-per-card-bias). Reserve
  LLM review for genuine judgment: rationale quality, framing accuracy, and the
  C2 corroboration decision (the script cannot judge whether two sources are
  genuinely independent).
- `build_report.py` copies every present checkpoint `.md` to
  `/mnt/user-data/outputs` (the work dir is ephemeral). The closing chat message
  points the user there and makes no false-persistence claim.
