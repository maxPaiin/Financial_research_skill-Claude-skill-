---
name: financial-research
description: Ranks US-listed equities, including ADRs, surfaced by 7-11 Hong Kong-distributed equity fund factsheets (PDF or one .zip). Extracts holdings with scripts, keeps only securities listed on Nasdaq, NYSE or CBOE per the SEC exchange file, screens fundamentals from SEC EDGAR with a yfinance fallback, and ranks by institutional consensus - votes from positions at or above benchmark weight, weighted by how independent the funds are - with confidence-shrunk ROE ordering names inside each consensus band. Adds a demotion-only coherence and exit-liquidity overlay, central-bank-anchored macro appendices under a two-source rule, and an English PDF watchlist of up to 15 names. Use when the user runs /financial-research or supplies several fund factsheets and asks for fund holdings analysis, cross-fund consensus, stock scoring or a watchlist. Triggers include fund analysis, holdings breakdown, analyze these fund PDFs, 股票型基金分析, 基金研究, 機構共識.
---

# Financial Research Skill v0.4

> **Every report must embed the disclaimer from `assets/disclaimer.md` verbatim (front and back).**
> v0.4 ranks the US-listed holdings of 7–11 fund factsheets by institutional consensus — votes from
> positions at or above benchmark weight, funds weighted by how independent they are — and orders
> names inside each consensus band by confidence-shrunk quality. Scripts read the factsheets and run
> every deterministic stage; Claude reviews flagged fields and writes the qualitative stages.
> Version history and the reasons for each change: `CHANGELOG.md`. Safety-first: when in doubt, say
> less and rank lower.

---

## Context budget (read first)

A run is long. The conversation should carry decisions, not data.

- **Never Read a PDF** — not to check it, not to fix a field. The scripts read the factsheets; a
  flagged field is checked by rendering that one page (`render_page.py`) and looking at the PNG.
- **Never `cat` or Read a large JSON file** (`candidates.json`, `holdings.json`,
  `fundamentals.json`, `consensus.json`, `rankings.json`, `coherence.json`). The `run_phase.py`
  summaries carry what the next step needs; if one value is missing, print only that value with a
  one-line `python -c`.
- **Load a reference file only at its stage** (table below), and only the sections named there.
  Every reference longer than 100 lines opens with a Contents list.
- **Stage 3b stays at 3 batches of 5 cards** — never all 15 at once.
- Write each Claude checkpoint to the work dir as soon as it is done. Every phase refreshes the
  resume bundle, so a run survives context pressure and the end of a usage window.

---

## Running a session

### Intake — one .zip, never a PDF in the conversation

On claude.ai, ask the user to upload **one .zip** holding the 7–11 fund factsheet PDFs: uploaded
PDFs are placed into the conversation context, an archive is not. On Claude Code CLI, take the
path of the .zip (or of a folder of PDFs). If loose PDFs were already uploaded on claude.ai, run
Stage 0 on the uploads folder rather than asking for a re-upload (the context cost is already
paid), and recommend a .zip next time.

**SEC contact email (B1).** SEC requires a contact email in the EDGAR User-Agent; without it EDGAR
returns 403. Ask the user for a usable email and tell them **why** (403 without it) and the
**privacy** position: it is placed ONLY in the SEC request header — never stored, never sent
anywhere else. Pass it with `--email` or `EDGAR_CONTACT_EMAIL`. No valid email → **halt**.

### The phase runner

Run the deterministic stages through `scripts/run_phase.py`, one call per phase. Each phase prints
at most 15 lines and ends with `Next: …` — follow it.

| Step | Command or actor | What happens |
|---|---|---|
| 1 | `run_phase.py p1 <uploads.zip>` | Stage 0 validation, scripted Stage 1a extraction |
| 2 | Claude | Stage 1a review — the flagged fields only |
| 3 | `run_phase.py p2` | US listing check, dedupe, Layer 1 (rerun after fixing a printed row) |
| 4 | `run_phase.py p3` | fundamentals, screen, scores, consensus, exit liquidity, Layer 2 |
| 5 | `run_phase.py p4` | ranking, ETF relative strength; prints the M1 scope |
| 6 | Claude | M1 + M1b for the industries p4 printed |
| 7 | `run_phase.py p5` | the coherence overlay |
| 8 | Claude | 3b cards, 3c framing, M2, M3, H1 |
| 9 | `run_phase.py p6` | Layer 3, checkpoint gate, PDF, checkpoint copies to the outputs dir |

