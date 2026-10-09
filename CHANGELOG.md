# Changelog

Notable changes to the financial-research skill, newest first. [`README.md`](./README.md)
describes the current version; this file keeps the history and the reasons.

Corrections and additions ship as separate version lines, so a reader can tell which changes
*corrected* behaviour and which *added* it. v0.32 was a correction line, and so is v0.34,
released inside v0.4 (decision DEC-6 of the v0.4 update specification), and so is v0.41.

---

## v0.41 — search-first retrieval and an enforced source whitelist (2026-10-09)

A correction line inside v0.4: no score, rank, tier, consensus or overlay rule changes.

- **Retrieval is search-first (R1–R6, `references/macro_appendix.md`).** v0.3 told Claude to
  fetch primary sources by a known URL and never through search, but named no URL, so Claude
  built URLs. The fetch tool refuses a URL that has not appeared in the conversation — in some
  sessions only after a five-minute permission wait (314 s measured). A blind test run on seven
  real factsheets spent 17 of its 28 minutes in M1, about 10.5 of them in two such waits.
  Claude now searches with the domain in the query, fetches only results on a whitelisted
  domain, never retries a failed fetch, stops after three queries per fact, and logs every
  fetched page in `sources_log.json`.
- **The primary tier is a closed whitelist.** `references/source_whitelist.json` lists each
  institution's domains and citation aliases; the US Census Bureau closes the old "…".
  `scripts/source_whitelist.py` maps URLs and citations to institutions.
- **The gate checks names and provenance.** `check_checkpoints.py` fails a citation outside
  the whitelist, a cited institution with no logged page, and a logged URL off the whitelist.
  The run's own data (Layer 2, SEC EDGAR, yfinance) stays citable where the spec uses it, never
  in the notice or `macro_factors.json`. Before v0.41 any bracketed name passed: a test run
  cited the Bank of England 27 times.
- `sources_log.json` is copied to the outputs directory with the checkpoints, and the report's
  methodology names the whitelisted institutions.

## v0.4 — consensus signal v2 and a token-lean, portable runtime (2026-10-01)

Built from the v0.4 update specification (findings F1–F20): the consensus signal (Phase B),
the token and runtime architecture (Phase C) and the optional consensus flow (Phase D). The
corrections landed first as v0.34, below.

- **The input rule changed:** the 7–11 fund factsheets (the fund sales documents) are
  uploaded as **one `.zip`**, not as individual PDFs.

### Consensus signal v2 (Phase B)

- **A vote is a choice, not a holding (DEC-1, F4).** A fund votes for a stock it holds above
  the common disclosure floor and, where its benchmark's proxy top-10 is known, at or above
  the stock's benchmark weight capped at the 10% single-issuer limit. A position at or below
  benchmark weight is "benchmark-anchored" — no vote. The factsheet's `benchmark` is
  recorded as printed (never inferred) and mapped to a proxy ETF (`benchmark_map.py`).
- **The common vote floor (F4).** The largest smallest-disclosed weight among the funds; a
  position below it cannot vote, because not every fund could have disclosed it.
- **Funds are weighted by independence (F5).** Similarity is the cosine of the funds' US
  holdings; each fund's weight is `1 / sum of its similarities`; `N_eff_run` says how many
  independent opinions the run holds. Identical share classes of one fund are merged first.
- **Consensus rises with agreement (F1, F6).** The consensus share is the weighted share of
  opinion voting for a stock, so adding a vote can only raise it. Bands: majority (≥ ½ and at
  least two voting funds), plural, single. Style labels no longer enter it (F3, I9).
- **The ranking is an ordering, not a weighted sum (DEC-2).** (band, −Q'', −c_share, ticker);
  up to 15 names; the 50/50 composite survives only in `scripts/dev/legacy_v033.py`.
  `few_eligible` warns when fewer than five names have a vote.
- **The benchmark-anchored core (DEC-3)** — names most funds hold only at benchmark weight —
  is listed in its own section, not ranked.
- **Crowding leaves the rank (DEC-4, F2).** `crowding_signal.py` keeps only exit liquidity;
  days-to-liquidate ≥ 10 (USD-reporting holders, an uncalibrated line) is a risk check in the
  coherence overlay that demotes one tier like a contradiction.
