# Financial Research Skill — Iteration v0.3 (Spec / Iteration Prompt)

> **What this document is.** A change brief that turns the existing `financial-research` skill (v0.2) into v0.3. It is written to be handed to a future Claude session (with `skill-creator`) as the work order. It does **not** restate the whole skill — it specifies *deltas*, the *rationale* behind each non-obvious delta (so the change is not silently reverted later), and the *acceptance criteria* that define "done."
>
> **How to use it.** (1) Read the current skill in full — `SKILL.md`, all `scripts/`, all `references/`. (2) Apply Parts A–D below. (3) Preserve every item under "Invariants" and "Out of scope." (4) Validate against the acceptance criteria. (5) Keep the skill `name` unchanged (`financial-research`); this is an in-place update, not a fork.
>
> **Version line.** v1 (multi-market, claimed alpha, backtest, bilingual) → v0.2 (US-only, honestly-scoped, no backtest, English-only, EDGAR+yfinance) → **v0.3 (risk-aware consensus, confidence-penalised quality, central-bank-anchored macro appendix, conservative-by-design).**

---

## 0. Design premises locked for v0.3

These are value judgments that fix the math downstream. They are not up for re-derivation during implementation.

1. **The tool is safety-first and conservative.** Its purpose is a defensible *starting point*, biased toward what can be verified. When in doubt, it says less and ranks lower.
2. **Uncertainty is treated as a quality defect, not a neutral state.** A high-quality business whose fundamentals we cannot verify is, *for this tool's purposes*, scored down — not parked at the median. (This reverses the usual "shrink-to-mean" instinct and drives the low-anchor formula in A4.)
3. **Consensus is not alpha.** Many funds holding the same name is, by construction, pro-cyclical and crowding-prone. v0.3 keeps consensus in the score but rebuilds *what it measures* so it carries risk information, not crowd-following.
4. **Primary sources outrank secondary; one-hand data outranks news.** Macro claims are anchored in central-bank and official output, with news as interpretation, not fact.
5. **Honesty about method is part of the product.** Every selection bias, data fallback, and source-filtering rule that shapes the output is disclosed *in the report*.

---

## Part A — Core signal & composite redesign

This is the heart of v0.3. A1–A4 compose into one revised composite; they are not four isolated tweaks.

### A1. Revive `adv` and `market_cap` (currently dead data)

- **Defect.** `yfinance_provider.py` fetches `adv` (as `adv_usd = adv_val × price`) and `market_cap`; `fetch_fundamentals.py` serialises both into `fundamentals.json`; **`compute_scores.py` then drops them** when assembling the per-stock `scores` dict. They never reach `build_rankings.py`, the reports, or the screen. Both liquidity/size signals are collected and discarded.
- **Change.** Carry `adv` and `market_cap` through `compute_scores.py` into `scores_per_stock.json`, and through `build_rankings.py` into `rankings.json`, so they are available to A2 and to the reports.
- **Acceptance.** `scores_per_stock.json` and `rankings.json` each contain non-null `adv` / `market_cap` for every stock where yfinance returned them.

### A2. Crowding discount upgraded from "NAV share" to "exit-crowdedness" (days-to-liquidate)

- **Change.** Add a liquidity dimension to the crowding signal (`crowding_signal.py`, fed by revived `adv` + fund AUM from holdings):
  - `aggregate_position_$ = Σ_funds ( fund_AUM × weight_in_fund )` for the ticker.
  - `days_to_liquidate = aggregate_position_$ / ADV_usd`.
  - Fold a bounded, increasing function of `days_to_liquidate` into `crowding_raw` **before** the existing `min(·, MAX_DISCOUNT)` cap. Proposed starting form (calibrate later, in the same "starting defaults" spirit as the existing constants): a liquidity amplifier `liq = clamp(days_to_liquidate / DTL_FULL, 0, 1)` applied as `crowding_raw' = crowding_raw × (1 + LIQ_WEIGHT × liq)`, with `DTL_FULL` and `LIQ_WEIGHT` exposed as tunable constants alongside `AVG_WEIGHT_THRESHOLD` etc. Discount remains capped at `MAX_DISCOUNT = 0.60`.