`run_phase.py status` shows what has run and what is stale. Settings given once (`--vote-basis`,
`--vote-floor`, `--asof`) are kept in `run_config.json`; the email never is.

**Resume (C7).** Every phase refreshes `work_bundle.zip` in the outputs dir. When the user supplies
a `work_bundle.zip`, run `bundle.py load <zip>` and continue from the phase it names (`state.json`;
`run_phase.py status` confirms) — one run can span two usage windows. The bundle never carries
PDFs: if the Stage 1a review was unfinished, ask for the .zip again before rendering pages.

### Stage → reference file to read now

Every file sits one level below this one; nothing needs to be read in advance.

| Stage | Read now | Sections |
|---|---|---|
| 0, 1a, 1b | nothing — the protocols below | — |
| 1a, optional `style` | `references/macro_appendix.md` | "Stage 1a — fund-style inference" |
| 2b–2c, a provider fails | `references/providers.md` | "Conflict resolution", "EDGAR contract" |
| 2d–2e, explaining the screen | `references/quality_screen.md` | whole file (56 lines) |
| 2f, 3a, a `few_eligible` warning | `references/consensus_signal.md` | 5 vote rule, 6 bands, 7 anchored core |
| 2f-iii, exit liquidity | `references/crowding_signal.md` | "Days-to-liquidate", "The currency gate" |
| M1 | `references/macro_appendix.md` | "M1 — Macro fetch", "C2 — Source integrity" |
| M1, M1b | `references/coherence_overlay.md` | "E2.1 Macro factors", "E2.2 Sector logic" |
| 3a-bis (after p5) | `references/coherence_overlay.md` | "The verdict…", "The exit-liquidity check" |
| 3b | `references/coherence_overlay.md` | "Reporting the overlay" |
| 3c | `references/honest_framing.md` | whole file |
| M2 | `references/macro_appendix.md` | "C3 — Appendix 1+2" |
| M3 | `references/macro_appendix.md` | "C4 — Appendix 3" |
| H1 | `references/important_notice.md` | H1–H4 |
| Mg fails on the notice | `references/important_notice.md` | "What `check_checkpoints.py` enforces" |
| the user asks what the skill does or cannot do | `references/methodology.md` | "What the skill is NOT", biases |

---

## Stages

`p1`–`p6` are `run_phase.py` phases; "—" marks a Claude step between phases. All files are in
the work dir.

| Stage | Phase | Run by | Writes |
|---|---|---|---|
| 0 | p1 | `validate_uploads.py` | `stage0_validation.json` (`input.pdf_dir`); advisories on stderr |
| 1a-auto | p1 | `extract_candidates.py` | `candidates.json`, `candidates_summary.md`, draft `holdings.json` |
| 1a-review | — | Claude + `render_page.py`, `apply_review.py` | `holdings.json`, fields corrected |
| 1b-resolve | p2 | `resolve_tickers.py` | `holdings.json` + `ticker_resolved`, `listing_exchange`, `resolution` |
| 1b–d | p2 | `extract_holdings.py --dedupe` | `holdings.json`: kept rows, merged share classes, flags |
| 1e | p2 | `layer1_report.py` | `layer1_extraction.md` (opens with the input review, G4) |
| 2a | p3 | `overlap_analysis.py` | `overlap.json` |
| 2b–2c | p3 | `fetch_fundamentals.py` | `fundamentals.json`, `unscored_tickers.json`, `data_provenance.json` |
| 2d | p3 | `quality_screen.py` | `screen_results.json` (+ `passed_industries`) |
| 2e | p3 | `compute_scores.py` | `scores_per_stock.json` (`Q''`, ADV, market cap) |
| 2f-i | p3 | `benchmark_weights.py` | `benchmark_weights.json` (proxy ETF top-10, or null + reason) |
| 2f-ii | p3 | `consensus_signal.py` | `consensus.json` (N_eff, ω, votes, `c_share`, bands, anchored core) |
| 2f-iii | p3 | `crowding_signal.py` | `crowding_signals.json` (days-to-liquidate, input review) |
| 2g | p3 | `layer2_report.py` | `layer2_screening.md` |
| 3a | p4 | `build_rankings.py` | `rankings.json` — **sole author of rank**, up to 15 |
| 3a-bis-i | p4 | `etf_relative_strength.py` | `etf_relative_strength.json` (RS vs SPY, 3M/6M/12M) |
| M1 | — | Claude + directed fetch | `macro_checkpoint.md`, `macro_factors.json` |
| M1b | — | Claude | `sector_logic.json` |
| 3a-bis | p5 | `coherence_audit.py` | `coherence.json` (`rankings.json` untouched) |
| 3b | — | Claude, 3 batches of 5 | `rationale/<TICKER>.txt` |
| 3c | — | Claude | `honest_framing.txt` |
| M2 | — | Claude | `expectations_checkpoint.md` |
| M3 | — | Claude | `appendix3_consensus_warning.md` |
| H1 | — | Claude | `important_notice_checkpoint.md` |
| 3d | p6 | `layer3_report.py` | `layer3_ranked_advice.md` (tiers apply demotions; rank display unchanged) |
| Mg | p6 | `check_checkpoints.py` | the gate — exit 1 names the checkpoint to fix |
| 4 | p6 | `build_report.py` | the PDF (notice after the appendices) + checkpoint copies |