- **Reports.** Layer 1: benchmarks, disclosure depth, the floor. Layer 2: "Consensus
  structure" and "Exit liquidity". Layer 3: the v0.4 card, the anchored-core section, an
  explicit note when the overlay empties a tier's populated slice (F19). The checkpoint gate
  requires the new sections.
- **Docs.** `references/consensus_signal.md` (new); `crowding_signal.md` retitled "Exit
  liquidity and the currency gate"; the overlay, methodology, framing and Appendix 3
  references updated.

### Token and runtime architecture (Phase C)

The goal is a run whose context holds decisions, not data (F17), and that runs the same on
claude.ai and in Claude Code CLI (F18).

- **Portable paths (C1).** `scripts/paths.py` is the only place that names a runtime
  directory: the claude.ai sandbox mounts, or `./fr_work`, `./fr_outputs`, `./fr_uploads` under
  the CLI, each overridable by an environment variable. `TestNoRuntimePathLiterals` keeps it so.
- **One .zip in (C2).** Uploaded PDFs are placed into the conversation context; an archive is
  not. `validate_uploads.py` extracts the .zip and rejects nested archives, paths that climb
  out of it and duplicate names. A folder of PDFs still works on the CLI.
- **Scripts read the factsheets (C3).** `extract_candidates.py` (pdfplumber) writes the
  candidates, a summary of at most 15 lines per fund and a draft `holdings.json`; a field it
  cannot read is null and flagged with its exact correction path. Claude reads the summary
  only, renders the one page behind a flag (`render_page.py`) and corrects it with
  `apply_review.py`. Tests build their own factsheet PDFs; no fund PDF is ever opened.
- **Alias learning loop (C4).** Name→ticker pairings seen printed on a factsheet are proposed
  in `new_aliases.json`, which the run never reads; the maintainer reviews them with
  `scripts/dev/review_aliases.py` before they reach `references/ticker_aliases.json`.
- **M1 and M1b after the ranking (C5).** The ranking reads no macro input, so M1 no longer has
  to run before it; it now covers only the ranked names' industries, which costs far less
  retrieval than the whole post-screen universe. Sources and the two-source gate are unchanged.
- **The phase runner (C6).** `run_phase.py p1`–`p6` run the deterministic stages, one call per
  phase, each printing at most 15 lines and the next step; `status` names stale phases;
  `--replay-dir` runs offline from recorded inputs. The dry run found two defects, both fixed:
  a ±100% sanity bound that rejected a real ROE (Apple, 163.9%; now ±1000%), and a local
  variable in `build_report.main()` that shadowed `paths.work_dir()`.
- **Resume bundle (C7).** After every phase, `work_bundle.zip` in the outputs directory carries
  the work directory's checkpoints and JSON — never PDFs, never the contact email — and
  `bundle.py load` continues a run in a new session, so one run can span two usage windows.
- **SKILL.md restructured (C8).** 389 lines, wrapped at 120 characters (the longest line was
  1,222), the context-budget rules first, a "Stage → reference file to read now" table one level
  deep, and a Contents list in every reference longer than 100 lines. Tests enforce all four.


### Consensus flow (Phase D)

- **Schema (D1).** Stage 1a records the fund's share-class `fund_isin` and `nav_per_share` as
  printed (C3 already extracted both); they survive the listing check and dedupe.
- **Flow between two snapshots (D2).** `consensus_flow.py --prior-holdings` (an earlier run's
  `holdings.json`, or its `work_bundle.zip`) matches funds on `fund_isin`, else on the exact
  normalised name, and takes price drift out of each weight: `w* = w_prev(1 + r_i)/(1 + R_f)`.
  `R_f` is the fund's NAV return only for a USD share class (I8); otherwise its benchmark proxy
  ETF's, otherwise SPY's, and the source is recorded. Per stock: building, unwinding, mixed or
  insufficient; names that entered or left a top-holdings list carry no sign. Wired into
  `run_phase.py p4 --prior-holdings`.
