---
name: financial-research
description: Ranks US-listed equities, including ADRs, surfaced by 7-11 Hong Kong-distributed equity fund factsheets (PDF or one .zip). Extracts holdings with scripts, keeps only securities listed on Nasdaq, NYSE or CBOE per the SEC exchange file, screens fundamentals from SEC EDGAR with a yfinance fallback, and ranks by institutional consensus - votes from positions at or above benchmark weight, weighted by how independent the funds are - with confidence-shrunk ROE ordering names inside each consensus band. Adds a demotion-only coherence and exit-liquidity overlay, central-bank-anchored macro appendices under a two-source rule, and an English PDF watchlist of up to 15 names. Use when the user runs /financial-research or supplies several fund factsheets and asks for fund holdings analysis, cross-fund consensus, stock scoring or a watchlist. Triggers include fund analysis, holdings breakdown, analyze these fund PDFs, 股票型基金分析, 基金研究, 機構共識.
---

# Financial Research Skill v0.34

> **Every report must embed the disclaimer from `assets/disclaimer.md` verbatim (front and back).**
> v0.34 is a corrections line inside v0.4: EDGAR reads IFRS and non-USD filers, the US listing
> is checked against SEC's exchange file, ROE comes from real annual series, negative equity
> never yields a ratio, and ranking ties break by ticker. The ranking itself is unchanged.
> Version history and the reasons behind each version: `CHANGELOG.md`. Safety-first: when in
> doubt, say less and rank lower.

---

## Pipeline orchestration

> **Run the deterministic stages through the phase runner (v0.4 C6)** — one call per phase,
> a ≤ 15-line summary and the next step, never a large JSON in the conversation:
> `run_phase.py p1 <uploads.zip>` → review → `p2` → `p3` → `p4` → M1/M1b → `p5` →
> 3b/3c/M2/M3/H1 → `p6`; `run_phase.py status` shows progress. Pass the SEC email with
> `--email` or `EDGAR_CONTACT_EMAIL`; it is never stored. The table lists what each phase runs.
> **Resume (C7):** p6 saves `work_bundle.zip` to the outputs dir (`bundle.py save` does it at any
> point). When the user supplies a `work_bundle.zip`, run `bundle.py load <zip>` and continue from
> the phase it names (`state.json`) — one run can span two usage windows.

