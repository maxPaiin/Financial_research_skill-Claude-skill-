> **Trigger keyword:** `/claude_skill_Financial_research`

# Financial Research Skill v0.33

> **v0.33 (current) — the Important Notice.** An outermost-layer addition: a per-stock
> section covering the two factors the ranking framework structurally *cannot* measure —
> the **expectations bar** and the **sentiment cycle** — each backed by evidence retrieved
> in the existing macro subsystem, with references cited.
> - **It sits outside every layer, and changes nothing.** The composite ranks; the v0.31
>   overlay may demote a tier; **this notice touches neither.** It never enters `Q''`, `C`,
>   the composite, `rankings.json` or `coherence.json`. Delete the section and every rank,
>   tier and score is bit-for-bit identical — the same reversibility property v0.31 holds,
>   stated one layer further out.
> - **Why outside, rather than a score.** Both factors are genuinely unquantifiable *in this
>   tool*: the backtest was removed in v0.2, so there is nothing to calibrate "is the market
>   overheated" against. Inventing a number would be exactly the false precision the honest-
>   framing policy exists to prevent — and a valuation tilt would systematically demote
>   semiconductor/AI names, precisely the names the HK channel surfaces most. A **sourced
>   notice is the only truthful form available.**
> - **What the framework is blind to.** The quality axis is entirely backward-looking: a
>   company that has beaten for eight straight quarters with three years of growth already in
>   the price, and a company with identical ROE that nobody expects anything from, **score the
>   same on `Q`**. `EV/EBITDA` does not help — it is a screen gate only, never scored, and it
>   is an absolute threshold rather than a position within the stock's own history.
> - **Sector-level evidence, per-stock attribution.** "The expectations bar for semiconductors
>   / AI infrastructure has been raised" is corroborable in Reuters/WSJ/BlackRock/Fed material.
>   "The market's expectations for AVGO specifically are too high" is not — single-stock
>   sentiment assertions are the **highest-fabrication-risk content in this skill**, fluent and
>   trivially invented. So the notice retrieves at group level and narrates by attributing the
>   stock to its group. **The C2 two-source hard gate is never relaxed here**; where evidence
>   is thin the entry says so explicitly, which is itself information.
> - **Constructive, not defensive.** It is not a second disclaimer — the standing verbatim one
>   already covers that. Its argument is the point: **Tier A means highest-ranked on the
>   measurable dimensions, and precisely for that reason such a name is more likely already
>   fully priced. The two readings must be held together.** Stated once at the section head,
>   never per stock.
> - **No new retrieval scope.** M1 was already bound to the post-screen universe's industries;
>   v0.33 adds a *facet* to that retrieval, not a scope. Per-stock retrieval is out of scope.
> - **Unchanged:** the composite, `Q''`, `C`, rank order, tiers, the v0.31 overlay, the screen,
>   the input gates and the existing disclaimer.