- **The overlay check (D3).** A majority-band name that the funds are unwinding is a
  contradiction — one tier down under the same cap, named on the card. Any other band or flow
  is coherent; no flow reading is insufficient data. Without the file the check does not run.
  Layer 3 states the method only on runs where it ran.
- **Deviation: the trade threshold covers both roundings.** The specification sets
  `ε_f` = half the reporting step, and so does the code. But a trade compares two rounded
  weights, so pure price drift can differ from `w*` by up to `ε_now + ε_prev·(1 + r_i)/(1 + R_f)`.
  Example: 3.049% printed as 3.0%, drifting 1.64% to 3.099% printed as 3.1%, leaves a 0.0508pp
  gap. That is above half a step but is only rounding. With a single ε, about a quarter of
  untouched positions would read as trades (two uniform rounding errors differ by more than half
  a step 25% of the time), so the specified test "pure drift produces 0 trades" could not hold.
  The threshold is therefore the two-sided bound. A 5,000-case property test shows that pure
  drift never crosses it.


### Measured (specification §9) — pending

The real-data validation needs the claude.ai usage meter and the maintainer's 2026-05-26 test
set (seven USD technology funds), so it has not been run yet. To record it here:

1. Run the `v0.33` tag end to end on the seven PDFs; note the usage meter at the start and end.
2. Run `v0.4` on the same PDFs, uploaded as one .zip; note the meter the same way.
3. Run `scripts/dev/compare_rankings.py --work-dir <dir>` twice: with the default vote basis and
   with `--vote-basis presence`.
4. Record the usage per run, the number of Read calls on PDFs (target 0), the number of fields
   Claude had to review, and the rank differences. Each rank change should be explained by
   F1–F7 or DEC-1.

`MAX_FILES` for v0.41 is decided from these measurements only (DEC-7: it stays 11 until then).
The offline dry run on generated fixtures (p1–p6, Apple through EDGAR from recorded filings)
passes and is part of the test suite. It is not a substitute for this measurement.

---

## v0.34 — corrections (2026-10-01)

Corrections only: no signal is redefined and no weight changes. What changes is which stocks
reach the ranking, and on which data.

### Fixed

- **EDGAR was never used (F14).** The ticker → CIK map was read from
  `data.sec.gov/files/company_tickers.json`, which answers HTTP 404 (checked 2026-10-01 with
  `scripts/dev/edgar_smoke.py`), so every ticker silently fell back to yfinance. The map now
  comes from `www.sec.gov/files/company_tickers_exchange.json` (ticker, CIK, issuer name,
  listing exchange), refreshed when older than 7 days.
- **IFRS and non-USD filers no longer vanish from the ranking (F7).** EDGAR reads `us-gaap`,
  then `ifrs-full`, in the issuer's reporting currency; a filing with no usable facts falls
  back to yfinance field by field; a stock that passes the screen but cannot be scored is
  listed in Layer 2 ("Passed the screen but could not be scored") with its reason instead of
  disappearing unseen. Recorded check: TSMC (20-F, IFRS, TWD) now yields five ROE years.
- **Ratios never mix units.** ROE and D/E are built only from a numerator and denominator
  in the same unit for the same period end. Ratios are dimensionless, so no conversion is
  needed — the no-FX rule holds.
- **yfinance ROE is a real multi-year series (F8)** from the annual statements, not the
  trailing value repeated five times; trailing-only data is one point.
- **Negative equity (F10)** leaves that year's ROE undefined (`roe_undefined_years`) and D/E
  undefined whenever the latest equity is ≤ 0. A loss over negative equity no longer reads as
  a positive ROE, and a negative D/E can no longer slip under the 5.0 ceiling.
- **Quality confidence (F9).** Q'' is shrunk by the confidence of the ROE points alone
  (`quality_confidence`). `overall_confidence` also averaged market cap, ADV and EV/EBITDA,
  so Q'' moved with whether unrelated yfinance fill-ins succeeded.
- **US listing (F11).** Decided by SEC's exchange file — kept only when listed on Nasdaq,
  NYSE or CBOE — instead of by the format of the ticker string. OTC lines and home-market
  lines are excluded and every dropped row is disclosed in Layer 1 with its reason. ADRs stay
  in scope, and a non-US ISIN alone never excludes a US-listed share (Accenture, Medtronic
  and Chubb carry IE/CH ISINs). Name-only rows are matched through curated aliases
  (`references/ticker_aliases.json`, English and Chinese names) and SEC issuer names; for a
  foreign private issuer the row needs an ADR marker or a US ISIN to be kept.
