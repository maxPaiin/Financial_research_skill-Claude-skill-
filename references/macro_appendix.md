# Macro & Expectations Appendices Reference (v0.3)

This file specifies the v0.3 web-retrieval subsystem and the three report
appendices it feeds. It is a reader for Claude and humans — the macro stages
(M1, M2) are performed by Claude in-conversation, not by a script. The only
scripts involved are `check_checkpoints.py` (deterministic gate) and
`build_report.py` (renders the appendix `.md` files into the PDF).

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

**Scope to the watchlist's industries — not a generic global macro dump.** Use
the `industry` buckets already on each ranked stock and the per-fund industry
breakdown to determine which sectors actually appear in the top-15, then analyse
the macro **and aggregate market-demand** picture *for those sectors
specifically*. This honours the per-industry Appendix-2 requirement and is
cheaper than a generic survey because it bounds retrieval to the sectors in play.

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

A homogeneous input produces a populated Appendix 3 naming specific
under-represented styles; a diverse input produces a correspondingly milder
version.

---

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

- M1 writes `macro_checkpoint.md`; M2 writes `expectations_checkpoint.md`;
  Appendix 3 is written to `appendix3_consensus_warning.md`.
- `check_checkpoints.py <work_dir>` is the deterministic gate (required sections,
  per-sentence attribution, percent-range sanity, D3 no-per-card-bias). Reserve
  LLM review for genuine judgment: rationale quality, framing accuracy, and the
  C2 corroboration decision (the script cannot judge whether two sources are
  genuinely independent).
- `build_report.py` copies every present checkpoint `.md` to
  `/mnt/user-data/outputs` (the work dir is ephemeral). The closing chat message
  points the user there and makes no false-persistence claim.