> **v0.32 — a defect patch, not a feature iteration.** It closes a currency-unit
> hole that v0.3's days-to-liquidate metric silently opened, and adds two input-review
> warnings the existing gates do not produce. It is kept as a separate version line so a
> reader can tell which changes *added* behaviour and which *corrected* it.
> - **`currency` is now a required Stage 1a field**, normalised to ISO-4217, and **`null`
>   when the factsheet does not state one — never defaulted to USD.** A bare `$` is
>   ambiguous (USD/HKD/SGD/AUD) and counts as unstated.
> - **Only USD-reporting funds enter the days-to-liquidate aggregate.** ADV is always USD,
>   so an HKD-reported AUM overstated days-to-liquidate by ~7.8× — silently, with no error
>   and no flag. That matters disproportionately here: the target input is the **Hong Kong
>   distribution channel**, where HKD-denominated share classes are routine.
> - **Excluded, never converted.** FX conversion would need a rate source, a rate-date policy
>   and a new provenance path — three new failure modes to repair a metric that already has
>   a well-defined NAV-only fallback. **No FX conversion exists anywhere in the codebase.**
>   An excluded fund still counts in full toward overlap, consensus and style diversity;
>   only its AUM is set aside, and tickers held solely by such funds show NAV-only crowding.
> - **Thin-US-exposure warning.** A global fund with 5 US holdings at 21% of AUM passes the
>   viability gate, then votes in the consensus signal exactly as loudly as a 95%-US fund —
>   `n_funds_holding` counts funds, not exposure. Funds at 20–35% are flagged in Layer 1,
>   Layer 2 and Appendix 3 and are deliberately **not** down-weighted: re-weighting would
>   alter `C`, whose definition is locked. A defect patch corrects; it does not redefine a signal.
> - **Stage 0 regional advisory.** A regional fund is otherwise rejected only at Stage 1c —
>   *after* the most expensive step in the pipeline. A title match now raises an advisory up
>   front. **Non-blocking by design**: a keyword is not evidence, Stage 1c remains the sole
>   authority on rejection, and a false advisory costs one sentence while a false rejection
>   would discard a valid input.
> - **One consolidated input review** at the top of `layer1_extraction.md`, so the user sees a
>   single review of what they submitted rather than warnings scattered across sections.
> - **Unchanged:** composite weights (50/50), `Q''`, `C`, rank order, viability thresholds
>   (≥5 holdings, ≥20% weight), Stage 0 blocking behaviour, and the entire v0.31 overlay. On
>   an all-USD input set the numeric output is bit-for-bit identical to v0.31.

> **v0.31 — the coherence overlay.** A bolt-on that asks one question per ranked
> stock: do the **macro read**, the **sector operating logic**, and the **sector-relative price
> action** tell the same story? Where they contradict each other, the stock's picture is
> incoherent — and in this tool incoherence is uncertainty, which is treated as a quality
> defect. Key deltas vs v0.3:
> - **Demotion-only, by construction.** The overlay can move a stock **down one display tier**
>   and never up. That is what makes it a bolt-on rather than a rewrite: switch it off and the
>   report is exactly the v0.3 output — reversibility as a hard property, not an aspiration.
> - **Rank never moves; only the tier does.** A stock ranked #3 whose macro and sector logic
>   contradict each other stays at **rank #3**, shown in **Tier B**, with the contradiction named
>   on its card. Rank stays a purely quantitative product of the composite; the tier carries the
>   qualitative judgment, and the two stay separable — *"ranked #3, demoted to B because X
>   contradicts Y"* is auditable in a way that folding macro into the score never could be.
> - **Not a third scoring axis.** `0.4·Q + 0.4·C + 0.2·Macro` was rejected: with no backtest
>   (removed in v0.2) the weight cannot be calibrated, and writing one down would be exactly the
>   false precision this tool's honesty framing exists to prevent. **Weights stay 50/50.**
> - **The macro stage moved earlier (M1: after 3a → after 2d)** and is now scoped to the
>   **post-screen universe's** industries. Tiering depends on macro, so macro must exist before
>   ranking — and the top-15 is *produced by* ranking, so the old anchor was circular. Pure
>   sequencing move: M1's sources, directed-fetch policy and hard corroboration gate are unchanged.
> - **Sector logic generalised to three universal questions** — *what constrains the inputs / how
>   much pricing power / what return on capital deployed* — replacing the physical supply-chain
>   triad, which produces confident nonsense on software, financial and consumer names.
> - **ETF check is divergence detection, never confirmation.** Relative strength **vs SPY** over
>   **fixed 3M/6M/12M** windows. Price agreeing with a thesis is not treated as evidence for it:
>   momentum confirmation is pro-cyclical and consensus already is, so stacking them would point
>   both signals the wrong way together in a de-rating.
> - **Missing data is never a verdict.** No sector-ETF mapping or a sparse macro read yields
>   **"insufficient data", tier unchanged** — it may not pass as coherence, nor be punished as a
>   contradiction, which would let data gaps drive tiering.
>
> Full spec: [`references/coherence_overlay.md`](./references/coherence_overlay.md).