| Stage | Script / Actor | Reads | Writes |
|---|---|---|---|
| 0 | `validate_uploads.py <uploads.zip \| dir> --email <e> --out stage0_validation.json` | **one .zip** (or a dir on the CLI) + email | stdout (errors) + `stage0_validation.json` (`input.pdf_dir` = where the PDFs are); **regional advisories on stderr (G3, non-blocking)** |
| **1a-auto** | `extract_candidates.py <pdf_dir>` | the PDFs (pdfplumber; never Claude) | `candidates.json`, `candidates_summary.md` (≤ 15 lines/fund, flags), draft `holdings.json` |
| **1a-review** | Claude: reads `candidates_summary.md` only; `render_page.py` for a flagged field; `apply_review.py` to fix | summary + one page PNG per flag | `holdings.json` (**required `currency`**, **`benchmark` exactly as printed or null**, `style` for display only) |
| **1b-resolve** | `resolve_tickers.py --holdings holdings.json --email <e>` | `holdings.json`, SEC exchange file | `holdings.json` (each equity row + `ticker_resolved`, `listing_exchange`, `resolution`); rows needing review printed |
| 1b–d | `extract_holdings.py --dedupe` | `holdings.json` | `holdings.json` (row kept **iff** `resolution.status == kept`; unresolved rows fall back to the labelled legacy format check; identical share classes merged (v0.4); `disclosure_depth`/`disclosure_floor`; `currency` normalised to ISO-4217/null, `thin_us_exposure` flagged) |
| 1e | `layer1_report.py --stage0` | `holdings.json`, `stage0_validation.json` | `layer1_extraction.md` (**opens with the consolidated input review, G4**) |
| 2a | `overlap_analysis.py` | `holdings.json` | `overlap.json` |
| 2b | `fetch_fundamentals.py --email <e>` | `holdings.json` | `fundamentals.json`, `unscored_tickers.json`, `data_provenance.json` |
| 2c | (inside 2b via `providers/resolver.py`) | EDGAR + yfinance per ticker | conflict entries appended to `data_provenance.json` |
| 2d | `quality_screen.py` | `holdings.json`, `fundamentals.json`, `unscored_tickers.json` | `screen_results.json` (+ `passed_industries` census) |
| 2e | `compute_scores.py` | `fundamentals.json`, `screen_results.json` | `scores_per_stock.json` (carries `adv`/`market_cap`) |
| **2f-i** | `benchmark_weights.py --holdings --out benchmark_weights.json` | `holdings.json` (`benchmark`), yfinance proxy top holdings | `benchmark_weights.json` (proxy ETF, top-10, `b10`, or null + reason) |
| **2f-ii** | `consensus_signal.py --holdings --benchmark-weights [--vote-basis active\|presence] [--vote-floor common\|none]` | `holdings.json`, `benchmark_weights.json` | `consensus.json` (N_eff, fund weights, votes, `c_share`, bands, anchored core) |
| 2f-iii | `crowding_signal.py --overlap --holdings --fundamentals` | `overlap.json`, `holdings.json`, `fundamentals.json` | `crowding_signals.json` (days-to-liquidate **from USD-reporting funds only**, `is_exit_crowded`, `input_review`, style distribution for display) |
| 2g | `layer2_report.py --scores --consensus` | overlap, screen, fundamentals, crowding, scores, consensus | `layer2_screening.md` (consensus structure + exit liquidity + **currency exclusions** + **thin-exposure count** + **passed-but-unscored list**) |
| 3a | `build_rankings.py --scores --consensus --overlap` | `scores_per_stock.json`, `consensus.json`, `overlap.json` (display) | `rankings.json` — **sole author of rank**: order (band, −Q'', −c_share, ticker), up to 15 |
| **3a-bis-i** | `etf_relative_strength.py` | `rankings.json` (read-only), yfinance quotes | `etf_relative_strength.json` (RS vs SPY, fixed 3M/6M/12M) |
| **M1** | Claude + directed-fetch | `rankings.json` → **the ranked names' industries** (≤ 15 stocks; Fed/ECB/BoJ + official stats) | `macro_checkpoint.md` (**also the per-industry expectations-bar / sentiment-cycle facet — same scope, same two-source gate**) **+ `macro_factors.json`** (rate-path / inflation-trend fields only — the facet must NOT go here) |
| **M1b** | Claude | `rankings.json` industries + Layer-2 fundamentals | `sector_logic.json` (three universal questions per industry) |
| **3a-bis** | `coherence_audit.py --crowding crowding_signals.json` | `rankings.json` (read-only), `macro_factors.json`, `sector_logic.json`, `etf_relative_strength.json`, `crowding_signals.json` | `coherence.json` (side-car; contradictions **and exit-liquidity risks**; **`rankings.json` untouched**) |
| 3b | Claude (LLM, 3 batches of 5) | `rankings.json`, `coherence.json` | rationale cards (name each stock's contradiction / explain its divergence) |
| 3c | Claude (LLM) | all Layer 2 outputs + `rankings.json` (`n_eff_run`) | honest framing prose (HK-bias, the consensus definition, the "too small to crowd" sentence and N_eff — each stated **once**) |
| 3d | `layer3_report.py --coherence --crowding` | `rankings.json`, `coherence.json`, `crowding_signals.json`, framing, rationale | `layer3_ranked_advice.md` (v0.4 cards; benchmark-anchored core section; tier grouping applies demotions; **rank display unchanged**) |
| M2 | Claude | `rankings.json`, `macro_checkpoint.md` | `expectations_checkpoint.md` (still post-rank, scoped to the final 15) |
| M3 | Claude | `consensus.json` (N_eff, ω, marginal contributions) + `crowding_signals.json` (style dist, `input_review.thin_us_exposure`, DTL) | `appendix3_consensus_warning.md` (remediation: **replace the lowest-contribution fund with a dissimilar one**; thin-exposure caveat only when a fund is thin) |
| **H1** | Claude | `rankings.json` (read-only) + the M1 facet in `macro_checkpoint.md` | `important_notice_checkpoint.md` (per-stock expectations bar + sentiment cycle, **group-attributed**) |
| Mg | `check_checkpoints.py <work-dir>` | all checkpoints + `coherence.json` | stdout (gate; exit 1 on failure) |
| 4 | `build_report.py` | layer + appendix .md files **+ `important_notice_checkpoint.md`** | `financial_research_report.pdf` (notice rendered **after the appendices, before methodology**) + checkpoint copies (incl. `coherence.json`) in outputs |

> **Stage 2c (multi-source resolution):** Runs implicitly inside Stage 2b. For
> each ticker EDGAR and yfinance are consulted; overlapping fields are merged via
> `providers/resolver.py` (first source wins on agreement; higher-confidence wins
> on disagreement, confidence halved when diff > 20%). Conflicts → `data_provenance.json`.

> **Intake (v0.4 C2) — one .zip, and never a PDF in the conversation.** On claude.ai, ask
> the user to upload **one .zip** holding the 7–11 fund factsheet PDFs: uploaded PDFs are
> placed into the conversation context, an archive is not. On Claude Code CLI, take the path
> of the .zip (or of a folder of PDFs). `validate_uploads.py` extracts the .zip and rejects
> nested archives, paths that climb out of the archive and duplicate file names — relay its
> message. **Never Read a PDF** — not to check it, not to fix a field; the scripts read them,
> and a flagged field is checked by rendering that one page. If loose PDFs were already
> uploaded on claude.ai, run Stage 0 on the uploads folder rather than asking for a
> re-upload (the context cost is already paid), and recommend a .zip next time.

> **Stage 0 email gate (B1):** SEC requires a contact email in the EDGAR
> User-Agent; without it EDGAR returns 403. In-conversation, ask the user for a
> usable email and tell them **why** (403 without it) and the **privacy**
> position (placed ONLY in the SEC request header; not stored or sent anywhere
> else). Pass it via `--email` to `validate_uploads.py` and `fetch_fundamentals.py`
> (or set `EDGAR_CONTACT_EMAIL`). No valid email → **halt**.

> **Stage 1a (v0.4 C3) — scripts extract, Claude reviews only what is flagged.**
> 1. `extract_candidates.py <input.pdf_dir>` writes the summary and a draft `holdings.json`.
>    Read **only** `candidates_summary.md` — never a PDF, never `candidates.json` whole.
> 2. For each flagged path: `render_page.py <pdf> --page N` and look at that one PNG, then fix
>    it with `apply_review.py --set <path>=<value>` (`--delete` drops a junk row; an index equal
>    to the row count appends one). Weights as fractions (`0.031`) or with `%` (`3.1%`).
> 3. **Never guess `currency` or `benchmark`**: if the page does not print it, it stays `null`.
>    A ticker or ISIN may be added only when it is printed on the page.
> 4. Optionally set each fund's `style` (display only) from the name and benchmark shown.

> **Stage 1b-resolve (v0.34):** a holding is in scope only if SEC's exchange file lists it on
> Nasdaq, NYSE or CBOE. The ticker is checked before the ISIN (ACN, MDT, CB carry IE/CH ISINs and
> stay). A name-only row of a foreign private issuer needs an ADR marker or a US ISIN, else it is
> `ambiguous_listing`. For each row the script prints as needing review, supply a ticker or ISIN
> **only if it is printed on that factsheet page** (check with `render_page.py`) via
> `apply_review.py --set Fn.holdings[i].ticker_raw=...` (or `.isin=`), then rerun the script; never
> infer one. A row the page does not identify stays excluded, and Layer 1 lists it.
> **Alias learning loop (C4):** a name→ticker pairing you saw printed may be proposed in
> `<work>/new_aliases.json` as `{"proposals": [{"name", "ticker", "seen_in": "F3 p2", "why"}]}`.
> The run never uses that file; the maintainer reviews it with `scripts/dev/review_aliases.py`
> and commits accepted aliases to `references/ticker_aliases.json`.

> **Stage 1a required fields (v0.32 G1.1):** `fund_name`, `asof`, the holdings
> table **and `currency`** — the fund's reporting currency for `total_aum`,
> normalised to an ISO-4217 code (`USD`, `HKD`, `EUR`, `JPY`, …). If the
> factsheet does not state one, write **`currency: null`** — **do not guess and
> never default to USD.** A bare `$` or `¥` is ambiguous and counts as unstated.
> Only USD-reporting funds enter the days-to-liquidate aggregate; the rest are
> excluded (never FX-converted); their tickers carry no days-to-liquidate figure.

> **Stage 0 regional advisory (v0.32 G3):** a title matching a regional marker
> (Asia / Europe / Japan / China / EM / Latin America / India / ASEAN, plus
> bilingual equivalents) raises an **advisory only**. It never halts, never
> rejects, never enters `errors`, and never changes the exit code or the 7–11
> file-count logic — Stage 1c remains the sole authority on rejection. Relay it
> to the user so they can swap the upload before the expensive Stage 1a parse.

> **Stage 1a benchmark (v0.4 B3):** record the benchmark **exactly as printed** on the
> factsheet as `benchmark`; `null` when none is printed. **Never infer it** — a fund
> without a benchmark simply casts presence votes, and the report says so.

> **Stage 1a fund-style inference (display only since v0.4):** infer a coarse `style`
> per fund — one or more of `{value, growth, blend, income_dividend,
> sector_specific, small_mid_cap, region_tilt_non_us}` — from name keywords,
> stated benchmark, and top-holdings profile. It appears in Layer 2 and Appendix 3
> as context; **it enters no number** (I9). See `references/macro_appendix.md`.

> **Stages 2f-i/2f-ii (v0.4 consensus):** a vote is a position above the common
> floor and, where the benchmark proxy's top-10 is known, at or above benchmark
> weight capped at 10%; funds are weighted by independence. If `build_rankings.py`
> warns `few_eligible`, **tell the user** and offer to rerun 2f-ii and 3a with
> `--vote-basis presence`; never switch silently. Spec:
> `references/consensus_signal.md`.

> **Stages M1–M3 (macro subsystem):** primary-first directed-fetch, cross-source
> corroboration **hard gate** (≥2 primary-tier sources per fact), per-sentence
> attribution. **v0.4 (C5): M1 and M1b run after 3a and before 3a-bis, scoped to the
> industries in `rankings.json`** (≤ 15 stocks); the H1 facet uses the same scope. The
> ranking reads no macro input (`TestRankingReadsNoMacro`), so the rank cannot depend on
> M1, and v0.31's reason for running M1 before ranking no longer applies — while scoping
> to the ranked names costs far less retrieval than the whole post-screen universe. M1's
> sources, directed-fetch policy and two-source gate are **unchanged** — only its position
> and scope moved. Full spec: `references/macro_appendix.md`. These stages add web
> retrieval and token load — the `.md` checkpoints let a long run survive context pressure.

> **Stage H1 (v0.33 Important Notice):** a per-stock section on the two factors
> the framework structurally cannot measure — the **expectations bar** (the
> quality axis is entirely backward-looking, so a name that has beaten for eight
> quarters and one nobody expects anything from score identically on `Q`) and the
> **sentiment cycle** (no regime detection exists, by design). It sits **outside
> every layer**: it enters no score, no rank and no tier, and removing it leaves
> the report's numbers bit-for-bit identical. **Evidence is retrieved and
> corroborated at sector/theme level and narrated by attributing the stock to its
> group** — a single-stock sentiment assertion is the highest-fabrication-risk
> sentence this skill could write, and the C2 two-source hard gate is never
> relaxed here. Written **constructively, not defensively**: it is not a second
> disclaimer. Full spec: `references/important_notice.md`.

> **Stage 3a-bis (v0.31 coherence overlay):** asks whether the macro read, the
> sector operating logic and the sector-relative price action tell the same
> story. A contradiction in any pair demotes the stock **exactly one display
> tier** and must be named on its card. **Demotion-only, one tier maximum,
> `rankings.json` read-only, and deleting the stage returns the v0.3 report.**
> Missing data → "insufficient data", tier unchanged. Full spec:
> `references/coherence_overlay.md`.

---

## Error decision tree

| Symptom | Action |
|---|---|
| Stage 0: no/invalid email | Halt; print the why+privacy message; ask user to supply an email |
| Stage 0 fails (wrong PDF count, unreadable) | Stop; print guidance from `validate_uploads.py`; ask user to resubmit |
| Stage 0 rejects the .zip (nested archive, path traversal, duplicate names, not a zip) | Relay the message; ask for one .zip of the PDFs themselves. Nothing was extracted |
| Stage 0 raises a regional advisory | **Do not stop.** Relay the advisory (it names the file), then continue to Stage 1a |
| Stage 1a: factsheet does not state a reporting currency | Write `currency: null`; **never default to USD**. The fund is kept; only its AUM is excluded downstream |
| Fund reports AUM in a non-USD currency | Exclude that AUM from the days-to-liquidate aggregate and say so. **Never FX-convert**; holdings still count for consensus/overlap/style |
| Accepted fund has 20–35% US weight | Flag `thin_us_exposure`; **accept in full, do not down-weight its consensus vote**; report it in Layer 1, Layer 2 and Appendix 3 |
| Stage 1a: the script finds no holdings table (flag `Fn.holdings`) | Render that page; add the rows with `apply_review.py` from the image (append at index == row count). If the factsheet has no holdings table, leave it — Stage 1c rejects the fund |
| Stage 1a: fund has < 5 US holdings or < 20% AUM weight | Reject that fund; continue if >= 7 remain; else halt |
| Post-rejection fund count < 7 | Halt; tell user which PDFs failed and why |
| Stage 1b-resolve: SEC exchange file unavailable | Stop the listing check (the script exits 1); retry, or pass `--sec-file` with a saved copy. Never fall back to guessing from ticker formats |
| Stage 1b-resolve: rows unresolved / ambiguous | Review only the printed rows; fix a row only from what its factsheet page prints, else leave it excluded (Layer 1 discloses it) |
| EDGAR returns empty for ticker | Fall through to yfinance |
| yfinance also returns empty | Mark ticker as unscored; disclose in `layer2_screening.md` |
| Stock passes the screen with < 2 defined ROE years | `unscored_no_roe` in `scores_per_stock.json`; listed under "Passed the screen but could not be scored"; never ranked |
| No AUM / no ADV for a name | No days-to-liquidate; label it `no-liquidity-data` (no crash, never a demotion) |
| `few_eligible` warning from 3a | Tell the user; offer a `--vote-basis presence` rerun of 2f-ii + 3a. No automatic fallback |
| Benchmark not printed / not in the proxy table | `benchmark: null` or unmapped → that fund casts presence votes; Layer 1 says which |
| Macro claim has only 1 primary-tier source | Do NOT write it (C2 hard gate) |
| No sector-ETF mapping / sparse macro read | Overlay records **"insufficient data"**, tier unchanged — never treat as coherent, never demote for it |
| yfinance quote fetch fails for a sector ETF | That sector's RS is insufficient-data; other sectors still audited; no crash |
| `coherence.json` absent at 3d | Run without `--coherence`: pure rank-slice tiers (v0.3 output) |
| Overlay would demote 2 tiers / promote | Impossible by construction; if seen, the implementation is wrong — `check_checkpoints.py` fails the run |
| No corroborating sentiment/expectations evidence for a stock's group | Write the explicit not-found statement in that entry. **Never** a single-source claim, never a fabricated summary |
| The notice would need a stock-level claim to say anything | Say nothing at stock level. Attribute the stock to its group and describe the group, or state that no evidence was found |
| M1's expectations/sentiment facet is tempting to put in `macro_factors.json` | Do not. That file feeds the overlay and can move a tier; the facet stays in `macro_checkpoint.md` |
| `important_notice_checkpoint.md` absent at Stage 4 | The section is simply omitted; every rank, tier and score is unchanged |
| `check_checkpoints.py` exits 1 | Fix the flagged checkpoint before building the PDF |
| Stage 3b batch fails | Retry that batch once; else write placeholder card with data only |
| PDF assembly (Stage 4) fails | Surface the layer .md files directly; explain reportlab issue |

---

## Output contract

Directories come from `scripts/paths.py` (v0.4) — the claude.ai sandbox mounts, or
`./fr_work`, `./fr_outputs`, `./fr_uploads` under Claude Code CLI; override with
`FR_WORK_DIR`, `FR_OUTPUTS_DIR`, `FR_UPLOADS_DIR`, `EDGAR_CACHE_DIR`.

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

OUTPUTS_DIR/                       (USER-VISIBLE — downloadable)
  financial_research_report.pdf
  <all checkpoint .md files + coherence.json, copied by build_report.py — D5>
```

The closing chat message points the user to OUTPUTS_DIR for the PDF **and** the
checkpoint `.md` files; it must NOT claim the work dir persists.

---

## Key constraints (non-negotiable)

- US exchange-listed equities only: SEC's exchange file must list the ticker on Nasdaq, NYSE or CBOE (v0.34). ADRs in scope; OTC lines and home-market lines are excluded and disclosed; a non-US ISIN alone never excludes a US-listed share.
- English-only in all output files. Chat may be bilingual.
- One ranking (up to 15), three display tiers. No parallel strategies. No backtest.
- **Consensus (v0.4, DEC-1/DEC-3):** a vote is a position above the common floor and at or above benchmark weight capped at 10% (presence where no proxy exists); funds weighted by independence (`N_eff_run`); bands majority (≥ ½ of independent opinion **and** ≥ 2 voting funds) / plural / single. Zero votes → not ranked; held by most funds with no vote → **benchmark-anchored core**, listed, not ranked.
- **The ranking is an ordering, not a weighted sum (DEC-2):** (band, −Q'', −c_share, ticker). No weight is written down. LLM-inferred labels never enter it (I9).
- **The coherence overlay may only DEMOTE**, by at most **one tier per stock**, no matter how many checks fail (contradictions and the v0.4 exit-liquidity risk alike). It never promotes, never changes rank, never touches `Q''` or the consensus. `rankings.json` is **read-only** to it; its only output is `coherence.json`. Removing Stage 3a-bis must leave a runnable pipeline producing the pre-overlay report.
- **The overlay is not a scoring axis.** A macro weight cannot be calibrated (no backtest exists), so none is written.
- ETF checks are **divergence detection, never confirmation**: relative strength **vs SPY** over **fixed 3M/6M/12M** windows. Divergence yields a flag **plus a required explanation**, not an automatic penalty.
- Sector logic uses the **three universal questions** (inputs / pricing power / return on capital), instantiated per industry — never blank-filled physical-supply-chain fields on software, financial or consumer names.
- **No industry-policy or company-level supply-chain claims anywhere in the output** (deferred; company supplier relationships are not in EDGAR's structured data and are the highest fabrication risk in the proposal).
- Do not fabricate data. If EDGAR and yfinance both fail, mark unscored.
- **Quality is low-anchor shrunk:** `Q'' = c·Q + (1−c)·Q_low`, `Q_low = 10` and **must stay > 0**; never re-percentiled. `c` is `quality_confidence`, the confidence of the ROE points alone (v0.34).
- **Crowding is out of the rank (DEC-4).** Days-to-liquidate (USD-reporting holders, simultaneous exit) ≥ 10 is an overlay risk → one tier down + HIGH CROWDING on the card. Each figure labelled liquidity-inclusive / no-liquidity-data.
- **`currency` is required at Stage 1a and never defaulted.** Only `currency == "USD"` funds contribute AUM to `aggregate_position_usd`; non-USD and `null` are **excluded, never converted**. **No FX conversion may exist anywhere in the codebase** — the units are either identical or the input is set aside and labelled. There is no third path.
- **Thin US exposure (20–35% of AUM) is a warning, never a re-weighting.** Such funds are accepted in full and vote on their positions like any fund. Viability thresholds (≥5 holdings, ≥20% weight) are unchanged.
- **Stage 0 regional advisories are non-blocking**: never in `errors`, never affecting `ok`, the exit code, or the file-count logic.
- **The Important Notice changes nothing it is placed after.** It never enters `Q''`, the consensus, `rankings.json` or `coherence.json`, and is not a coherence input. Deleting `important_notice_checkpoint.md` must leave every rank, tier and score bit-for-bit identical.
- **Notice evidence is sector-level; notice wording must not exceed it.** Corroborate at sector/theme level, narrate by attributing the stock to its group. No stock-level sentiment or valuation assertion anywhere — "this group is in an elevated-expectations environment", never "this stock is overpriced". The defect in the second is not that it resembles advice, it is that it exceeds the granularity of the evidence.
- **The C2 hard gate is never relaxed for the notice.** ≥2 primary-tier sources per claim, or an explicit statement that no corroborating evidence was found. Admitting single-source claims here would make it the one low-standard region in the report — and the one most easily fabricated.
- **The notice is written constructively, not defensively.** It is not a second disclaimer; the standing verbatim disclaimer already covers that. Its argument — **Tier A means highest-ranked on the measurable dimensions, and precisely for that reason such a name is more likely already fully priced** — is stated ONCE at the section head, not per stock (same discipline as the HK-bias note).
- **Presenting sentiment evidence does not create a regime detector.** The notice must say plainly that the tool still has none.
- **No new retrieval scope for the notice.** M1's sector scope — the industries of the ranked names since v0.4 — gains a facet; per-stock retrieval is out of scope.
- Consensus is independence-weighted from the holdings themselves; stratified sampling is abandoned (sample too small; token budget) — disclose both reasons.
- Macro/expectations facts: ≥2 primary-tier sources (HARD gate), per-sentence attribution, no blacklist.
- Stage 3b: cards in 3 batches of 5, never all 15 at once.
- **HK-bias note stated ONCE** in the framing section — NOT on every card; likewise the consensus definition, the "too small to crowd" sentence and N_eff. Exit-crowded cards keep their per-card HIGH CROWDING flag; front/back disclaimer intact.
- A valid SEC contact email is required before any EDGAR fetch (B1).
- Copyright: paraphrase fetched content, never reproduce; per-sentence attribution in the macro appendices.

---

*See `references/` for methodology, crowding signal (incl. the v0.32 currency
gate), providers, quality screen, honest framing, the macro/expectations
appendices, the v0.31 coherence overlay, and the v0.33 important notice. No
formulas live in this file.*