- **Share classes.** `BRK.B` (internal) and `BRK-B` (SEC, Yahoo) resolve to the same security
  on both providers.
- **Industry map (F12).** yfinance's "Consumer Cyclical" and "Consumer Defensive" map to
  consumer discretionary / staples; AMZN and TSLA had no sector ETF and no macro scope.
- **SEC request budget (F13).** SEC publishes a rate limit (≤ 10 requests per second), not a
  daily quota. The 600-request "daily budget" is replaced by a 10,000-request runaway guard;
  the 100 ms throttle and 429 backoff stay.
- **Skill name (F15).** The slash command is the skill's name, `/financial-research`; names
  may not contain "claude", so `/claude_skill_Financial_research` could never resolve. The
  description is 937 characters (limit 1,024).
- **Determinism (F16).** Every rank-deciding sort ends with the ticker; shuffled inputs give a
  byte-identical `rankings.json`.
- **Repository hygiene (F20).** New test modules and JSON fixtures were silently git-ignored;
  they are now committed. Claude Code CLI runtime directories are ignored.

### Deviations from the specification, and the evidence for each

The provider's choices were checked against real filings: `scripts/dev/record_fixtures.py`
recorded trimmed SEC fixtures and a concept census over 19 filers (US, IFRS, 20-F and 40-F).

- **Unit choice: the reporting currency, not "USD whenever present".** TSMC tags a USD
  convenience translation of each 20-F year (9 facts against 25 in TWD), and SAP carries one
  USD fact against 41 in EUR — "USD whenever present" left SAP one ROE year. The shared unit
  with the most facts wins; USD breaks ties.
- **Current data first.** Toyota and Sony moved from US GAAP to IFRS in 2020–21, and
  "first concept present wins" read Toyota's 2012–13 us-gaap USD series. A concept or
  taxonomy whose data ended more than two years before the request never beats a current one.
- **Dropped candidate.** `ifrs-full:NoncurrentPortionOfNoncurrentBorrowings` occurred in none
  of the 19 filers and is not a candidate; every other candidate occurs in 4–10 of them.
- **TCEHY is not in SEC's file** (Tencent is not an SEC registrant), so a bare `TCEHY` resolves
  as unresolved rather than OTC. Both are excluded; the OTC test cases use `TCEHY.PK` and
  Advantest's ADR (`ATEYY`), which SEC lists on OTC.