> **v0.3** — risk-aware consensus, confidence-penalised quality, central-bank-anchored
> macro appendix, conservative-by-design. Key deltas vs v0.2:
> - **Confidence-shrunk quality (A4).** The quality half is low-anchor shrunk: `Q'' = c·Q + (1−c)·10`.
>   Low-confidence (yfinance) quality is pulled toward a low-but-non-zero anchor, so unverifiable
>   numbers cannot float a stock to mid-pack. Applied to quality only; not re-percentiled.
> - **Exit-crowdedness (A2).** Crowding now folds in days-to-liquidate = (Σ fund_AUM × weight) / ADV,
>   labelled liquidity-inclusive or NAV-only.
> - **Style-diversity-weighted consensus (A3).** Cross-style agreement outweighs same-mandate
>   funds; a run-level homogeneity warning fires when the input is single-style. Stratified
>   sampling is abandoned (sample too small; token budget).
> - **SEC email gate (B1).** A user-supplied contact email is required and injected into the EDGAR
>   User-Agent (SEC returns 403 without it).
> - **Macro & expectations appendices (C).** Central-bank-anchored, primary-first, with a hard
>   ≥2-primary-tier corroboration gate and per-sentence attribution.
> - **Denser PDF + checkpoint copy (D).** Fewer forced page breaks; all checkpoint `.md` files are
>   copied to the user-visible outputs directory.

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

**Purpose.** Hong Kong private-banking distribution channels (Standard Chartered HK, Citi HK, and similar) sell a limited set of HKMA-approved global equity funds. This skill takes 7–11 of those fund factsheets, isolates their US-listed holdings, cross-checks fundamentals against SEC EDGAR, and produces a single ranked watchlist of the 15 highest-quality stocks the channel surfaces — with the selection bias and data limitations disclosed explicitly in every report.

**Non-goals.** It is not an alpha tool, not a backtest engine, not a portfolio constructor. Rankings reflect what HK distributors are pushing, not what the global market is doing. The output is meant as a research starting point, not a trade list.

---

## Disclaimer

> **This skill produces an AI-generated analysis. The reports it generates must not be used as investment advice.**
> All rankings and scores are derived from publicly available data and statistical models. Past performance does not guarantee future results. Data sources (SEC EDGAR, yfinance, fund prospectus PDFs) may contain errors or delays. Any investment decision is solely the user's responsibility.

The verbatim disclaimer in `assets/disclaimer.md` is embedded into every generated PDF (front and back pages) and printed in the chat response.

---

## What this skill does

Given **7–11 HKMA-approved global fund prospectus PDFs**, the skill runs a three-layer pipeline:

1. **Layer 1 — Extraction**: validates uploads, extracts US-listed equity holdings (including ADRs) from each fund via LLM-assisted PDF parsing, filters out non-US listings, deduplicates across funds.
2. **Layer 2 — Overlap & Screen**: builds a cross-fund overlap matrix, fetches fundamentals from SEC EDGAR (true PIT) with yfinance fallback, applies a quality screen (PASS/FAIL), computes a fundamental quality percentile score, and computes the v0.3 consensus signal (style-diversity-weighted, with an exit-liquidity / days-to-liquidate crowding discount).
3. **Layer 3 — Ranking & Advice**: composite-ranks the passed universe (fixed 50/50; the quality half is low-anchor confidence-shrunk), selects the top 15 stocks, organizes them into Tier A/B/C, and generates per-stock rationale cards with honest framing (HK-bias stated once).
4. **Coherence overlay (v0.31)**: audits each ranked stock for agreement between the macro read, the sector operating logic and sector-ETF relative strength, and **demotes** — never promotes — the display tier by at most one level where they contradict, naming the contradiction on the card. Writes a side-car `coherence.json`; `rankings.json` is read-only to it.
4b. **Input review (v0.32)**: reports what the submitted set actually is — reporting currency per fund and which funds that excludes from the exit-liquidity aggregate, funds whose US sleeve is thin, Stage 0 regional advisories, rejections, and the style distribution — as one block rather than warnings scattered across sections.
5. **Macro appendices (v0.3)**: central-bank-anchored macro/sector view, per-stock best/avg/worst scenarios, and an over-consensus / fund-style remediation appendix — all under a hard ≥2-primary-tier source-corroboration gate.