---

## Stage protocols

### Stage 0 — validation

- `validate_uploads.py` extracts the .zip and rejects nested archives, paths that climb out of the
  archive, duplicate file names and a wrong PDF count. Relay its message; nothing was extracted.
- **Regional advisory (v0.32 G3):** a title matching a regional marker (Asia, Europe, Japan, China,
  EM, Latin America, India, ASEAN, and bilingual equivalents) raises an **advisory only**. It never
  halts, never enters `errors`, never changes the exit code or the 7–11 count — Stage 1c alone
  rejects. Relay it so the user can swap the upload before the review.

### Stage 1a — scripts extract, Claude reviews only what is flagged

1. Read **only** `candidates_summary.md` (≤ 15 lines per fund) — never a PDF, never
   `candidates.json` whole.
2. For each flagged path: `render_page.py <pdf> --page N`, look at that one PNG, and fix it with
   `apply_review.py --set <path>=<value>` (`--delete` drops a junk row; an index equal to the row
   count appends one). Weights as fractions (`0.031`) or with `%` (`3.1%`).
3. **Required fields (v0.32 G1.1):** `fund_name`, `asof`, the holdings table and **`currency`** —
   the reporting currency of `total_aum` as ISO-4217 (`USD`, `HKD`, `EUR`, …). Not stated →
   **`currency: null`**. **Never guess it and never default to USD**; a bare `$` or `¥` counts as
   unstated. Only USD-reporting funds enter days-to-liquidate; the rest are excluded, never
   converted.
4. **`benchmark` exactly as printed** (v0.4 B3), `null` when none is printed. Never infer it — a
   fund without one casts presence votes, and the report says so.
5. A ticker or ISIN may be added only when it is printed on the page. The same holds for the fund's
   own `fund_isin` (the share class) and `nav_per_share` (D1): optional, but a later run's
   consensus flow matches funds and prices USD classes with them.
6. Optional: a coarse `style` per fund — one or more of `{value, growth, blend, income_dividend,
   sector_specific, small_mid_cap, region_tilt_non_us}` — from the name, the stated benchmark and
   the top holdings. **Display only; it enters no number** (I9).

### Stage 1b-resolve — the US listing test (DEC-5)

- A holding is in scope only if SEC's exchange file lists it on Nasdaq, NYSE or CBOE. The ticker is
  checked before the ISIN (ACN, MDT, CB carry IE/CH ISINs and stay). A name-only row of a foreign
  private issuer needs an ADR marker or a US ISIN, else it is `ambiguous_listing`.
- For each row p2 prints as needing review, supply a ticker or ISIN **only if it is printed on that
  factsheet page** (check with `render_page.py`) via `apply_review.py --set
  Fn.holdings[i].ticker_raw=...` (or `.isin=`), then rerun p2. Never infer one. A row the page
  does not identify stays excluded, and Layer 1 lists it.
- **Alias learning loop (C4):** a name→ticker pairing you saw printed may be proposed in
  `<work>/new_aliases.json` as `{"proposals": [{"name", "ticker", "seen_in": "F3 p2", "why"}]}`.
  The run never uses that file; the maintainer reviews it with `scripts/dev/review_aliases.py`.

### Stages 2b–2c — fundamentals