- **A fiscal year is reconciled only against the same fiscal year.** SEC's companyfacts lag
  some filings (TSMC's FY2025 20-F, filed 2026-04-16, was not yet in it on 2026-10-01), and
  comparing EDGAR's FY2024 with yfinance's FY2025 would log a conflict that does not exist.
- **The SKILL.md length check is a plain test**, not an expected failure: the body was already
  under 500 lines, and an expected failure that passes fails the suite.

---

## v0.33 — the Important Notice (2026-08-26)

**v0.33 — the Important Notice.** An outermost-layer addition: a per-stock
section covering the two factors the ranking framework structurally *cannot* measure —
the **expectations bar** and the **sentiment cycle** — each backed by evidence retrieved
in the existing macro subsystem, with references cited.
- **It sits outside every layer, and changes nothing.** The composite ranks; the v0.31
  overlay may demote a tier; **this notice touches neither.** It never enters `Q''`, `C`,
  the composite, `rankings.json` or `coherence.json`. Delete the section and every rank,
  tier and score is bit-for-bit identical — the same reversibility property v0.31 holds,
  stated one layer further out.
- **Why outside, rather than a score.** Both factors are genuinely unquantifiable *in this
  tool*: the backtest was removed in v0.2, so there is nothing to calibrate "is the market
  overheated" against. Inventing a number would be exactly the false precision the honest-
  framing policy exists to prevent — and a valuation tilt would systematically demote
  semiconductor/AI names, precisely the names the HK channel surfaces most. A **sourced
  notice is the only truthful form available.**
- **What the framework is blind to.** The quality axis is entirely backward-looking: a
  company that has beaten for eight straight quarters with three years of growth already in
  the price, and a company with identical ROE that nobody expects anything from, **score the
  same on `Q`**. `EV/EBITDA` does not help — it is a screen gate only, never scored, and it
  is an absolute threshold rather than a position within the stock's own history.
- **Sector-level evidence, per-stock attribution.** "The expectations bar for semiconductors
  / AI infrastructure has been raised" is corroborable in Reuters/WSJ/BlackRock/Fed material.
  "The market's expectations for AVGO specifically are too high" is not — single-stock
  sentiment assertions are the **highest-fabrication-risk content in this skill**, fluent and
  trivially invented. So the notice retrieves at group level and narrates by attributing the
  stock to its group. **The C2 two-source hard gate is never relaxed here**; where evidence
  is thin the entry says so explicitly, which is itself information.
- **Constructive, not defensive.** It is not a second disclaimer — the standing verbatim one
  already covers that. Its argument is the point: **Tier A means highest-ranked on the
  measurable dimensions, and precisely for that reason such a name is more likely already
  fully priced. The two readings must be held together.** Stated once at the section head,
  never per stock.
- **No new retrieval scope.** M1 was already bound to the post-screen universe's industries;
  v0.33 adds a *facet* to that retrieval, not a scope. Per-stock retrieval is out of scope.
- **Unchanged:** the composite, `Q''`, `C`, rank order, tiers, the v0.31 overlay, the screen,
  the input gates and the existing disclaimer.

---

## v0.32 — currency-integrity defect patch (2026-08-16)

**v0.32 — a defect patch, not a feature iteration.** It closes a currency-unit
hole that v0.3's days-to-liquidate metric silently opened, and adds two input-review
warnings the existing gates do not produce. It is kept as a separate version line so a
reader can tell which changes *added* behaviour and which *corrected* it.
- **`currency` is now a required Stage 1a field**, normalised to ISO-4217, and **`null`
  when the factsheet does not state one — never defaulted to USD.** A bare `$` is
  ambiguous (USD/HKD/SGD/AUD) and counts as unstated.
- **Only USD-reporting funds enter the days-to-liquidate aggregate.** ADV is always USD,
  so an HKD-reported AUM overstated days-to-liquidate by ~7.8× — silently, with no error
  and no flag. That matters disproportionately here: the target input is the **Hong Kong
  distribution channel**, where HKD-denominated share classes are routine.
- **Excluded, never converted.** FX conversion would need a rate source, a rate-date policy
  and a new provenance path — three new failure modes to repair a metric that already has
  a well-defined NAV-only fallback. **No FX conversion exists anywhere in the codebase.**
  An excluded fund still counts in full toward overlap, consensus and style diversity;
  only its AUM is set aside, and tickers held solely by such funds show NAV-only crowding.
- **Thin-US-exposure warning.** A global fund with 5 US holdings at 21% of AUM passes the
  viability gate, then votes in the consensus signal exactly as loudly as a 95%-US fund —
  `n_funds_holding` counts funds, not exposure. Funds at 20–35% are flagged in Layer 1,
  Layer 2 and Appendix 3 and are deliberately **not** down-weighted: re-weighting would
  alter `C`, whose definition is locked. A defect patch corrects; it does not redefine a signal.
- **Stage 0 regional advisory.** A regional fund is otherwise rejected only at Stage 1c —
  *after* the most expensive step in the pipeline. A title match now raises an advisory up
  front. **Non-blocking by design**: a keyword is not evidence, Stage 1c remains the sole
  authority on rejection, and a false advisory costs one sentence while a false rejection
  would discard a valid input.
- **One consolidated input review** at the top of `layer1_extraction.md`, so the user sees a
  single review of what they submitted rather than warnings scattered across sections.
- **Unchanged:** composite weights (50/50), `Q''`, `C`, rank order, viability thresholds
  (≥5 holdings, ≥20% weight), Stage 0 blocking behaviour, and the entire v0.31 overlay. On
  an all-USD input set the numeric output is bit-for-bit identical to v0.31.

---

## v0.31 — the coherence overlay (2026-08-06)

**v0.31 — the coherence overlay.** A bolt-on that asks one question per ranked
stock: do the **macro read**, the **sector operating logic**, and the **sector-relative price
action** tell the same story? Where they contradict each other, the stock's picture is
incoherent — and in this tool incoherence is uncertainty, which is treated as a quality
defect. Key deltas vs v0.3:
- **Demotion-only, by construction.** The overlay can move a stock **down one display tier**
  and never up. That is what makes it a bolt-on rather than a rewrite: switch it off and the
  report is exactly the v0.3 output — reversibility as a hard property, not an aspiration.
- **Rank never moves; only the tier does.** A stock ranked #3 whose macro and sector logic
  contradict each other stays at **rank #3**, shown in **Tier B**, with the contradiction named
  on its card. Rank stays a purely quantitative product of the composite; the tier carries the
  qualitative judgment, and the two stay separable — *"ranked #3, demoted to B because X
  contradicts Y"* is auditable in a way that folding macro into the score never could be.
- **Not a third scoring axis.** `0.4·Q + 0.4·C + 0.2·Macro` was rejected: with no backtest
  (removed in v0.2) the weight cannot be calibrated, and writing one down would be exactly the
  false precision this tool's honesty framing exists to prevent. **Weights stay 50/50.**
- **The macro stage moved earlier (M1: after 3a → after 2d)** and is now scoped to the
  **post-screen universe's** industries. Tiering depends on macro, so macro must exist before
  ranking — and the top-15 is *produced by* ranking, so the old anchor was circular. Pure
  sequencing move: M1's sources, directed-fetch policy and hard corroboration gate are unchanged.
- **Sector logic generalised to three universal questions** — *what constrains the inputs / how
  much pricing power / what return on capital deployed* — replacing the physical supply-chain
  triad, which produces confident nonsense on software, financial and consumer names.
- **ETF check is divergence detection, never confirmation.** Relative strength **vs SPY** over
  **fixed 3M/6M/12M** windows. Price agreeing with a thesis is not treated as evidence for it:
  momentum confirmation is pro-cyclical and consensus already is, so stacking them would point
  both signals the wrong way together in a de-rating.
- **Missing data is never a verdict.** No sector-ETF mapping or a sparse macro read yields
  **"insufficient data", tier unchanged** — it may not pass as coherence, nor be punished as a
  contradiction, which would let data gaps drive tiering.

Full spec: [`references/coherence_overlay.md`](./references/coherence_overlay.md).

---

## v0.3 — risk-aware consensus (2026-06-14)

**v0.3** — risk-aware consensus, confidence-penalised quality, central-bank-anchored
macro appendix, conservative-by-design. Key deltas vs v0.2:
- **Confidence-shrunk quality (A4).** The quality half is low-anchor shrunk: `Q'' = c·Q + (1−c)·10`.
  Low-confidence (yfinance) quality is pulled toward a low-but-non-zero anchor, so unverifiable
  numbers cannot float a stock to mid-pack. Applied to quality only; not re-percentiled.
- **Exit-crowdedness (A2).** Crowding now folds in days-to-liquidate = (Σ fund_AUM × weight) / ADV,
  labelled liquidity-inclusive or NAV-only.
- **Style-diversity-weighted consensus (A3).** Cross-style agreement outweighs same-mandate
  funds; a run-level homogeneity warning fires when the input is single-style. Stratified
  sampling is abandoned (sample too small; token budget).
- **SEC email gate (B1).** A user-supplied contact email is required and injected into the EDGAR
  User-Agent (SEC returns 403 without it).
- **Macro & expectations appendices (C).** Central-bank-anchored, primary-first, with a hard
  ≥2-primary-tier corroboration gate and per-sentence attribution.
- **Denser PDF + checkpoint copy (D).** Fewer forced page breaks; all checkpoint `.md` files are
  copied to the user-visible outputs directory.

---

## Design decisions across versions (v1 → v0.2 → v0.3 → v0.31 → v0.32 → v0.33)


| Decision        | v1                                                   | v0.2                                                 | v0.3                                                              | v0.31                                                        |
| --------------- | ---------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------ |
| Scope           | Multi-market, claimed alpha                          | US equities, honestly scoped to HK channel           | unchanged                                                         | unchanged                                                    |
| Strategies      | 3 parallel (Growth / Conservative / Risk-avoidance)  | 1 ranking, 3 display tiers                           | unchanged                                                         | 1 ranking; tiers now carry judgment, not just position       |
| Backtest        | Monthly-rebalanced with CAGR/Sharpe/MDD              | Removed (misleading given inputs)                    | unchanged (still none)                                            | still none — which is *why* the overlay carries no weight    |
| Output language | Bilingual (English + Chinese)                        | English-only                                         | unchanged                                                         | unchanged                                                    |
| Data source     | yfinance + FRED only                                 | EDGAR (conf 0.9) + yfinance (conf 0.5)               | + central-bank directed-fetch (Fed/ECB/BoJ) for macro appendix    | + yfinance quotes for sector-ETF RS (no new macro sources)   |
| Quality metric  | Continuous score (industry + growth + quality_value) | Binary screen + single ROE percentile rank           | + low-anchor confidence shrinkage `Q'' = c·Q + (1−c)·10`          | unchanged                                                    |
| Consensus       | Raw count                                            | Consensus-with-crowding (NAV-share discount)         | Style-diversity-weighted + exit-crowdedness (days-to-liquidate)   | unchanged                                                    |
| Composite       | n/a                                                  | Fixed 50/50                                          | Fixed 50/50                                                       | Fixed 50/50 — overlay is **not** a third axis                |
| Tiers           | n/a                                                  | Display slice of rank                                | Display slice of rank                                             | Rank slice, then **demotion-only** coherence adjustment      |
| Macro position  | n/a                                                  | n/a                                                  | M1 after 3a, scoped to top-15 industries                          | M1 after **2d**, scoped to the **post-screen universe**      |
| Price signal    | Momentum-ish                                         | none                                                 | none                                                              | Divergence detector only (RS vs SPY, fixed windows)          |
| EDGAR UA        | n/a                                                  | Hardcoded, no email (would 403)                      | User-supplied contact email, gated at Stage 0 (B1)               | unchanged                                                    |

**v0.32 deltas (defect patch — nothing above changes):**

| Decision | v0.31 | v0.32 |
| --- | --- | --- |
| `currency` field | in the schema, never validated or read | **required at Stage 1a**, ISO-4217, `null` when unstated, never defaulted |
| Non-USD fund AUM | silently summed into a USD-named aggregate | **excluded** from the aggregate; ticker falls back to NAV-only |
| FX conversion | n/a | **none, deliberately** — exclude and label, never convert |
| Marginal US exposure (20–35%) | invisible; votes like a 95%-US fund | flagged in Layer 1 / 2 / Appendix 3; **vote unchanged** |
| Regional fund feedback | only at Stage 1c, after the expensive parse | **Stage 0 advisory**, non-blocking; Stage 1c still decides |
| Input warnings | scattered across sections | **one consolidated input-review block** |

**v0.33 deltas (outermost-layer addition — nothing above changes):**

| Decision | v0.32 | v0.33 |
| --- | --- | --- |
| Expectations bar / sentiment cycle | invisible to the framework, and unmentioned | stated as a **measurement boundary**, with sector-level evidence and references |
| Where it sits | n/a | **outside every layer** — no score, no rank, no tier; removable with bit-for-bit identical numbers |
| Quantify it? | n/a | **no.** No backtest exists to calibrate "overheated"; a number would be false precision, and a valuation tilt would systematically demote semiconductor/AI names |
| Evidence granularity | n/a | corroborated at **sector/theme level**, narrated by attributing the stock to its group — never a stock-level sentiment claim |
| C2 hard gate | ≥2 primary-tier sources | **unchanged, and explicitly not relaxed** for the notice; thin evidence produces an explicit not-found statement |
| Retrieval scope | M1 bound to post-screen industries | **same scope, one more facet** — no per-stock retrieval |
| Register | n/a | **constructive, not a second disclaimer**; the "Tier A ≠ best entry" argument stated once at the section head |