**Output**: the layered `.md` checkpoints, the `coherence.json` audit trail, and a single English-only PDF report, all copied to the user-visible outputs directory.

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
- **Not an exposure-weighted consensus (v0.32).** The consensus counts funds, not US exposure. Funds with a thin US sleeve are flagged, not down-weighted — that would change a locked signal.
- **Not a supply-chain mapper.** Industry-policy and company-level supplier claims are deliberately out of scope — those relationships are absent from EDGAR's structured data and are the highest fabrication risk in the design.

---

## Input requirements

The skill is gated at three levels. If any gate fails, the pipeline halts and the user is told exactly which inputs caused the failure so they can replace them.

### Level 1 — File-level (Stage 0, `validate_uploads.py`)

Every uploaded PDF is checked before any LLM parsing begins:


| Check            | Requirement                                                                                                                                                                                                                                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| File count       | **7–11** `.pdf` files in the upload directory (inclusive).                                                                                                                                                                                                     |
| Parseable        | Each PDF must open with`pypdf` and contain at least one page.                                                                                                                                                                                                   |
| Extractable text | The first 10 pages combined must yield non-empty text. Image-only scans fail here.                                                                                                                                                                              |
| Holdings keyword | Each PDF must contain at least one of:`holdings`, `portfolio`, `top holdings`, `portfolio composition`. Bilingual HK factsheets often include Chinese equivalents as well — the validator accepts those too; see `validate_uploads.py` for the canonical list. |
| Reporting date   | Each PDF must contain a recognizable date. Supported formats include`2025-03-31`, `31/03/2025`, `Q1 2025`, `FY 2024`, `H1 2025`, `March 31, 2025`, `31 March 2025`, `March 2025`.                                                                               |
| Regional advisory (v0.32) | **Not a check.** If the fund's *title* names a region (Asia, Europe, Japan, China, EM, Latin America, India, ASEAN, or a bilingual equivalent), Stage 0 prints an advisory naming the file — that fund may hold fewer than 5 US-listed equities and be rejected at Stage 1c, after the expensive parse. It does **not** halt, reject, or change the exit code or file count. Matching is restricted to the title (percentage-bearing lines are ignored) so a global fund's country-breakdown table does not trip it. |

### Level 2 — Per-fund content (Stage 1a, LLM extraction)

Claude reads each PDF and writes one record per fund into `holdings.json`. For that to succeed, each PDF must surface the following:


| Field                   | Required?   | Why it matters                                                                               |
| ----------------------- | ----------- | -------------------------------------------------------------------------------------------- |
| Fund name               | yes         | Identifies the fund in every downstream report.                                              |
| Issuer                  | recommended | Shown in Layer 1 / 2 summaries.                                                              |
| Reporting date (`asof`) | yes         | Per-fund snapshot date; appears in Layer 1 and PIT tracking.                                 |
| **Reporting currency**  | **yes (v0.32)** | ISO-4217 code for `total_aum` (`USD`, `HKD`, `EUR`, `JPY`, …). **`null` if the factsheet does not state one — never defaulted to USD**; a bare `$` is ambiguous and counts as unstated. Only USD-reporting funds enter the days-to-liquidate aggregate; the rest are excluded (never FX-converted) and their tickers fall back to NAV-only crowding. |
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
| User uploads 7–11 fund prospectus PDFs and asks for analysis.                                                                                     |
| Phrases:*fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, fund prospectus analysis*, "analyze these fund PDFs". |