- **Rationale.** The reflexivity / "everyone exits the same door" risk is position size *relative to exit liquidity*, not relative to NAV. The current signal conflates a crowded mega-cap with a crowded mid-cap; ADV is the door width. The formula deliberately assumes **simultaneous exit by all holders** — the tail-risk framing the tool is meant to surface.
- **Fallbacks (mandatory — the model must not crash on missing inputs).**
  - No `total_aum` for a fund (it is *recommended*, not required, at extraction) → cannot form `aggregate_position_$` → fall back to the current `avg_weight`-based discount.
  - No `ADV_usd` (yfinance failed; EDGAR never provides it) → fall back to the current pure-weight discount.
- **Disclosure.** Each stock's crowding figure must be labelled in the report as **liquidity-inclusive** or **NAV-only** depending on which path produced it.
- **Acceptance.** A crowded large-cap and an equally-NAV-crowded mid-cap receive materially different discounts when ADV+AUM are present; missing-data stocks degrade to the v0.2 behaviour without error and are labelled NAV-only.

### A3. Style-diversity-weighted consensus + homogeneity warning (stratification abandoned)

- **Prerequisite — Stage 1a fund-style inference.** At extraction, infer a coarse style label per fund — one or more of `{value, growth, blend, income_dividend, sector_specific, small_mid_cap, region_tilt_non_us}` — from fund name keywords, stated benchmark, and the fund's own top-holdings profile. Persist it on each fund record in `holdings.json`. This is a **shared dependency** of A3 *and* Appendix 3; build it once.
- **Change.** Weight consensus by the *style diversity* of the holders rather than raw `n_funds_holding`. A name held by funds spanning several distinct styles scores higher than a name held by the same number of single-style funds. (Concrete metric left to implementation — e.g. count of distinct holder-styles, or an entropy measure over holder-styles — but it must move cross-style agreement *up* and within-style agreement *down*.)
- **Stratified sampling is explicitly abandoned for v0.3.** Reasons, both of which must appear in the methodology disclosure:
  1. **Sample too small.** 7–11 funds cannot be stratified meaningfully; style cells would hold 1–2 funds each, so any "cross-style statistic" is itself low-N.
  2. **Token budget.** Full stratified analysis exceeds the processing budget this tool operates under.
- **Replacement = "diversity-weighted discount + homogeneity warning."** Compute a concentration measure over the inferred styles of the *input set*. If the input is style-homogeneous (e.g. ≥80% one style), raise a prominent warning that consensus in this run is largely uninformative (same-mandate funds buying the same names is tautological). This warning is the payload of Appendix 3.
- **Rationale.** "AAPL held by 9/9 funds" carries ~zero information when all nine are tech funds; the consensus is measuring the input bias. Cross-style agreement is the only version of consensus that is genuinely informative — but at this sample size we can warn about its absence, not robustly estimate its presence.
- **Acceptance.** A homogeneous (single-style) input triggers the warning and yields visibly compressed consensus contributions; a style-diverse input does not.

### A4. Low-anchor confidence shrinkage on the quality half (Q only)

- **Change.** Apply a confidence penalty to the fundamental-quality score before combining:
  - `Q'' = c · Q + (1 − c) · Q_low`, where `c = overall_confidence` for the stock and **`Q_low = 10`** (on the 0–100 percentile scale).
  - **`Q_low` MUST be > 0.** With `Q_low = 0`, the formula degenerates to `c · Q` — the *multiplicative* form that was explicitly rejected in favour of low-anchor. Preserving `Q_low > 0` is the whole point of the chosen design. `Q_low = 10` is the locked default; it may be tuned *toward* 0 for more conservatism, never to 0.
- **The penalty applies to Q only, never to C.** Rationale: Q's confidence comes from the *data source* (EDGAR ≈0.9 vs yfinance ≈0.5 — a real, stock-by-stock difference). C's "confidence" is *staleness*, which is roughly uniform within a single run (all funds drawn from the same vintage of factsheets); scaling C by it is a near-cancelling monotone transform that does not change ranking. So `composite = 0.50 · Q'' + 0.50 · C`, then sort.
- **Do NOT re-percentile `Q''`.** The entire purpose is to let confidence move a stock's *absolute* position on the scale; re-ranking into percentiles afterward would wash the penalty out.
- **Rationale (premise 2).** A stock scored entirely from low-confidence yfinance data is pulled toward "low but non-zero" (≈10), so it cannot sit mid-pack on the strength of unverifiable numbers. This systematically prefers verifiable (EDGAR-sourced) names, consistent with the existing EDGAR-primary routing and the screen's confidence floor.
- **Acceptance.** Two stocks with identical raw `Q` but different `overall_confidence` produce different `Q''`, the lower-confidence one strictly lower; an EDGAR-sourced stock is barely moved while a yfinance-only stock is pulled toward ≈10.

