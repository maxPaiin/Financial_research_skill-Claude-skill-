> **Trigger keyword:** `/financial-research`
>
> The slash command is the skill's `name`, and Agent Skills names may use only lowercase
> letters, digits and hyphens and may not contain the reserved words "claude" or
> "anthropic" — so the v0.33 trigger `/claude_skill_Financial_research` could never resolve.

# Financial Research Skill v0.4

> **⚠ The input rule changed in v0.4 — upload ONE `.zip`, not individual PDFs.**
> Put the **7–11 fund sales documents** (the funds' factsheets, as PDF files) into **a single
> `.zip` archive** and upload only that archive.
> - **claude.ai:** upload the one `.zip`. Uploaded PDFs are usually placed straight into the
>   conversation context, where every page costs tokens; an archive is not, so the skill's
>   scripts read the PDFs instead and no PDF is ever read into the conversation.
> - **Claude Code CLI:** pass the path of the `.zip` (a folder of PDFs also works there).
> - The archive must hold **7–11 `.pdf` files**. Nested archives and entries that point
>   outside the archive (`../`) are rejected; macOS `__MACOSX/` metadata is ignored.
> - **中文說明：** 自 v0.4 起，請將 7–11 份基金銷售文件（基金月報／基金單張的 PDF 檔）**打包成一個
>   `.zip` 壓縮檔**後上傳，不要再逐一上傳 PDF。

> **v0.4 (current) — consensus signal v2 and a token-lean, portable runtime.** Key deltas
> vs v0.33:
> - **Scripted intake.** One `.zip` in; scripts extract each factsheet's fields and holdings
>   table, and Claude reviews only the fields the scripts flag — rendering just that page as
>   an image when needed.
> - **Consensus that rises with agreement.** A fund votes for a stock only when it holds it
>   above the common disclosure floor and, where its benchmark's top-10 is known, at or above
>   the benchmark weight (capped at the 10% single-issuer limit). Votes are weighted by how
>   independent the funds are, so share-class duplicates and same-mandate funds stop counting
>   as separate opinions. Stocks rank by consensus band (majority / plural / single), then by
>   confidence-shrunk quality — an ordering, not a weighted composite — and no LLM-inferred
>   style label enters it. Names every fund holds only at benchmark weight are listed
>   separately as benchmark-anchored core holdings.
> - **Crowding becomes an exit-liquidity risk check in the demotion-only overlay**:
>   days-to-liquidate ≥ 10 moves a stock down one display tier. Position size no longer lowers
>   a rank.
> - **US listing verified against SEC's exchange file** (Nasdaq / NYSE / CBOE). OTC lines and
>   home-market lines are excluded and disclosed; ADRs stay in scope.
> - **Corrections (tagged `v0.34`, part of v0.4):** IFRS / non-USD filers such as TSMC no
>   longer drop out of the ranking unseen; yfinance ROE is a real multi-year series rather than
>   one value repeated five times; negative equity never yields a sign-flipped ROE or D/E; ties
>   break deterministically; the slash command is `/financial-research`; SEC's request-rate
>   limit replaces a daily quota that never existed.
> - **Runs on claude.ai and in Claude Code CLI**, with a phase runner that prints short
>   summaries and a resume bundle (`work_bundle.zip`) so one run can span two usage windows.
> - **Unchanged:** 7–11 funds, US-listed equities only, no FX conversion anywhere, the
>   two-source macro gate, the Important Notice and its invariants, English-only output and
>   the verbatim disclaimer.

> **Earlier versions** — v0.33 (the Important Notice), v0.32 (currency-integrity patch),
> v0.31 (coherence overlay), v0.3 (risk-aware consensus) and the v1 → v0.33 design
> decisions — are described in [`CHANGELOG.md`](./CHANGELOG.md).

### Test Report (May 26, 2026)

On May 26, 2026, a comprehensive test of this Claude skill was performed. The input datasets and generated output reports are archived in the `Analysis inputs and results/5-26-2026_Test` directory.

**Test Configuration:**

- **Scope:** 7 funds were randomly selected from the Standard Chartered Hong Kong fund universe, filtered by a "USD x Technology" constraint.
- **Data Source:** Fund documents(Traditional Chinese) and report -> https://drive.google.com/drive/folders/1brDazbsFx1oP-Xmek4rQ4DNj-lK0lott?usp=drive_link.

**Identified Issues & Areas for Improvement:**

1. **Validation:** The initial reports generated have not yet undergone professional audit or verification by financial experts.
2. **Token Efficiency:** Significant resource consumption was observed. This test depleted over 90% of the Claude Pro (Personal) Opus 4.7 Adaptive session quota (3-hour window) and incurred an additional $0.24 in API costs. Optimizing prompt structure and processing logic to reduce token overhead is a priority.
3. **Methodological Bias:** The current sampling methodology may lead to a severe "Echo Chamber Effect." Future iterations should adopt stratified sampling to ensure broader analytical diversity.
4. **Metric Weighting:** There is an ongoing discussion regarding the role of ROE (Return on Equity). We are evaluating whether to de-emphasize ROE in favor of "Institutional Consensus Depth" as a more robust core signal.

---

A Claude skill that turns a small batch of fund prospectus PDFs into a ranked, defensibly-scoped US-equity watchlist.

**Purpose.** Hong Kong private-banking distribution channels (Standard Chartered HK, Citi HK, and similar) sell a limited set of HKMA-approved global equity funds. This skill takes 7–11 of those fund factsheets (uploaded together as one `.zip`), isolates their US-listed holdings, cross-checks fundamentals against SEC EDGAR, and produces a single ranked watchlist of the 15 highest-quality stocks the channel surfaces — with the selection bias and data limitations disclosed explicitly in every report.

**Non-goals.** It is not an alpha tool, not a backtest engine, not a portfolio constructor. Rankings reflect what HK distributors are pushing, not what the global market is doing. The output is meant as a research starting point, not a trade list.

---

## Disclaimer

> **This skill produces an AI-generated analysis. The reports it generates must not be used as investment advice.**
> All rankings and scores are derived from publicly available data and statistical models. Past performance does not guarantee future results. Data sources (SEC EDGAR, yfinance, fund prospectus PDFs) may contain errors or delays. Any investment decision is solely the user's responsibility.

The verbatim disclaimer in `assets/disclaimer.md` is embedded into every generated PDF (front and back pages) and printed in the chat response.

---

## What this skill does

Given **one `.zip` holding 7–11 HKMA-approved global fund factsheet PDFs**, the skill runs a three-layer pipeline:

1. **Layer 1 — Extraction**: validates the upload, extracts each fund's holdings, keeps only securities SEC's exchange file lists on Nasdaq, NYSE or CBOE (ADRs included; v0.34), merges identical share classes of one fund (v0.4), and deduplicates across funds.
2. **Layer 2 — Overlap & Screen**: builds a cross-fund overlap matrix, fetches fundamentals from SEC EDGAR (US GAAP and IFRS, true PIT) with a field-level yfinance fallback, applies a quality screen (PASS/FAIL), computes a fundamental quality percentile score, and computes the **consensus signal v2** (v0.4): a vote is a position above the common disclosure floor and at or above benchmark weight (capped at 10%), funds are weighted by how independent they are, and each stock gets a consensus band. It also measures **exit liquidity** (days-to-liquidate, USD-reporting holders only).
3. **Layer 3 — Ranking & Advice**: orders eligible stocks by **consensus band, then confidence-shrunk quality** — an ordering, not a weighted sum — ranks up to 15 into Tier A/B/C, lists the benchmark-anchored core separately, and generates per-stock rationale cards with honest framing (HK-bias stated once).
4. **Coherence overlay (v0.31, v0.4)**: audits each ranked stock for agreement between the macro read, the sector operating logic and sector-ETF relative strength — and, since v0.4, for exit liquidity — and **demotes** (never promotes) the display tier by at most one level where a pair contradicts or the stock is exit-crowded, naming the reason on the card. Writes a side-car `coherence.json`; `rankings.json` is read-only to it.
4b. **Input review (v0.32)**: reports what the submitted set actually is — reporting currency per fund and which funds that excludes from the exit-liquidity aggregate, funds whose US sleeve is thin, Stage 0 regional advisories, rejections, and the style distribution — as one block rather than warnings scattered across sections.
5. **Macro appendices (v0.3)**: central-bank-anchored macro/sector view, per-stock best/avg/worst scenarios, and an over-consensus / fund-style remediation appendix — all under a hard ≥2-primary-tier source-corroboration gate.
6. **Important Notice (v0.33)**: a per-stock section on the **expectations bar** and the **sentiment cycle** — the two factors the ranking structurally cannot measure. Evidence is corroborated at sector/theme level and narrated by attributing the stock to its group; where two primary-tier sources do not exist, the entry says so explicitly. It enters no score, rank or tier, and is placed after the appendices and before the methodology.

**Output**: the layered `.md` checkpoints, the `coherence.json` audit trail, the Important Notice checkpoint, and a single English-only PDF report, all copied to the user-visible outputs directory.

---

## What this skill is NOT

- **Not an alpha tool.** Rankings reflect HK distribution-channel preferences, not the global market.
- **Not a portfolio constructor.** Output is a ranked watchlist; no allocation weights.
- **Not a backtest engine.** Backtesting was removed in v0.2 (it produced misleading results given the small, biased input set).
- **Not a bilingual tool.** All output files are English-only.
- **Not a three-strategies tool.** One ranking, three display tiers.
- **Not a macro forecaster (v0.31).** The macro readings are directional summaries of central-bank material, not predictions, and the coherence verdict is a qualitative judgment — deliberately unweighted, with no calibrated model behind it.
- **Not a price-confirmation tool (v0.31).** ETF relative strength is context, never confirmation; sector ETFs carry their own crowding. The overlay can only lower confidence in a name, never raise it.
- **Not a currency converter (v0.32).** Non-USD fund AUM is excluded from the exit-liquidity aggregate and labelled, never FX-converted. Exclusion has one failure mode the report can state; conversion would add three it could not.
- **Not an exposure-weighted consensus (v0.32).** A vote is about a position, not about how much of the fund is in US equity. Funds with a thin US sleeve are flagged, not down-weighted.
- **Not a crowding score (v0.4).** Seven to eleven Hong Kong–distributed funds are too small to crowd US large caps, and global crowding cannot be measured from factsheets. Days-to-liquidate shows what these holders alone would take to unwind, as an overlay risk — never as a penalty on position size.
- **Not a regime detector (v0.33).** The framework cannot tell you whether the market is currently overheated, and adding sourced sentiment evidence did not change that. The backtest was removed in v0.2, so there is nothing to calibrate such a judgment against — the notice states the boundary rather than papering over it with a number.
- **Not a stock-level sentiment analyst (v0.33).** "The expectations bar for semiconductors / AI infrastructure has been raised" is corroborable; "the market's expectations for AVGO specifically are too high" is not. The notice describes the *environment a group is in*, never a verdict on a stock's price — the defect in the latter is not that it resembles advice, it is that it exceeds the granularity of the evidence.
- **Not a supply-chain mapper.** Industry-policy and company-level supplier claims are deliberately out of scope — those relationships are absent from EDGAR's structured data and are the highest fabrication risk in the design.

---

## Input requirements

The skill is gated at three levels. If any gate fails, the pipeline halts and the user is told exactly which inputs caused the failure so they can replace them.

### Level 1 — File-level (Stage 0, `validate_uploads.py`)

Every uploaded PDF is checked before any LLM parsing begins:


| Check            | Requirement                                                                                                                                                                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Upload format (v0.4) | **One `.zip` archive** holding the PDFs (claude.ai). On Claude Code CLI a folder path also works. Nested archives and entries that point outside the archive are rejected; macOS `__MACOSX/` metadata is ignored. |
| File count       | **7–11** `.pdf` files inside the archive (or folder), inclusive.                                                                                                                                                                                               |
| Parseable        | Each PDF must open with`pypdf` and contain at least one page.                                                                                                                                                                                                   |
| Extractable text | The first 10 pages combined must yield non-empty text. Image-only scans fail here.                                                                                                                                                                              |
| Holdings keyword | Each PDF must contain at least one of:`holdings`, `portfolio`, `top holdings`, `portfolio composition`. Bilingual HK factsheets often include Chinese equivalents as well — the validator accepts those too; see `validate_uploads.py` for the canonical list. |
| Reporting date   | Each PDF must contain a recognizable date. Supported formats include`2025-03-31`, `31/03/2025`, `Q1 2025`, `FY 2024`, `H1 2025`, `March 31, 2025`, `31 March 2025`, `March 2025`.                                                                               |
| Regional advisory (v0.32) | **Not a check.** If the fund's *title* names a region (Asia, Europe, Japan, China, EM, Latin America, India, ASEAN, or a bilingual equivalent), Stage 0 prints an advisory naming the file — that fund may hold fewer than 5 US-listed equities and be rejected at Stage 1c, after the expensive parse. It does **not** halt, reject, or change the exit code or file count. Matching is restricted to the title (percentage-bearing lines are ignored) so a global fund's country-breakdown table does not trip it. |

### Level 2 — Per-fund content (Stage 1a, scripted extraction + review)

v0.4: scripts extract each factsheet's fields and holdings table into `holdings.json`, one record per fund; Claude reviews only the fields the scripts flag as missing or low-confidence and never reads a PDF into the conversation. For that to succeed, each PDF must surface the following:


| Field                   | Required?   | Why it matters                                                                               |
| ----------------------- | ----------- | -------------------------------------------------------------------------------------------- |
| Fund name               | yes         | Identifies the fund in every downstream report.                                              |
| Issuer                  | recommended | Shown in Layer 1 / 2 summaries.                                                              |
| Reporting date (`asof`) | yes         | Per-fund snapshot date; appears in Layer 1 and PIT tracking.                                 |
| **Reporting currency**  | **yes (v0.32)** | ISO-4217 code for `total_aum` (`USD`, `HKD`, `EUR`, `JPY`, …). **`null` if the factsheet does not state one — never defaulted to USD**; a bare `$` is ambiguous and counts as unstated. Only USD-reporting funds enter the days-to-liquidate aggregate; the rest are excluded (never FX-converted), so a ticker held only by them has no days-to-liquidate figure. |
| Total AUM               | recommended | Activates the "US holdings ≥ 20% of AUM" viability check; without AUM the check is skipped. |
| Holdings table          | yes         | The core data feeding every downstream stage.                                                |

Each row of the **holdings table** must include:

- `ticker` (raw form is fine — `AAPL`, `BRK.B`, `BAC.PB`, `0700.HK` are all accepted and normalized in Stage 1b).
- `weight` (percentage of NAV / AUM).
- `name` of the holding (used by the non-equity filter and displayed in reports).
- `ISIN` (optional — used as a fallback for US-listing detection when the ticker format is non-standard).

### Level 3 — Fund viability and universe gate (Stage 1b–d, `extract_holdings.py --dedupe`)

After Stage 1a, each fund's holdings are filtered to US-listed equities (ADRs included; non-US suffixes such as `.HK`, `.T`, `.L`, `.SS` are dropped; cash, bonds, ETFs, warrants, money-market instruments are dropped via a word-boundary keyword filter). Each fund must then satisfy:


| Check            | Requirement                                                           |
| ---------------- | --------------------------------------------------------------------- |
| US equity count  | ≥**5** US-listed holdings remaining after filtering.                 |
| US equity weight | If AUM was extracted, the kept holdings must sum to ≥**20%** of AUM. |

Funds that fail are rejected, but the run continues — **as long as at least 7 funds survive**. If post-rejection count drops below 7, the pipeline halts with a message naming the failed PDFs.

**Marginal passes are flagged, not rejected (v0.32).** A fund whose US equity lands between
**20% and 35%** of AUM clears the gate but carries a `thin_us_exposure` flag: its consensus
vote counts exactly as much as a 95%-US fund's, because the signal counts funds rather than
exposure. The thresholds above are unchanged and the vote is **not** down-weighted — the flag
is surfaced in Layer 1, Layer 2 and Appendix 3 so the reader can discount the consensus
themselves.

### Examples

**Works (typical factsheets the skill is built for):**

- Monthly or quarterly factsheets from HKMA-approved global equity funds — HSBC, Eastspring, JPMorgan, Allianz Global Investors, Schroders, Pictet, Fidelity, and similar.
- Documents that explicitly disclose at least top-10 holdings with ticker, weight, and company name.
- Standard Chartered HK / Citi HK private-banking style fund profile PDFs.

**Does not work:**

- Image-only scanned PDFs (no extractable text layer).
- Marketing brochures, annual letters, or commentaries without a holdings table.
- Pure Asia or Europe regional funds (US holdings < 5 after filtering → rejected).
- Pure bond funds or balanced / mixed-asset funds (non-equity filter strips most rows).
- ETF monthly reports (an ETF is itself flagged as non-equity in this pipeline).
- Annual reports with holdings disclosure older than 12 months from `asof` — Stage 2 fundamentals will struggle to match.

---

## When the skill triggers


| Trigger                                                                                                                                            |
| -------------------------------------------------------------------------------------------------------------------------------------------------- |
| User runs `/financial-research`.                                                                                                                   |
| User uploads one `.zip` of 7–11 fund factsheet PDFs and asks for analysis.                                                                       |
| Phrases:*fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, fund prospectus analysis*, "analyze these fund PDFs". |

If fewer than 7 PDFs are supplied, validation stops the pipeline and asks the user to resubmit.

---

## Pipeline overview


| Layer                       | Stages       | Key scripts                                                                                                                        |
| --------------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Layer 1 — Extraction       | 0–1e        | `validate_uploads.py`, `resolve_tickers.py`, `extract_holdings.py`, `layer1_report.py`                                             |
| Layer 2 — Overlap & Screen | 2a–2g       | `overlap_analysis.py`, `providers/registry.py`, `quality_screen.py`, `compute_scores.py`, `benchmark_weights.py`, `consensus_signal.py`, `crowding_signal.py`, `layer2_report.py` |
| Macro (v0.31: after 2d)     | M1, M1b      | Claude directed-fetch → `macro_checkpoint.md` (v0.33: **+ expectations/sentiment facet**) + `macro_factors.json`, `sector_logic.json` |
| Important Notice (v0.33)    | H1           | Claude → `important_notice_checkpoint.md` — outside every scoring layer; rendered after the appendices, before methodology         |
| Layer 3 — Ranking & Advice | 3a–3d + PDF | `build_rankings.py`, `etf_relative_strength.py`, `coherence_audit.py`, `layer3_report.py`, `build_report.py`                       |

Full orchestration logic and error recovery rules: [`SKILL.md`](./SKILL.md).

### Where the overlay sits (v0.31)

```
2d quality_screen.py ──► screen_results.json (+ passed_industries)
      │
      ├─► M1  Claude directed-fetch ──► macro_checkpoint.md + macro_factors.json
      └─► M1b Claude ────────────────► sector_logic.json
                                              │
2e–2f ──► 3a build_rankings.py ──► rankings.json ──┐   (sole author of rank)
                                              │    │   READ-ONLY below this line
         etf_relative_strength.py + crowding_signals.json (v0.4: exit liquidity)
                                              ▼    ▼
                       3a-bis coherence_audit.py ──► coherence.json   (side-car)
                                              │
      3b/3d cards + layer3_report.py ◄────────┘   tier may drop one level; rank never changes
```

Delete `coherence_audit.py` and its side-car and the pipeline still runs, producing the
pre-overlay report. If removing it breaks anything downstream or changes a rank, the implementation is wrong
— that is the overlay's acceptance test, not a nice-to-have.

### Where the notice sits (v0.33)

```
3a     build_rankings.py  ──► rankings.json    ── rank order (band, then Q'')
3a-bis coherence_audit.py ──► coherence.json   ── tier may drop one level
       │
       │   READ-ONLY below this line
       ▼
H1     Claude             ──► important_notice_checkpoint.md
       │                      prose only — no score, no rank, no tier
       ▼
4      build_report.py       renders it after the appendices, before the methodology
```

One layer further out again, held to the same standard. The notice reads `rankings.json` to know
which 15 stocks to write about and which group each belongs to; it writes only
`important_notice_checkpoint.md`. Delete that checkpoint and the PDF builds with every rank, tier
and score identical.

The property is enforced structurally rather than trusted: `TestNoticeIsOutsideEveryScoringLayer`
fails if any script other than `build_report.py` and `check_checkpoints.py` so much as mentions
the notice, and if `coherence_audit.py` ever grows a `sentiment` input. That second half matters
because `macro_factors.json` — where the M1 expectations/sentiment facet would most naturally be
written — is the overlay's input, and anything placed there can move a display tier.

---

## Project structure

```
.
├── SKILL.md                          # Skill orchestration: pipeline, error tree, constraints
├── README.md
├── CHANGELOG.md                      # Version history and the reasons for each change
├── requirements.txt
├── assets/
│   └── disclaimer.md                 # English-only disclaimer (verbatim in every PDF)
├── references/                       # Methodology readers (no executable code)
│   ├── methodology.md                # What the skill does and does not do
│   ├── quality_screen.md             # Screen criteria and rationale
│   ├── consensus_signal.md           # v0.4: votes, fund independence (N_eff), bands, limits
│   ├── crowding_signal.md            # Exit liquidity and the currency gate (v0.4 retitle)
│   ├── providers.md                  # Provider routing, EDGAR contract (B1 email), confidence
│   ├── honest_framing.md             # Framing template for Layer 3 (bias stated once)
│   ├── macro_appendix.md             # v0.3 macro/expectations appendices + source gate
│   │                                 #   (v0.33: M1 gains the expectations/sentiment facet)
│   ├── coherence_overlay.md          # v0.31 overlay: inputs, verdicts, invariants, deferrals
│   ├── important_notice.md           # v0.33 Part H: expectations bar + sentiment cycle,
│   │                                 #   sourcing rules, guardrails, what the gate enforces
│   └── ticker_aliases.json           # v0.34: curated name -> ticker aliases (EN, zh-Hant, zh-Hans)
├── scripts/                          # Deterministic computation (no LLM calls)
│   ├── validate_uploads.py           # + v0.32 G3 regional advisory (non-blocking)
│   ├── resolve_tickers.py            # v0.34 Stage 1b-resolve: SEC exchange-file listing check
│   ├── extract_holdings.py           # + v0.32 currency normalisation + thin-exposure flag
│   ├── overlap_analysis.py
│   ├── fetch_fundamentals.py         # Stage 2b: EDGAR + yfinance → fundamentals.json
│   ├── compute_scores.py
│   ├── aggregate_funds.py
│   ├── benchmark_weights.py          # v0.4 Stage 2f-i: benchmark proxy top-10 weights
│   ├── consensus_signal.py           # v0.4 Stage 2f-ii: consensus signal v2
│   ├── build_rankings.py             # Sole author of rank: (band, Q'', c_share, ticker)
│   ├── etf_relative_strength.py      # v0.31 E2.3: RS vs SPY, fixed 3M/6M/12M windows
│   ├── coherence_audit.py            # v0.31 Stage 3a-bis: the overlay → coherence.json
│   ├── build_report.py               # + v0.33 notice placement (after appendices, pre-method)
│   ├── quality_screen.py             # + v0.31 post-screen industry census (M1 scope)
│   ├── crowding_signal.py            # v0.4: exit liquidity only (USD-only AUM since v0.32)
│   ├── check_checkpoints.py          # v0.3 D4 gate + v0.31 overlay + v0.32 sections
│   │                                 #   + v0.33 Part H notice content rules
│   ├── layer1_report.py              # v0.32 G4: consolidated input-review block
│   ├── layer2_report.py              # + currency exclusions + thin-exposure count
│   ├── layer3_report.py              # Tier grouping applies demotions; rank display unchanged
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                   # DataPoint, FundamentalsRecord, ABCs
│   │   ├── edgar_provider.py         # True-PIT EDGAR: 10-K/20-F/40-F, us-gaap + ifrs-full,
│   │   │                             #   SEC exchange-file ticker map (v0.34)
│   │   ├── yfinance_provider.py      # Degraded-PIT fallback (sole yfinance import); replay mode
│   │   ├── registry.py               # Provider routing + field-level fallback (v0.34)
│   │   ├── resolver.py               # Conflict resolution + data_provenance log
│   │   ├── names.py                  # v0.34: company-name normalisation for name-only rows
│   │   ├── benchmark_map.py          # v0.4: printed benchmark -> proxy ETF (Appendix B)
│   │   └── industry_map.py           # Industry buckets + v0.31 industry → sector-ETF column
│   └── dev/                          # Maintainer tools — never imported by the pipeline
│       ├── edgar_smoke.py            # Which SEC endpoints answer (needs a contact email)
│       ├── record_fixtures.py        # Records trimmed SEC fixtures + a concept census
│       ├── legacy_v033.py            # The retired v0.33 composite, for comparison only
│       └── compare_rankings.py       # v0.33 vs v0.4 rankings of one work dir, side by side
└── tests/                            # Offline stdlib-unittest suite (no network)
    ├── test_smoke.py                 # v0.2–v0.33 regression tests
    ├── test_v04_*.py                 # one module per v0.4 work-package group
    └── fixtures/                     # recorded SEC data (trimmed) + synthetic yfinance replays
```

---

## Installation

```bash
pip install -r requirements.txt --break-system-packages
```

No API keys required. **A SEC EDGAR contact email is required (v0.3 B1)** — SEC returns 403
without one. Supply it via `--email you@example.com` to `validate_uploads.py` /
`fetch_fundamentals.py` / `resolve_tickers.py`, or set `EDGAR_CONTACT_EMAIL`. The email is
placed only into the EDGAR request header; it is not stored or transmitted anywhere else.

### Install for Claude Code CLI (v0.4)

1. Clone the skill into a skills directory, under the name `financial-research`:
   - personal: `~/.claude/skills/financial-research/`
   - one project only: `<project>/.claude/skills/financial-research/`
2. Install the dependencies (above) into the Python that Claude Code uses.
3. Set `EDGAR_CONTACT_EMAIL`, or pass `--email` when asked.
4. In Claude Code, run **`/financial-research`** and give it the path of the `.zip` of 7–11
   fund factsheet PDFs (a folder of PDFs also works on the CLI).

Outside the claude.ai sandbox every runtime directory is relative to the directory Claude
Code runs in: working files in `./fr_work`, the PDF report and checkpoint copies in
**`./fr_outputs`**, extracted uploads in `./fr_uploads`. Override any of them with
`FR_WORK_DIR`, `FR_OUTPUTS_DIR`, `FR_UPLOADS_DIR` or `EDGAR_CACHE_DIR`
(`scripts/paths.py`). On claude.ai nothing needs configuring.

---

## Usage

This is a Claude skill — put 7–11 HKMA-approved fund factsheet PDFs into **one `.zip`**, upload it, and run `/financial-research` (or ask Claude for fund analysis). The skill runs the full pipeline and surfaces a downloadable PDF report.

For local development, individual scripts can be run directly:

```bash
# Stage 0 — validate (+ SEC email gate). --out saves the result so Stage 1e can
# reproduce the v0.32 regional advisories inside the consolidated input review.
python scripts/validate_uploads.py /path/to/uploads --email you@example.com \
  --out fr_work/stage0_validation.json

# Stage 1b-resolve (v0.34) — SEC listing check: a row is kept only if SEC's
# exchange file lists it on Nasdaq, NYSE or CBOE (--sec-file replays a saved copy)
python scripts/resolve_tickers.py --holdings fr_work/holdings.json \
  --email you@example.com

# Stage 1b-d — filter, normalise currency, flag thin US exposure, dedupe
# (after Claude writes holdings.json at Stage 1a)
python scripts/extract_holdings.py --input fr_work/holdings.json --dedupe

# Stage 1e — Layer 1 report (--stage0 is optional; without it the advisory
# subsection is omitted rather than printed empty)
python scripts/layer1_report.py \
  --holdings fr_work/holdings.json \
  --stage0 fr_work/stage0_validation.json

# Stage 2a — overlap matrix
python scripts/overlap_analysis.py \
  --holdings fr_work/holdings.json \
  --out fr_work/overlap.json

# Stage 2b — fetch fundamentals from EDGAR + yfinance, with resolver
python scripts/fetch_fundamentals.py \
  --holdings fr_work/holdings.json \
  --email you@example.com \
  --out fr_work/fundamentals.json

# Stage 2d — quality screen (PASS / FAIL)
python scripts/quality_screen.py \
  --holdings fr_work/holdings.json \
  --fundamentals fr_work/fundamentals.json \
  --unscored fr_work/unscored_tickers.json \
  --out fr_work/screen_results.json

# Stage 2e — fundamental quality scores
python scripts/compute_scores.py \
  --fundamentals fr_work/fundamentals.json \
  --screen fr_work/screen_results.json \
  --out fr_work/scores_per_stock.json

# Stage 2f-i (v0.4) — benchmark proxy top-10 weights per fund
# (--replay <file> reads a saved {etf: {ticker: weight}} instead of the network)
python scripts/benchmark_weights.py \
  --holdings fr_work/holdings.json \
  --out fr_work/benchmark_weights.json

# Stage 2f-ii (v0.4) — consensus signal v2: votes, fund independence, bands.
# --vote-basis presence / --vote-floor none are for sensitivity runs only.
python scripts/consensus_signal.py \
  --holdings fr_work/holdings.json \
  --benchmark-weights fr_work/benchmark_weights.json \
  --out fr_work/consensus.json

# Stage 2f-iii — exit liquidity (days-to-liquidate, USD-reporting holders only)
python scripts/crowding_signal.py \
  --overlap fr_work/overlap.json \
  --holdings fr_work/holdings.json \
  --fundamentals fr_work/fundamentals.json \
  --out fr_work/crowding_signals.json

# Stage 3a — the ranking (the ONLY writer of rank order): band, then Q''
python scripts/build_rankings.py \
  --scores fr_work/scores_per_stock.json \
  --consensus fr_work/consensus.json \
  --overlap fr_work/overlap.json \
  --out fr_work/rankings.json

# Stage 3a-bis-i (v0.31) — sector-ETF relative strength vs SPY, fixed 3M/6M/12M
# (--prices <file> replays a saved {symbol: [closes]} map instead of calling yfinance)
python scripts/etf_relative_strength.py \
  --rankings fr_work/rankings.json \
  --out fr_work/etf_relative_strength.json

# Stage 3a-bis (v0.31) — the coherence overlay. Writes ONLY the side-car;
# rankings.json is read-only. Each input is optional: an absent one degrades the
# affected pairs to "insufficient data", never to a verdict.
python scripts/coherence_audit.py \
  --rankings fr_work/rankings.json \
  --macro fr_work/macro_factors.json \
  --sector-logic fr_work/sector_logic.json \
  --etf fr_work/etf_relative_strength.json \
  --crowding fr_work/crowding_signals.json \
  --out fr_work/coherence.json

# Stage 3d — Layer 3 report. Drop --coherence to get the pre-overlay (v0.3) tiers.
python scripts/layer3_report.py \
  --rankings fr_work/rankings.json \
  --framing fr_work/honest_framing.txt \
  --rationale-dir fr_work/rationale/ \
  --coherence fr_work/coherence.json \
  --crowding fr_work/crowding_signals.json \
  --out fr_work/layer3_ranked_advice.md

# Macro gate — deterministic checkpoint review (v0.3 D4 + v0.31 overlay invariants
# + v0.33 Part H notice rules: two-source citations, per-entry sourcing, no verdict
# vocabulary, no ticker-bound sentiment claim, constructive register).
# coherence.json and important_notice_checkpoint.md are checked when present;
# --require-coherence / --require-important-notice make them mandatory.
python scripts/check_checkpoints.py fr_work/

# Stage 4 — PDF assembly (+ copies all checkpoint .md to the outputs dir, D5)
python scripts/build_report.py \
  --work-dir fr_work/ \
  --out fr_outputs/financial_research_report.pdf
```

### Running the test suite

```bash
python -m unittest discover tests -v
```

Offline, no network calls, no pytest dependency.

Alongside the unit tests, the suite locks in the structural invariants each iteration
depends on, as grep- and property-based tests that must never be deleted:

| Test | Invariant |
|---|---|
| `TestNoFxConversion` | no FX-conversion machinery anywhere in `scripts/` (v0.32) |
| `TestNoticeIsOutsideEveryScoringLayer` | no scoring stage reads the Important Notice (v0.33) |
| `TestConsensusIgnoresStyle` | no LLM-inferred style label enters the consensus (v0.4, I9) |
| `TestNoLegacyWeights` | the retired 50/50 weights live only under `scripts/dev/` (v0.4, I4) |
| `TestRankingReadsNoMacro` | the ranking reads no macro, sector, ETF, overlay or crowding input (v0.4) |
| `TestSingleYfinanceImport` | yfinance is imported in exactly one file (I11) |
| `TestDeterministicRanking` | shuffled inputs give a byte-identical `rankings.json` (I10) |

If one of those properties is ever quietly broken, a test is what says so.

---

## Output

The layered `.md` checkpoints, the overlay's audit trail, and a final English-only PDF:


| File                              | Content                                                                      |
| --------------------------------- | ---------------------------------------------------------------------------- |
| `layer1_extraction.md`            | v0.32 — opens with the consolidated **input review** (rejections, reporting currency per fund + exit-liquidity exclusions, thin-US-exposure flags, Stage 0 advisories, style distribution), then per-fund extraction, universe size, out-of-scope |
| `layer2_screening.md`             | Overlap matrix, quality screen (incl. passed-but-unscored), data quality, consensus structure (N_eff, fund weights, floor, coverage), exit liquidity, currency exclusions, thin-exposure count |
| `layer3_ranked_advice.md`         | Honest framing (stated once), up-to-15 watchlist cards, benchmark-anchored core holdings, methodology disclosure |
| `macro_checkpoint.md`             | v0.3 — central-bank-anchored macro/sector view, per-sentence attribution     |
| `expectations_checkpoint.md`      | v0.3 — per-stock best/avg/worst scenarios driven by the macro view           |
| `appendix3_consensus_warning.md`  | v0.3 — over-consensus & false-theme warning + fund-style remediation         |
| `important_notice_checkpoint.md`  | v0.33 — per-stock expectations bar + sentiment cycle, group-attributed and sourced; enters no score |
| `coherence.json`                  | v0.31 — per-stock audit: three factor readings, pairwise verdicts, tier delta, contradiction text |
| `financial_research_report.pdf`   | All of the above, assembled into a denser English PDF (18–26pp ceiling)      |

All checkpoint files — including `coherence.json` — are copied to the outputs directory (`./fr_outputs` on the CLI)
alongside the PDF (the container work dir is ephemeral and resets between sessions).
`coherence.json` is shipped because keeping the qualitative judgment out of the ranking is
only worth something if a reader can check every demotion against the readings that produced it.

Intermediate v0.31 working files (`macro_factors.json`, `sector_logic.json`,
`etf_relative_strength.json`) stay in the work dir; they are inputs to the audit, and the audit
itself is what gets shipped.

---

## Version history

What changed in each version, and why — including the design-decision tables from
v1 to v0.33 — is in [`CHANGELOG.md`](./CHANGELOG.md).

---

## Dependencies

- `pypdf >= 4.0` — Stage 0 validation / flat-text fallback
- `pdfplumber >= 0.11` — Stage 1a hybrid table extraction (v0.3 D1)
- `yfinance >= 0.2.40` — market data fallback (only imported in `providers/yfinance_provider.py`)
- `requests >= 2.31` — EDGAR HTTP calls
- `pandas >= 2.0`, `numpy >= 1.24`
- `reportlab >= 4.0` — PDF generation (English layout, no CJK font needed)
- `matplotlib >= 3.7` — chart embedding

---

## Disclaimer (repeat)

> **The reports produced by this skill are AI-generated analyses and must not be used as investment advice.**
> Past performance does not guarantee future results. Data sources may contain errors or delays. Any investment decision made based on these reports is solely the user's responsibility.

---

### Appendix: Other known risks or bugs

1. **Ticker symbol compatibility (fixed in v0.34)**: the pipeline writes share classes as `BRK.B`; SEC and Yahoo write `BRK-B`. Both providers now map between the two forms, and lookups succeed whichever form a factsheet used.
2. **ADR / IFRS data coverage (fixed in v0.34)**: EDGAR used to read `us-gaap` facts in USD only, so a foreign issuer reporting under IFRS or in another currency (TSMC: IFRS, TWD) came back empty and silently dropped out of the ranking. EDGAR now reads `ifrs-full` as well, in the issuer's reporting currency, building ROE and D/E only from same-unit pairs; when it still has nothing usable, yfinance fills in field by field, and a stock that passes the screen but cannot be scored is listed in Layer 2 with its reason.
3. **SEC request rate (corrected in v0.34)**: SEC publishes a fair-access *rate* limit — at most 10 requests per second — not a daily quota. v0.33 enforced a 600-request "daily budget" that does not exist, so a large universe silently lost EDGAR coverage after 600 calls. The provider keeps the 100 ms throttle and the 1 s → 2 s → 4 s backoff on HTTP 429; a 10,000-request runaway guard, logged as a WARNING, replaces the budget. Each uncached ticker costs about two requests (companyfacts + submissions), plus one ticker-map download per week.
4. **Sector-ETF proxy error (v0.31)**: an eleven-bucket industry map is coarser than a real sector classification, so a stock can be measured against an ETF that is only approximately its sector — a diversified conglomerate or an unusual ADR most of all. The mapping is deliberately conservative (`other` is left unmapped, producing "insufficient data" instead of a wrong proxy), but a *plausible-but-imprecise* bucket will still be used.
5. **Uncalibrated overlay bands (v0.31)**: the thresholds separating "outperforming / inline / lagging" (±5pp) and "sharp divergence" (±20pp) are round numbers, not fitted parameters — there is no backtest in this tool to fit them against. They exist to separate decisive moves from noise. This is why the overlay is capped at a single tier and can only demote: a wrong band costs one display tier on one stock, never a re-ordering.
6. **Structured macro fields are a lossy summary (v0.31)**: collapsing a central-bank corpus into one rate direction and one inflation direction discards nuance by design (regional divergence, forward guidance conditionality). The full narrative stays in `macro_checkpoint.md`; the structured fields exist only to make the coherence comparison mechanical and auditable.
7. **Reduced exit-liquidity coverage on non-USD input sets (v0.32)**: excluding non-USD AUM is correct but not free — an input set dominated by HKD share classes leaves most stocks with no days-to-liquidate figure (`no-liquidity-data`), so the overlay's exit-liquidity check rarely fires. This is a *stated* gap rather than a distorted number, and the exclusion count is reported in Layer 1 and Layer 2, but the check is genuinely weaker on such a run.
8. **Currency normalisation depends on Stage 1a (v0.32)**: the gate reads the `currency` the LLM extracted. A factsheet that states its reporting currency only in a footnote, a share-class table, or an image the text layer does not carry will come through as `null` and be excluded — the safe direction, but a false exclusion. Only unambiguous spellings are mapped (`US$`, `HK$`, `Euro`, `RMB`); a bare `$` or `¥` resolves to `null` rather than a guess.
9. **The regional advisory is a title heuristic (v0.32)**: it reads the first few lines of page one, keeping lines that carry a fund-type word and no percentage figure. A factsheet whose title sits in an image, or whose text layer scrambles the first page, produces no advisory; a fund-of-funds row named after a region could produce a spurious one. Neither outcome affects the pipeline — Stage 1c is still the only thing that rejects a fund.
10. **Group attribution is coarser than the company (v0.33)**: the notice attributes each stock to its industry bucket (or a named theme where the evidence supports one) and then describes *that group's* environment. A semiconductor name with little AI exposure still inherits the AI-infrastructure expectations reading, and a diversified company inherits whichever bucket it landed in. This is the deliberate trade: the precise alternative — a per-company sentiment claim — cannot clear the two-source gate and is the highest fabrication risk in the design.
11. **A not-found entry is not an all-clear (v0.33)**: where a group has thin sentiment coverage, the entry states that no corroborating evidence was found. That means *no evidence either way* — not that the group's expectations bar is normal. Coverage is uneven by construction, so the well-documented groups (semis / AI infrastructure) get substantive entries while quieter sectors get a blank, and the asymmetry is a property of the source material, not a reading of the stocks.
12. **The notice gate checks strings, not truth (v0.33)**: `check_checkpoints.py` catches banned verdict vocabulary, ticker-bound sentiment, unsourced entries and single-source citations. It cannot judge whether two named sources are genuinely independent, or whether the cited material actually supports the sentence written next to it. A fluent, correctly-formatted, correctly-cited but *wrong* paragraph passes the gate — that half of the review is Claude's, and it is the half that matters most here.
13. **Square brackets are reserved inside the notice (v0.33)**: the two-source check reads every `[...]` in `important_notice_checkpoint.md` as a citation, so a markdown link or a bracketed aside is flagged as a single-source citation. The convention is documented in `references/important_notice.md`; the trade is a rigid notation in exchange for a mechanical C2 check on the section that most needs one.
14. **Name-only rows for foreign issuers are excluded and disclosed (v0.34)**: a factsheet that lists a holding by name alone — "台積電", "Taiwan Semiconductor Manufacturing" — does not say whether the fund holds the US ADR or the home-market share. For a foreign private issuer (20-F / 40-F filer) the row is kept only with evidence: an ADR marker in the name or a US ISIN. Without it the row is excluded as `ambiguous_listing` and listed in Layer 1's input review. The error is one-sided by design — a possible false exclusion, never a false inclusion — and an issuer whose filer type cannot be determined is treated the same way.
15. **A non-US ISIN alone never excludes a US-listed share (v0.34)**: the listing check reads the ticker first. Accenture, Medtronic and Chubb trade on the NYSE with Irish or Swiss ISINs; they are kept. Only on a name-only row of a foreign private issuer does a non-US ISIN decide (`non_us_listing`: the fund holds the home-market share).