If fewer than 7 PDFs are supplied, validation stops the pipeline and asks the user to resubmit.

---

## Pipeline overview


| Layer                       | Stages       | Key scripts                                                                                                                        |
| --------------------------- | ------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Layer 1 — Extraction       | 0–1e        | `validate_uploads.py`, `extract_holdings.py`, `layer1_report.py`                                                                   |
| Layer 2 — Overlap & Screen | 2a–2g       | `overlap_analysis.py`, `providers/registry.py`, `quality_screen.py`, `compute_scores.py`, `crowding_signal.py`, `layer2_report.py` |
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
2e–2f ──► 3a build_rankings.py ──► rankings.json ──┐   (sole author of composite + rank)
                                              │    │   READ-ONLY below this line
                            etf_relative_strength.py│
                                              ▼    ▼
                       3a-bis coherence_audit.py ──► coherence.json   (side-car)
                                              │
      3b/3d cards + layer3_report.py ◄────────┘   tier may drop one level; rank never changes
```

Delete `coherence_audit.py` and its side-car and the pipeline still runs, producing the v0.3
report. If removing it breaks anything downstream or changes a rank, the implementation is wrong
— that is the overlay's acceptance test, not a nice-to-have.

---

## Project structure

```
.
├── SKILL.md                          # Skill orchestration: pipeline, error tree, constraints
├── README.md
├── requirements.txt
├── assets/
│   └── disclaimer.md                 # English-only disclaimer (verbatim in every PDF)
├── references/                       # Methodology readers (no executable code)
│   ├── methodology.md                # What the skill does and does not do
│   ├── quality_screen.md             # Screen criteria and rationale
│   ├── crowding_signal.md            # Signal formula (A2 days-to-liquidate, A3 diversity,
│   │                                 #   v0.32 G1 currency gate, G2 thin-exposure warning)
│   ├── providers.md                  # Provider routing, EDGAR contract (B1 email), confidence
│   ├── honest_framing.md             # Framing template for Layer 3 (bias stated once)
│   ├── macro_appendix.md             # v0.3 macro/expectations appendices + source gate
│   │                                 #   (v0.33: M1 gains the expectations/sentiment facet)
│   ├── coherence_overlay.md          # v0.31 overlay: inputs, verdicts, invariants, deferrals
│   └── important_notice.md           # v0.33 Part H: expectations bar + sentiment cycle,
│                                     #   sourcing rules, guardrails, what the gate enforces
├── scripts/                          # Deterministic computation (no LLM calls)
│   ├── validate_uploads.py           # + v0.32 G3 regional advisory (non-blocking)
│   ├── extract_holdings.py           # + v0.32 currency normalisation + thin-exposure flag
│   ├── overlap_analysis.py
│   ├── fetch_fundamentals.py         # Stage 2b: EDGAR + yfinance → fundamentals.json
│   ├── compute_scores.py
│   ├── aggregate_funds.py
│   ├── build_rankings.py             # Sole author of composite + rank order
│   ├── etf_relative_strength.py      # v0.31 E2.3: RS vs SPY, fixed 3M/6M/12M windows
│   ├── coherence_audit.py            # v0.31 Stage 3a-bis: the overlay → coherence.json
│   ├── build_report.py               # + v0.33 notice placement (after appendices, pre-method)
│   ├── quality_screen.py             # + v0.31 post-screen industry census (M1 scope)
│   ├── crowding_signal.py            # A2 days-to-liquidate (v0.32: USD-only AUM) + A3 diversity
│   ├── check_checkpoints.py          # v0.3 D4 gate + v0.31 overlay + v0.32 sections
│   │                                 #   + v0.33 Part H notice content rules
│   ├── layer1_report.py              # v0.32 G4: consolidated input-review block
│   ├── layer2_report.py              # + currency exclusions + thin-exposure count
│   ├── layer3_report.py              # Tier grouping applies demotions; rank display unchanged
│   └── providers/
│       ├── __init__.py
│       ├── base.py                   # DataPoint, FundamentalsRecord, ABCs
│       ├── edgar_provider.py         # True-PIT EDGAR fetcher (10-K + 20-F)
│       ├── yfinance_provider.py      # Degraded-PIT fallback (sole yfinance import)
│       ├── registry.py               # Provider routing + multi-source merge
│       ├── resolver.py               # Conflict resolution + data_provenance log
│       └── industry_map.py           # Industry buckets + v0.31 industry → sector-ETF column
└── tests/                            # Offline stdlib-unittest smoke suite
    └── test_smoke.py