> **Composite, end to end (v0.3):** keep 50/50 weighting (unchanged). `C` is now style-diversity-weighted and liquidity-aware (A2/A3). `Q''` is low-anchor confidence-shrunk (A4). `composite = 0.50·Q'' + 0.50·C`; sort descending; top 15; tiers A (1–5) / B (6–10) / C (11–15) unchanged.

> **Noted caveat carried forward (quality axis out of scope this round).** ROE-only quality rewards leverage (high leverage inflates ROE), and the `D/E < 5.0` screen is only a loose gate, not part of the score; confidence-shrinkage does not fix this. A DuPont decomposition is the future direction if the quality axis is ever reopened. **Do not** change the quality metric in v0.3.

---

## Part B — EDGAR & data integrity

### B1. EDGAR User-Agent fix + Stage 0 email gate

- **Defect.** The hardcoded User-Agent `"FinancialResearchSkill-v0.2 anthropic-claude-skill"` contains no contact email. SEC requires every EDGAR request to declare a User-Agent identifying the application **and providing a contact email**; requests lacking it receive `403 Forbidden`, and generic UA strings are treated as bots and blocked.
- **Change — make the UA carry a user-supplied contact email, and gate on it at Stage 0.**
  - Add an **email gate to Stage 0**, alongside the 7–11 PDF requirement: in-conversation, require the user to supply a usable email. Validate basic format. Inject it into the EDGAR provider's User-Agent (configurable — kwarg / env var, not hardcoded). If absent or invalid → **halt** the pipeline.
  - **(a) Tell the user *why*.** State plainly: SEC requires a contact email in the request header, and omitting it causes EDGAR to return 403 — so the skill cannot fetch fundamentals without it.
  - **(b) Privacy statement.** State plainly: the email is placed **only** into the SEC request header (SEC's stated use is to contact the operator if the script causes problems); it is **not stored and not transmitted anywhere else.**
- **Keep unchanged.** The 100 ms throttle (≤10 req/s), 600-request session budget, and 1s→2s→4s exponential backoff are correct — do not alter.
- **Acceptance.** Running the skill without a supplied email halts with the why+privacy message; with an email, EDGAR requests carry `…<email>` in the UA and succeed.

---

## Part C — Macro web-retrieval layer & report appendices

v0.3 adds web retrieval to a skill that previously did none. This changes the skill's nature and runtime; treat C as a self-contained subsystem with its own checkpoint.

### C1. Macro fetch — central-bank-anchored, directed-fetch

- **Backbone (primary, all free & public, fetched by directed URL, not open search):**
  - **Fed** — FOMC statements & minutes, Summary of Economic Projections (incl. dot plot), Beige Book, semiannual Monetary Policy Report.
  - **ECB** — monetary policy decisions & statements, Economic Bulletin, Eurosystem staff macroeconomic projections, monetary policy meeting accounts.
  - **BoJ** — Outlook for Economic Activity and Prices (展望レポート), Tankan (短観), monetary policy statements.
  - Plus official statistical releases as needed.
- **Supplement (use if publicly retrievable, do not depend on):** Reuters, WSJ, BlackRock public commentary (e.g. BlackRock Investment Institute), Fitch public rating commentary. Sell-side research (Citi/JPM/Nomura/etc.) is mostly paywalled — treat as best-effort, never a prerequisite.
- **Scope the sector & demand analysis to the ranked watchlist's industries — not a generic global macro dump.** Use the `industry` buckets already on each stock (`industry_map.py`) and the per-fund industry breakdown (`aggregate_funds.py`) to determine which sectors actually appear in the top-15, then analyse the macro **and aggregate market-demand** picture *for those sectors specifically*. This honours the original Appendix-2 requirement (per-industry analysis of the selected stocks + overall market demand) and is *cheaper* than a generic global survey, because it bounds retrieval to the sectors in play.
- **Rationale.** Central-bank output *is* the macro view, and it is the most manipulation-resistant source available — which makes the appendix's backbone stronger than sell-side research, not weaker. Adding ECB completes US/EU/JP coverage.
- **Output.** A macro checkpoint `.md` (see D4) capturing the fetched primary material and its provenance.

### C2. Source integrity — primary-first + cross-source corroboration **hard gate** (no blacklist)

- **No blacklist is maintained.** Instead, integrity is enforced structurally:
  1. **Primary-first at the retrieval layer.** Use **directed-fetch** for the primary tier (known central-bank / official URLs). Reserve open `web_search` for the **secondary/news layer only**. This confines the contamination surface to the secondary layer.
  2. **Cross-source corroboration is a HARD inclusion gate, not a soft confidence discount.** Any **factual statement** in the macro/expectations appendices may be written into the report **only if corroborated by ≥2 independent sources *within the primary tier*** (central banks / official statistics / Reuters / WSJ / BlackRock / Fitch). A claim that can be traced only to low-trust platforms **cannot, by construction, obtain primary-tier corroboration → it auto-fails the gate and is not written.**
  3. **Per-sentence source attribution.** Every factual sentence in the appendices carries its source(s), so provenance is auditable.
  4. **Commentary/opinion** (non-fact) is subject to the same gate; do not adopt commentary from outside the primary tier.
  5. **Methodology disclosure.** The source-selection method — primary-first, the corroboration gate, and the fact that it structurally excludes uncorroborated low-trust material — is disclosed in the report (premise 5; a curated/filtered source policy is itself a stance and must be transparent).
- **Why a hard gate and not a blacklist.** The user's goal is *zero adoption* of contaminated narratives. A soft discount would still let an uncorroborated low-trust claim appear (merely down-weighted). The hard gate delivers true non-adoption **and** is stronger than any blacklist: it also blocks a false narrative "laundered" through a non-listed low-quality outlet, and requires maintaining no list.
- **Stated semantic boundary (implement, and surface in the disclosure).** Under the hard gate, a low-trust source's *unique* claim never enters — regardless of truth. But if that claim is *true and independently reported by a primary-tier source* (e.g. Reuters), it appears **attributed to the primary source**. So "not adopted" holds in the strong sense *"a low-trust source is never the sole basis for any fact in the report,"* and does not hold in the weaker sense *"a fact it happened to report can never appear" — because the primary corroboration, not the low-trust source, is the basis.*
- **Acceptance.** A macro claim sourced only to a single outlet is excluded; a claim appearing in two primary-tier sources is included with both attributions; the appendix shows per-sentence sources; the report's methodology section documents the gate.

### C3. Appendix 1 + 2 (bundled) — per-stock scenario expectations, macro-driven

- **Form.** For each of the 15 selected stocks: **best / average / worst expectation, each with reasons.**
- **Drive it from the macro view (scenario framing), not from price targets alone.** The best/average/worst cases are bull/base/bear scenarios whose drivers come from the Appendix-2 macro + sector picture, so the per-stock view is coherent with the macro view.
- **Integrate with the rest of the report — the macro appendix is elaborated *in connection with* the other analysis results, not as a standalone essay.** Each scenario must reference the *specific* named holding and its Layer-2 evidence (quality-screen outcome, ROE / leverage, crowding & liquidity label) and sit against the watchlist's *sector concentration*. The macro view flows **forward** into the per-stock scenarios; the per-stock scenarios loop **back** to the named stocks and their screened fundamentals — so a reader sees one woven analysis, not a macro section bolted onto a stock list.
- **Analyst target dispersion is *one anchor only*, not the conclusion.** yfinance `targetHighPrice / targetMeanPrice / targetLowPrice` + `numberOfAnalystOpinions` may anchor the range, but they are themselves lagging consensus and must not *be* the scenarios.
- **Guardrail.** Scenarios are illustrative, not predictions; the "not investment advice" framing applies (see disclaimer, unchanged).
- **Output.** An expectations checkpoint `.md` (see D4).
- **Acceptance.** Each ranked stock has a three-scenario block with named macro/sector drivers and cited sources; the sector analysis covers only industries present in the top-15; each scenario references that stock's Layer-2 screen result and fundamentals and the watchlist's sector concentration; the macro drivers trace back to the Appendix-2 fetch.

### C4. Appendix 3 — over-consensus / false-theme warning + fund-style remediation

- **Content.**
  1. **Over-consensus & crowded-trade tail-risk warning** (ties to A2: crowded names face larger forced-selling pressure in a tail event; plus the 30–60 day staleness caveat).
  2. **False-theme / homogeneity warning** (ties to A3: if the input is single-style, the consensus signal is largely tautological and uninformative).
  3. **Remediation recommendation — which fund styles to add.** Using the Stage 1a style distribution, identify thin/missing style buckets and tell the user what to add. Concrete pattern: *"Your input is 8 growth/tech funds. To obtain cross-style confirmation, add a value fund, a dividend/income fund, a small/mid-cap fund, and a non-US-tilted global fund."*
- **Acceptance.** A homogeneous input produces a populated Appendix 3 naming the specific under-represented styles; a diverse input produces a correspondingly milder version.

---

## Part D — Reporting, extraction & packaging

### D1. Hybrid PDF extraction (pdfplumber + LLM normalisation)

- **Change.** At Stage 1a, use **pdfplumber `extract_tables()`** to recover the holdings table grid, then have the LLM map columns → schema and normalise tickers/weights. Add `pdfplumber` to `requirements.txt`.
- **Rationale.** pypdf's flat text extraction mangles tables (column order, merged cells); holdings tables are exactly tabular, and pdfplumber preserves cell structure. The hybrid targets the **"text layer present but table messy"** case specifically.
- **Scope note.** Image-only PDFs remain out of scope (need OCR) and stay gated out at Stage 0; PDFs with holdings rendered as graphics are likewise unsupported.
- **Acceptance.** A factsheet whose holdings table pypdf scrambles is extracted correctly via the pdfplumber path.

### D2. Denser PDF layout

- **Change.** Stop inserting `PageBreak()` after nearly every section in `build_report.py`. Use `KeepTogether` + conditional spacing to pack content; reserve hard page breaks for major boundaries only (cover; layer transitions). Keep the 18–26pp target as a ceiling, not a floor — denser is fine.
- **Rationale.** Per-section breaks waste pages and dilute impact; `KeepTogether` prevents orphaned section titles without one-section-per-page bloat.
- **Acceptance.** No section is followed by a forced page break unless it is a major boundary; total page count drops versus v0.2 on the same data.

### D3. Bias note stated once, not per-card

- **Change.** State the HK-distribution-channel bias **once**, prominently, in the opening framing section. **Remove** the per-card repetition (`SKILL.md` currently mandates the bias note on every card, and `layer3_report.py` repeats it 15×). Update both.
- **Exceptions kept.** (i) High-crowding stocks **retain their per-card warning**. (ii) The full disclaimer still appears front and back of the PDF (unchanged). Optionally, a single one-line per-*tier* footer.
- **Acceptance.** The bias statement appears once in the framing section; ranked cards no longer repeat it; high-crowding cards still carry their warning; the front/back disclaimer is intact.

### D4. Checkpoint discipline (`.md` per stage) + surface to outputs

- **Keep & strengthen the existing pattern.** The skill already checkpoints to disk (`layer1/2/3.md`, the `.json` artifacts); this is the context-loss protection. Multi-agent decomposition is shelved (see Out of Scope), but the **per-stage `.md` checkpoint discipline is retained and extended**: the **new macro fetch** stage and the **new per-stock expectations** stage each write their own checkpoint `.md`.
- **Rationale.** v0.3 adds web retrieval, raising token load; staged checkpoints let a long run survive context pressure and remain auditable. Keep the review gate **deterministic** for now (a script checks each `.md` has the required sections and that numbers are in range); reserve LLM review for genuine judgment (rationale quality, framing accuracy, the C2 source gate).

### D5. Tell the user where the cache is — correctly (ephemerality fix)

- **Correctness issue to avoid.** The working directory (`/home/claude/work`) is **ephemeral — it resets between sessions.** Telling the user their cache "is saved locally" there is misleading.
- **Change.** **Copy the checkpoint `.md` files (all layer reports + the new macro and expectations checkpoints) to `/mnt/user-data/outputs`** — the user-visible download location — alongside the final PDF. The end-of-run chat message tells the user the intermediate `.md` files are **downloadable there**, and does **not** claim they persist in the container work dir.
- **Acceptance.** After a run, the PDF *and* the checkpoint `.md` files are present in `/mnt/user-data/outputs`; the closing message points to that location and makes no false persistence claim.

---

## Invariants (carry over from v0.2 — do not break)

- US-listed equities only; ADRs in scope; non-US primary listings dropped at Stage 1b.
- English-only in all output files (chat may be bilingual).
- One ranking, top 15, three display tiers — no parallel strategies, no backtest.
- Never fabricate data; if EDGAR and yfinance both fail, mark unscored and disclose.
- Stage 3b rationale cards generated in 3 batches of 5, never 15 at once.
- The verbatim `assets/disclaimer.md` appears front and back of the PDF and in chat.
- Composite weights remain **50 / 50**.
- Quality screen thresholds unchanged; EDGAR throttle/budget/backoff unchanged.
- Copyright discipline on all fetched content: paraphrase, do not reproduce; per-sentence attribution in the macro appendices.

## Out of scope / shelved for v0.3 (do not implement)

- **Multi-agent (main + sub-agents with LLM review gates) — shelved.** Only the `.md` checkpoint discipline survives (D4). Do **not** build explicit sub-agent decomposition or LLM-gated handoffs this round.
- **Full stratified sampling — abandoned** (A3); replaced by diversity-weighted discount + warning.
- **Quality-axis rework / DuPont decomposition — deferred**; keep ROE-5y-avg percentile as the sole quality metric.

## Locked-but-tunable defaults (decided; user retains veto)

| Parameter | Value | Note |
|---|---|---|
| Composite weights | 0.50 / 0.50 | Fixed (premise 3 reconciled by redesigning C, not the weight). |
| `Q_low` (quality low anchor) | **10** | Tunable toward 0 for more conservatism; **must stay > 0** (=0 degenerates to the rejected multiplicative form). |
| Confidence penalty target | **Q only** | Never applied to C. |
| Re-percentile `Q''` | **No** | Penalty must move absolute position. |
| Cross-source corroboration | **Hard gate, ≥2 primary-tier sources** | Not a soft discount. |
| `MAX_DISCOUNT` (crowding) | 0.60 | Unchanged from v0.2. |
| Days-to-liquidate constants (`DTL_FULL`, `LIQ_WEIGHT`) | TBD starting defaults | Expose as named constants; calibrate later, same spirit as existing crowding constants. |

---

## Updated pipeline map (v0.3 deltas marked ✚ / ✎)

| Stage | Actor / script | Change |
|---|---|---|
| 0 | `validate_uploads.py` | ✎ **+ email gate** (B1): require & validate user email; halt if missing, with why+privacy message. |
| 1a | Claude (LLM) | ✚ **fund-style inference** (A3); ✎ **pdfplumber + LLM** hybrid table extraction (D1). |
| 1b–e | `extract_holdings.py`, `layer1_report.py` | Persist style label; otherwise unchanged. ✎ checkpoint `.md` to outputs (D4/D5). |
| 2a | `overlap_analysis.py` | Unchanged. |
| 2b | `fetch_fundamentals.py` | ✎ inject email into EDGAR UA (B1); ✎ keep `adv`/`market_cap` flowing (A1). |
| 2d | `quality_screen.py` | Unchanged (thresholds invariant). |
| 2e | `compute_scores.py` | ✚ **carry `adv`/`market_cap`** into `scores_per_stock.json` (A1). |
| 2f | `crowding_signal.py` | ✚ **days-to-liquidate** in the discount, with fallbacks + NAV-only/liquidity-inclusive label (A2); ✚ **style-diversity weighting** of consensus (A3). |
| 2g | `layer2_report.py` | ✎ surface liquidity labels + homogeneity state. ✎ checkpoint `.md` to outputs. |
| 3a | `build_rankings.py` | ✚ **low-anchor confidence shrinkage on Q** (`Q_low=10`, Q only, no re-percentile) (A4); carry `adv`/`market_cap`. |
| 3b/3c/3d | Claude (LLM) + `layer3_report.py` | ✎ **bias note once** (D3); high-crowding per-card warning retained. ✎ checkpoint `.md` to outputs. |
| **M1 (new)** | Claude + directed-fetch | ✚ **macro fetch** (Fed/ECB/BoJ + official stats), primary-first, corroboration hard gate (C1/C2) → macro checkpoint `.md`. |
| **M2 (new)** | Claude | ✚ **per-stock scenario expectations** driven by M1 (C3) → expectations checkpoint `.md`. |
| 4 | `build_report.py` | ✚ Appendices 1+2 (C3), 3 (C4); ✎ denser layout (D2); ✎ source-method disclosure (C2); ✎ copy all checkpoint `.md` to `/mnt/user-data/outputs` (D5). |

## Updated PDF section order

1. Cover
2. Disclaimer (front)
3. Honest framing — **incl. the single HK-bias statement, the homogeneity warning, the stratification-abandoned + token-budget note, and the source-selection-method disclosure**
4. Executive summary
5. Layer 1 — extraction summary (with per-fund style labels)
6. Layer 2 — overlap matrix
7. Layer 2 — quality screen (pass/fail/unscored)
8. Layer 2 — data-quality summary
9. Layer 3 — ranked watchlist (cards; bias note **not** repeated; high-crowding warning kept; crowding labelled liquidity-inclusive / NAV-only)
10. Layer 3 — tier groupings
11. **Appendix 1+2 — per-stock best/avg/worst scenarios with macro/sector drivers + sources** (sector scope = the watchlist's industries; each scenario cross-referenced to the named holding's Layer-2 screen / fundamentals)
12. **Appendix 3 — over-consensus & false-theme warning + fund-style remediation**
13. Methodology disclosure (incl. confidence-shrinkage, days-to-liquidate, corroboration gate)
14. Disclaimer (back)

---

## Acceptance criteria (roll-up)

A v0.3 build is acceptable when:

1. `adv`/`market_cap` reach `rankings.json`; crowding discount differentiates a crowded large-cap from an equally-NAV-crowded mid-cap when liquidity data exists, and degrades gracefully (labelled NAV-only) when it does not.
2. Style labels are produced at 1a; a single-style input raises the homogeneity warning and compresses consensus; the methodology states both reasons stratification was abandoned.
3. `Q''` uses `Q_low=10`, is applied to Q only, is **not** re-percentiled; a yfinance-only stock is pulled toward ≈10 while an EDGAR stock is barely moved.
4. Running without an email halts with the why+privacy message; with one, the EDGAR UA carries it.
5. The macro appendix is built from directed-fetch central-bank sources; every factual sentence is corroborated by ≥2 primary-tier sources and attributed per sentence; uncorroborated single-source claims are absent; the source-selection method is disclosed.
6. Each ranked stock has a macro-driven best/avg/worst block whose sector analysis is scoped to the watchlist's industries and which cross-references that stock's Layer-2 screen/fundamentals (woven, not standalone); Appendix 3 names specific under-represented styles to add.
7. The PDF is denser than v0.2 (fewer forced breaks), states the bias note once, keeps high-crowding per-card warnings, and keeps the front/back disclaimer.
8. All checkpoint `.md` files plus the PDF land in `/mnt/user-data/outputs`; the closing chat message points there and makes no false persistence claim.

## Suggested test prompts for the iteration loop

1. **Style-homogeneous input** — 9 global *growth/tech* factsheets. Expect: homogeneity warning fires, consensus compressed, Appendix 3 recommends value/income/small-mid/non-US additions.
2. **Style-diverse input** — a mix (growth, value, dividend, a non-US-tilted global). Expect: milder warning, cross-style names rank up.
3. **Liquidity contrast** — an input whose consensus names span mega-cap and mid-cap. Expect: mid-cap crowding penalised harder via days-to-liquidate; large-cap less so.
4. **Missing-data path** — factsheets lacking AUM and a few tickers yfinance can't price. Expect: graceful fallback to NAV-only crowding, those stocks labelled accordingly, no crash.
5. **Email gate** — run without supplying an email. Expect: halt with the why+privacy message.
