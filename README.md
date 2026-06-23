> **Trigger keyword:** `/claude_skill_Financial_research`

# Financial Research Skill v0.3

> **v0.3 (current)** — risk-aware consensus, confidence-penalised quality, central-bank-anchored
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
4. **Macro appendices (v0.3)**: central-bank-anchored macro/sector view, per-stock best/avg/worst scenarios, and an over-consensus / fund-style remediation appendix — all under a hard ≥2-primary-tier source-corroboration gate.

**Output**: the layered `.md` checkpoints and a single English-only PDF report, all copied to the user-visible outputs directory.

---

## What this skill is NOT

- **Not an alpha tool.** Rankings reflect HK distribution-channel preferences, not the global market.
- **Not a portfolio constructor.** Output is a ranked watchlist; no allocation weights.
- **Not a backtest engine.** Backtesting was removed in v0.2 (it produced misleading results given the small, biased input set).
- **Not a bilingual tool.** All output files are English-only.
- **Not a three-strategies tool.** One ranking, three display tiers.

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

### Level 2 — Per-fund content (Stage 1a, LLM extraction)

Claude reads each PDF and writes one record per fund into `holdings.json`. For that to succeed, each PDF must surface the following:


| Field                   | Required?   | Why it matters                                                                               |
| ----------------------- | ----------- | -------------------------------------------------------------------------------------------- |
| Fund name               | yes         | Identifies the fund in every downstream report.                                              |
| Issuer                  | recommended | Shown in Layer 1 / 2 summaries.                                                              |
| Reporting date (`asof`) | yes         | Per-fund snapshot date; appears in Layer 1 and PIT tracking.                                 |
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
| Layer 3 — Ranking & Advice | 3a–3d + PDF | `build_rankings.py`, `layer3_report.py`, `build_report.py`                                                                         |

Full orchestration logic and error recovery rules: [`SKILL.md`](./SKILL.md).

---

## Project structure

```
.
├── SKILL.md                          # Skill orchestration (≤150 lines)
├── README.md
├── requirements.txt
├── assets/
│   └── disclaimer.md                 # English-only disclaimer (verbatim in every PDF)
├── references/                       # Methodology readers (no executable code)
│   ├── methodology.md                # What the skill does and does not do
│   ├── quality_screen.md             # Screen criteria and rationale
│   ├── crowding_signal.md            # Signal formula (A2 days-to-liquidate, A3 diversity)
│   ├── providers.md                  # Provider routing, EDGAR contract (B1 email), confidence
│   ├── honest_framing.md             # Framing template for Layer 3 (bias stated once)
│   └── macro_appendix.md             # v0.3 macro/expectations appendices + source gate
├── scripts/                          # Deterministic computation (no LLM calls)
│   ├── validate_uploads.py
│   ├── extract_holdings.py
│   ├── overlap_analysis.py
│   ├── fetch_fundamentals.py         # Stage 2b: EDGAR + yfinance → fundamentals.json
│   ├── compute_scores.py
│   ├── aggregate_funds.py
│   ├── build_rankings.py
│   ├── build_report.py
│   ├── quality_screen.py
│   ├── crowding_signal.py            # A2 days-to-liquidate + A3 style-diversity / homogeneity
│   ├── check_checkpoints.py          # v0.3 D4 deterministic checkpoint review gate
│   ├── layer1_report.py
│   ├── layer2_report.py
│   ├── layer3_report.py
│   └── providers/
│       ├── __init__.py
│       ├── base.py                   # DataPoint, FundamentalsRecord, ABCs
│       ├── edgar_provider.py         # True-PIT EDGAR fetcher (10-K + 20-F)
│       ├── yfinance_provider.py      # Degraded-PIT fallback (sole yfinance import)
│       ├── registry.py               # Provider routing + multi-source merge
│       ├── resolver.py               # Conflict resolution + data_provenance log
│       └── industry_map.py           # US-only industry bucket constants
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
# Stage 0 — validate (+ SEC email gate)
python scripts/validate_uploads.py /path/to/uploads --email you@example.com

# Stage 1b-d — filter and dedupe (after Claude writes holdings.json at Stage 1a)
python scripts/extract_holdings.py --input /home/claude/work/holdings.json --dedupe

# Stage 1e — Layer 1 report
python scripts/layer1_report.py --holdings /home/claude/work/holdings.json

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

# Stage 3a — composite ranking
python scripts/build_rankings.py \
  --scores /home/claude/work/scores_per_stock.json \
  --crowding /home/claude/work/crowding_signals.json \
  --overlap /home/claude/work/overlap.json \
  --out /home/claude/work/rankings.json

# Macro gate — deterministic checkpoint review (v0.3 D4)
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

Three downloadable `.md` files plus a final English-only PDF:


| File                              | Content                                                                      |
| --------------------------------- | ---------------------------------------------------------------------------- |
| `layer1_extraction.md`            | Per-fund extraction summary (with style labels), universe size, out-of-scope |
| `layer2_screening.md`             | Overlap matrix, quality screen, data quality, liquidity labels + homogeneity |
| `layer3_ranked_advice.md`         | Honest framing (bias once), top-15 watchlist cards, methodology disclosure   |
| `macro_checkpoint.md`             | v0.3 — central-bank-anchored macro/sector view, per-sentence attribution     |
| `expectations_checkpoint.md`      | v0.3 — per-stock best/avg/worst scenarios driven by the macro view           |
| `appendix3_consensus_warning.md`  | v0.3 — over-consensus & false-theme warning + fund-style remediation         |
| `financial_research_report.pdf`   | All of the above, assembled into a denser English PDF (18–26pp ceiling)      |

All checkpoint `.md` files are copied to `/mnt/user-data/outputs` alongside the PDF (the
container work dir is ephemeral and resets between sessions).

---

## Key design decisions (v1 → v0.2 → v0.3)


| Decision        | v1                                                   | v0.2                                                 | v0.3                                                              |
| --------------- | ---------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------- |
| Scope           | Multi-market, claimed alpha                          | US equities, honestly scoped to HK channel           | unchanged                                                         |
| Strategies      | 3 parallel (Growth / Conservative / Risk-avoidance)  | 1 ranking, 3 display tiers                           | unchanged                                                         |
| Backtest        | Monthly-rebalanced with CAGR/Sharpe/MDD              | Removed (misleading given inputs)                    | unchanged (still none)                                            |
| Output language | Bilingual (English + Chinese)                        | English-only                                         | unchanged                                                         |
| Data source     | yfinance + FRED only                                 | EDGAR (conf 0.9) + yfinance (conf 0.5)               | + central-bank directed-fetch (Fed/ECB/BoJ) for macro appendix    |
| Quality metric  | Continuous score (industry + growth + quality_value) | Binary screen + single ROE percentile rank           | + low-anchor confidence shrinkage `Q'' = c·Q + (1−c)·10`          |
| Consensus       | Raw count                                            | Consensus-with-crowding (NAV-share discount)         | Style-diversity-weighted + exit-crowdedness (days-to-liquidate)   |
| EDGAR UA        | n/a                                                  | Hardcoded, no email (would 403)                      | User-supplied contact email, gated at Stage 0 (B1)               |

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