```

---

## Installation

```bash
pip install -r requirements.txt --break-system-packages
```

No API keys required. **A SEC EDGAR contact email is required (v0.3 B1)** — SEC returns 403
without one. Supply it via `--email you@example.com` to `validate_uploads.py` /
`fetch_fundamentals.py`, or set `EDGAR_CONTACT_EMAIL`. The email is placed only into the EDGAR
request header; it is not stored or transmitted anywhere else.

---

## Usage

This is a Claude skill — upload 7–11 HKMA-approved fund factsheet PDFs and ask Claude for fund analysis. The skill runs the full pipeline and surfaces a downloadable PDF report.

For local development, individual scripts can be run directly:

```bash
# Stage 0 — validate (+ SEC email gate). --out saves the result so Stage 1e can
# reproduce the v0.32 regional advisories inside the consolidated input review.
python scripts/validate_uploads.py /path/to/uploads --email you@example.com \
  --out /home/claude/work/stage0_validation.json

# Stage 1b-d — filter, normalise currency, flag thin US exposure, dedupe
# (after Claude writes holdings.json at Stage 1a)
python scripts/extract_holdings.py --input /home/claude/work/holdings.json --dedupe

# Stage 1e — Layer 1 report (--stage0 is optional; without it the advisory
# subsection is omitted rather than printed empty)
python scripts/layer1_report.py \
  --holdings /home/claude/work/holdings.json \
  --stage0 /home/claude/work/stage0_validation.json

# Stage 2a — overlap matrix
python scripts/overlap_analysis.py \
  --holdings /home/claude/work/holdings.json \
  --out /home/claude/work/overlap.json

# Stage 2b — fetch fundamentals from EDGAR + yfinance, with resolver
python scripts/fetch_fundamentals.py \
  --holdings /home/claude/work/holdings.json \
  --email you@example.com \
  --out /home/claude/work/fundamentals.json

# Stage 2d — quality screen (PASS / FAIL)
python scripts/quality_screen.py \
  --holdings /home/claude/work/holdings.json \
  --fundamentals /home/claude/work/fundamentals.json \
  --unscored /home/claude/work/unscored_tickers.json \
  --out /home/claude/work/screen_results.json

# Stage 2e — fundamental quality scores
python scripts/compute_scores.py \
  --fundamentals /home/claude/work/fundamentals.json \
  --screen /home/claude/work/screen_results.json \
  --out /home/claude/work/scores_per_stock.json

# Stage 2f — consensus-with-crowding-discount signal
# (v0.3: --holdings adds fund AUM + style for days-to-liquidate / diversity;
#  --fundamentals adds per-ticker ADV. Both optional — absent => NAV-only, unweighted.)
python scripts/crowding_signal.py \
  --overlap /home/claude/work/overlap.json \
  --holdings /home/claude/work/holdings.json \
  --fundamentals /home/claude/work/fundamentals.json \
  --out /home/claude/work/crowding_signals.json