EDGAR first (true point-in-time; 10-K, 20-F, 40-F; `us-gaap`, then `ifrs-full`), yfinance as the
fallback. Fields both report are merged in `providers/resolver.py`: the first source wins on
agreement, the higher-confidence one on disagreement, with its confidence halved when they differ
by more than 20%. Conflicts go to `data_provenance.json`. Both empty → the ticker is unscored and
disclosed in Layer 2.

### Stage 2f — consensus (DEC-1 to DEC-3)

A vote is a position above the common floor and, where the benchmark proxy's top-10 is known, at or
above benchmark weight capped at 10%; funds are weighted by independence (`N_eff_run`). If p4
reports `few_eligible`, **tell the user** and offer a rerun with `run_phase.py p3 --vote-basis
presence` and `p4`. Never switch silently.

### Stages M1–M3 — the macro subsystem

- Primary-first directed fetch (Fed, ECB, BoJ, official statistics). **Hard gate: ≥ 2 primary-tier
  sources per fact**, else the fact is not written. Per-sentence attribution; paraphrase, never
  reproduce.
- **M1 and M1b run after 3a, scoped to the industries in `rankings.json`** (≤ 15 stocks; p4 prints
  them). The ranking reads no macro input (`TestRankingReadsNoMacro`), so the rank cannot depend on
  M1. Sources, fetch policy and the gate are unchanged since v0.3 — only position and scope moved
  (C5).
- M1 writes `macro_checkpoint.md` — including the per-industry expectations-bar / sentiment-cycle
  facet that H1 uses — and `macro_factors.json` (rate-path and inflation-trend fields only). **The
  facet never goes into `macro_factors.json`**: that file feeds the overlay and can move a tier.
- M1b writes `sector_logic.json`: the three universal questions (inputs / pricing power / return on
  capital) per industry — never blank-filled supply-chain fields on software, financial or
  consumer names.
- M2 (`expectations_checkpoint.md`) is post-rank, scoped to the final list. M3
  (`appendix3_consensus_warning.md`) reads `consensus.json` (N_eff, ω, marginal contributions) and
  `crowding_signals.json`; its remedy is to **replace the lowest-contribution fund with a
  dissimilar one**, and its thin-exposure caveat appears only when a fund is thin.

### Stage 3a-bis — the coherence overlay

It asks whether the macro read, the sector operating logic and the sector-relative price action
tell the same story. A contradiction in any pair, or an exit-liquidity risk (days-to-liquidate
≥ 10, DEC-4), demotes the stock **exactly one display tier**, and the card must name it.
**Demotion-only, one tier maximum, `rankings.json` read-only; deleting the stage returns the
pre-overlay report.** Missing data → "insufficient data", tier unchanged.

### Stages 3b–3c — cards and framing

- 3b: `rationale/<TICKER>.txt`, written in 3 batches of 5. Each card names its stock's
  contradiction or explains its divergence.
- 3c: `honest_framing.txt` — the HK-bias note, the consensus definition, the "too small to crowd"
  sentence and N_eff, each stated **once**, never on every card.

### Stage H1 — the Important Notice (v0.33)

A per-stock section on the two factors the framework structurally cannot measure: the
**expectations bar** (the quality axis is backward-looking, so a name that has beaten for eight
quarters and one nobody expects anything from score the same) and the **sentiment cycle** (no
regime detection exists, by design). It sits **outside every layer**: it enters no score, rank or
tier, and removing it leaves every number bit-for-bit identical. **Evidence is corroborated at
sector/theme level, and the stock is narrated by attribution to its group** — a single-stock
sentiment assertion is the highest-fabrication-risk sentence this skill could write, and the
two-source gate is never relaxed here. Written **constructively, not defensively**: it is not a
second disclaimer.

---

## Error decision tree

**Intake and extraction**
- No or invalid email → halt; give the why (403) and the privacy position; ask for an email.
- Wrong PDF count or unreadable file → stop; relay `validate_uploads.py`'s guidance; ask to resubmit.
- The .zip is rejected (nested archive, path traversal, duplicate names, not a zip) → relay the
  message; ask for one .zip of the PDFs themselves. Nothing was extracted.
- Regional advisory → **do not stop**; relay it (it names the file), then continue.
- A factsheet states no reporting currency → `currency: null`, **never USD**. The fund is kept;
  only its AUM is excluded downstream.
- No holdings table found (flag `Fn.holdings`) → render that page and add the rows with
  `apply_review.py` (index == row count appends). If the factsheet has none, leave it: Stage 1c
  rejects the fund.