# Stage 3a — composite ranking (the ONLY writer of composite scores and rank order)
python scripts/build_rankings.py \
  --scores /home/claude/work/scores_per_stock.json \
  --crowding /home/claude/work/crowding_signals.json \
  --overlap /home/claude/work/overlap.json \
  --out /home/claude/work/rankings.json

# Stage 3a-bis-i (v0.31) — sector-ETF relative strength vs SPY, fixed 3M/6M/12M
# (--prices <file> replays a saved {symbol: [closes]} map instead of calling yfinance)
python scripts/etf_relative_strength.py \
  --rankings /home/claude/work/rankings.json \
  --out /home/claude/work/etf_relative_strength.json

# Stage 3a-bis (v0.31) — the coherence overlay. Writes ONLY the side-car;
# rankings.json is read-only. Each input is optional: an absent one degrades the
# affected pairs to "insufficient data", never to a verdict.
python scripts/coherence_audit.py \
  --rankings /home/claude/work/rankings.json \
  --macro /home/claude/work/macro_factors.json \
  --sector-logic /home/claude/work/sector_logic.json \
  --etf /home/claude/work/etf_relative_strength.json \
  --out /home/claude/work/coherence.json

# Stage 3d — Layer 3 report. Drop --coherence to get the pre-overlay (v0.3) tiers.
python scripts/layer3_report.py \
  --rankings /home/claude/work/rankings.json \
  --n-funds 8 \
  --framing /home/claude/work/honest_framing.txt \
  --rationale-dir /home/claude/work/rationale/ \
  --coherence /home/claude/work/coherence.json \
  --out /home/claude/work/layer3_ranked_advice.md

# Macro gate — deterministic checkpoint review (v0.3 D4 + v0.31 overlay invariants
# + v0.33 Part H notice rules: two-source citations, per-entry sourcing, no verdict
# vocabulary, no ticker-bound sentiment claim, constructive register).
# coherence.json and important_notice_checkpoint.md are checked when present;
# --require-coherence / --require-important-notice make them mandatory.
python scripts/check_checkpoints.py /home/claude/work/

# Stage 4 — PDF assembly (+ copies all checkpoint .md to the outputs dir, D5)
python scripts/build_report.py \
  --work-dir /home/claude/work/ \
  --out /mnt/user-data/outputs/financial_research_report.pdf
```

### Running the test suite

```bash
python -m unittest discover tests -v
```

Offline, no network calls, no pytest dependency.

---

## Output

The layered `.md` checkpoints, the overlay's audit trail, and a final English-only PDF:


| File                              | Content                                                                      |
| --------------------------------- | ---------------------------------------------------------------------------- |
| `layer1_extraction.md`            | v0.32 — opens with the consolidated **input review** (rejections, reporting currency per fund + exit-liquidity exclusions, thin-US-exposure flags, Stage 0 advisories, style distribution), then per-fund extraction, universe size, out-of-scope |
| `layer2_screening.md`             | Overlap matrix, quality screen, data quality, liquidity labels + currency exclusions + homogeneity + thin-exposure count |
| `layer3_ranked_advice.md`         | Honest framing (bias once), top-15 watchlist cards, methodology disclosure   |
| `macro_checkpoint.md`             | v0.3 — central-bank-anchored macro/sector view, per-sentence attribution     |
| `expectations_checkpoint.md`      | v0.3 — per-stock best/avg/worst scenarios driven by the macro view           |
| `appendix3_consensus_warning.md`  | v0.3 — over-consensus & false-theme warning + fund-style remediation         |
| `important_notice_checkpoint.md`  | v0.33 — per-stock expectations bar + sentiment cycle, group-attributed and sourced; enters no score |
| `coherence.json`                  | v0.31 — per-stock audit: three factor readings, pairwise verdicts, tier delta, contradiction text |
| `financial_research_report.pdf`   | All of the above, assembled into a denser English PDF (18–26pp ceiling)      |

All checkpoint files — including `coherence.json` — are copied to `/mnt/user-data/outputs`
alongside the PDF (the container work dir is ephemeral and resets between sessions).
`coherence.json` is shipped because keeping the qualitative judgment out of the composite is
only worth something if a reader can check every demotion against the readings that produced it.

Intermediate v0.31 working files (`macro_factors.json`, `sector_logic.json`,
`etf_relative_strength.json`) stay in the work dir; they are inputs to the audit, and the audit
itself is what gets shipped.

---

## Key design decisions (v1 → v0.2 → v0.3 → v0.31 → v0.32 → v0.33)


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

1. **Ticker Symbol Compatibility Risk**: The system normalizes tickers to the `BRK.B` format (using dots). However, `yfinance` typically requires the `BRK-B` format (using hyphens) for specific share classes. Without proper transformation in `yfinance_provider.py`, the fallback mechanism may fail for these securities.
2. **ADR Data Coverage Risk**: `EDGARProvider` primarily retrieves data using `us-gaap` tags. Many foreign companies listed in the US (ADRs) report using `ifrs-full` (International Financial Reporting Standards) tags. This may cause EDGAR to fail in extracting fundamentals for ADRs, leading to total reliance on lower-confidence `yfinance` data.
3. **SEC API Quota Limits**: Although a 100ms throttle is implemented, SEC EDGAR has a hard quota of 600 requests per daily session. Processing a large unique universe or running multiple pipelines in a short window may trigger 429 errors or exhaust the quota.
4. **Sector-ETF proxy error (v0.31)**: an eleven-bucket industry map is coarser than a real sector classification, so a stock can be measured against an ETF that is only approximately its sector — a diversified conglomerate or an unusual ADR most of all. The mapping is deliberately conservative (`other` is left unmapped, producing "insufficient data" instead of a wrong proxy), but a *plausible-but-imprecise* bucket will still be used.
5. **Uncalibrated overlay bands (v0.31)**: the thresholds separating "outperforming / inline / lagging" (±5pp) and "sharp divergence" (±20pp) are round numbers, not fitted parameters — there is no backtest in this tool to fit them against. They exist to separate decisive moves from noise. This is why the overlay is capped at a single tier and can only demote: a wrong band costs one display tier on one stock, never a re-ordering.
6. **Structured macro fields are a lossy summary (v0.31)**: collapsing a central-bank corpus into one rate direction and one inflation direction discards nuance by design (regional divergence, forward guidance conditionality). The full narrative stays in `macro_checkpoint.md`; the structured fields exist only to make the coherence comparison mechanical and auditable.
7. **Reduced exit-liquidity coverage on non-USD input sets (v0.32)**: excluding non-USD AUM is correct but not free — an input set dominated by HKD share classes yields mostly `NAV-only` crowding figures, i.e. the v0.2 pure-weight discount with no days-to-liquidate information. This is a *stated* gap rather than a distorted number, and the exclusion count is reported in Layer 1 and Layer 2, but the exit-crowdedness signal is genuinely weaker on such a run.
8. **Currency normalisation depends on Stage 1a (v0.32)**: the gate reads the `currency` the LLM extracted. A factsheet that states its reporting currency only in a footnote, a share-class table, or an image the text layer does not carry will come through as `null` and be excluded — the safe direction, but a false exclusion. Only unambiguous spellings are mapped (`US$`, `HK$`, `Euro`, `RMB`); a bare `$` or `¥` resolves to `null` rather than a guess.
9. **The regional advisory is a title heuristic (v0.32)**: it reads the first few lines of page one, keeping lines that carry a fund-type word and no percentage figure. A factsheet whose title sits in an image, or whose text layer scrambles the first page, produces no advisory; a fund-of-funds row named after a region could produce a spurious one. Neither outcome affects the pipeline — Stage 1c is still the only thing that rejects a fund.