- A fund has < 5 US holdings or < 20% US weight → rejected; continue if ≥ 7 remain, else halt and
  say which PDFs failed and why.
- An accepted fund has 20–35% US weight → `thin_us_exposure`: accept in full, **do not down-weight
  its vote**; report it in Layer 1, Layer 2 and Appendix 3.

**Listing and data**
- SEC exchange file unavailable → p2 stops; retry, or pass `--sec-file` with a saved copy. Never
  fall back to guessing from ticker formats.
- Rows unresolved or ambiguous → review only the printed rows; fix one only from what its page
  prints, else leave it excluded (Layer 1 discloses it).
- EDGAR empty → yfinance. Both empty → unscored, disclosed in `layer2_screening.md`.
- Passes the screen with < 2 defined ROE years → `unscored_no_roe`, listed under "Passed the
  screen but could not be scored", never ranked.
- A fund reports AUM in a non-USD currency → exclude that AUM from days-to-liquidate and say so.
  **Never FX-convert**; its holdings still count for consensus, overlap and style.
- No AUM or no ADV for a name → no days-to-liquidate; label it `no-liquidity-data` (never a
  demotion).
- Benchmark not printed or not in the proxy table → that fund casts presence votes; Layer 1 says
  which.
- `few_eligible` from 3a → tell the user; offer the `--vote-basis presence` rerun. No automatic
  fallback.

**Macro, overlay and notice**
- A macro claim has only one primary-tier source → do NOT write it (hard gate).
- No sector-ETF mapping or a sparse macro read → "insufficient data", tier unchanged — never
  treated as coherent, never a demotion.
- A sector ETF quote fails → that sector's RS is insufficient data; the others are still audited.
- `coherence.json` absent at 3d → p6 runs without it: pure rank-slice tiers.
- The overlay would demote two tiers or promote → impossible by construction; the gate fails the
  run, and the implementation is wrong.
- No corroborating sentiment or expectations evidence for a group → write the explicit not-found
  statement. Never a single-source claim, never a fabricated summary.
- The notice would need a stock-level claim → say nothing at stock level; describe the group, or
  state that no evidence was found.
- `important_notice_checkpoint.md` absent at Stage 4 → the section is omitted; nothing else changes.

**Reporting**
- `check_checkpoints.py` exits 1 → fix the checkpoint it names, then rerun p6.
- A 3b batch fails → retry it once; else write placeholder cards with data only.
- PDF assembly fails → point the user to the layer `.md` files; explain the reportlab error.

---

## Output contract

Directories come from `scripts/paths.py` — the claude.ai sandbox mounts, or `./fr_work`,
`./fr_outputs`, `./fr_uploads` under Claude Code CLI; override with `FR_WORK_DIR`,
`FR_OUTPUTS_DIR`, `FR_UPLOADS_DIR`, `EDGAR_CACHE_DIR`.

```
WORK_DIR/                          (EPHEMERAL on claude.ai — resets between sessions)
  layer1_extraction.md  layer2_screening.md  layer3_ranked_advice.md
  macro_checkpoint.md   expectations_checkpoint.md  appendix3_consensus_warning.md
  important_notice_checkpoint.md                                                      (v0.33)
  holdings.json  overlap.json  fundamentals.json  unscored_tickers.json
  data_provenance.json  screen_results.json  scores_per_stock.json
  benchmark_weights.json  consensus.json  crowding_signals.json  rankings.json        (v0.4)
  macro_factors.json  sector_logic.json  etf_relative_strength.json  coherence.json   (v0.31)
  stage0_validation.json                                                              (v0.32)
  candidates.json  candidates_summary.md  rationale/  honest_framing.txt              (v0.4)
  run_config.json  state.json                                                         (v0.4)

OUTPUTS_DIR/                       (USER-VISIBLE — downloadable)
  financial_research_report.pdf
  <all checkpoint .md files + coherence.json, copied by build_report.py — D5>
  work_bundle.zip                  (refreshed after every phase — the resume point)
```

The closing message points the user to OUTPUTS_DIR for the PDF **and** the checkpoint `.md` files;
it must NOT claim the work dir persists.

---

## Key constraints (non-negotiable)

**Changed in v0.4**
- **Consensus (DEC-1, DEC-3):** a vote is a position above the common floor and at or above
  benchmark weight capped at 10% (a presence vote where no proxy is known); funds are weighted by
  independence (`N_eff_run`); bands are majority (≥ ½ of independent opinion **and** ≥ 2 voting
  funds), plural and single. Zero votes → not ranked; held by most funds without a vote →
  **benchmark-anchored core**, listed, not ranked. **Up to 15** names; one ranking, three display
  tiers, no parallel strategies, no backtest.
- **The ranking is an ordering, not a weighted sum (DEC-2):** (band, −`Q''`, −`c_share`, ticker).
  No weight is written down. LLM-inferred labels never enter it (I9).
- **Crowding is out of the rank (DEC-4).** Days-to-liquidate (USD-reporting holders, simultaneous
  exit) ≥ 10 is an overlay risk → one tier down and HIGH CROWDING on the card. Each figure is
  labelled liquidity-inclusive or no-liquidity-data.
- **US exchange-listed equities only (DEC-5):** SEC's exchange file must list the ticker on Nasdaq,
  NYSE or CBOE. ADRs are in scope; OTC and home-market lines are excluded and disclosed; a non-US
  ISIN alone never excludes a US-listed share.
- **M1 and M1b run after 3a**, scoped to the ranked names' industries; the ranking reads no macro
  input.
- **Quality is low-anchor shrunk:** `Q'' = c·Q + (1−c)·Q_low`, `Q_low = 10` and **must stay > 0**;
  never re-percentiled. `c` is `quality_confidence`, the confidence of the ROE points alone.

**Unchanged**
- **No FX conversion anywhere in the codebase.** `currency` is required at Stage 1a and never
  defaulted; only `currency == "USD"` funds contribute AUM to `aggregate_position_usd`; non-USD
  and `null` are **excluded, never converted**. The units are identical or the input is set aside
  and labelled — there is no third path.
- **The coherence overlay may only DEMOTE**, by at most **one tier per stock** however many checks
  fail. It never promotes, never changes rank, never touches `Q''` or the consensus.
  `rankings.json` is **read-only** to it; its only output is `coherence.json`. Removing Stage
  3a-bis leaves a runnable pipeline producing the pre-overlay report. It is not a scoring axis: a
  macro weight cannot be calibrated without a backtest, so none is written.
- ETF checks are **divergence detection, never confirmation**: relative strength **vs SPY** over
  **fixed 3M/6M/12M** windows. Divergence yields a flag **plus a required explanation**, not a
  penalty.
- **No industry-policy or company-level supply-chain claims** anywhere in the output (supplier
  relationships are not in EDGAR's structured data — the highest fabrication risk).
- **Macro and expectations facts: ≥ 2 primary-tier sources (hard gate)**, per-sentence
  attribution, no blacklist. Paraphrase fetched content; never reproduce it.
- **The Important Notice changes nothing it is placed after.** It never enters `Q''`, the
  consensus, `rankings.json` or `coherence.json`, and is not a coherence input. Deleting
  `important_notice_checkpoint.md` leaves every rank, tier and score bit-for-bit identical.
- **Notice evidence is sector-level, and its wording must not exceed it** — "this group is in an
  elevated-expectations environment", never "this stock is overpriced". The two-source gate is
  never relaxed for the notice: two primary-tier sources per claim, or an explicit not-found
  statement.
- **The notice is constructive, not defensive.** Its argument — Tier A means highest-ranked on the
  measurable dimensions, and precisely for that reason more likely already fully priced — is
  stated ONCE at the section head. Presenting sentiment evidence does not create a regime
  detector; the notice says so. No new retrieval scope: M1's scope gains a facet, nothing per stock.
- **Thin US exposure (20–35% of AUM) is a warning, never a re-weighting.** Viability thresholds
  (≥ 5 US holdings, ≥ 20% US weight) are unchanged. Stage 0 regional advisories are non-blocking.
- **Stated once:** the HK-bias note, the consensus definition, the "too small to crowd" sentence
  and N_eff live in the framing, not on every card. Exit-crowded cards keep their HIGH CROWDING
  flag; the front and back disclaimer stay intact.
- English-only in every output file; chat may be bilingual. Do not fabricate data. A valid SEC
  contact email is required before any EDGAR fetch.
- Consensus comes from the holdings themselves; stratified sampling is abandoned (sample too
  small; token budget) — disclose both reasons.

---

*Formulas and their reasons live in `references/` and the scripts, not in this file.*
