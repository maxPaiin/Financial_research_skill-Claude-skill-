# Financial Research Skill v0.2

End-to-end research pipeline for US equities held in HKMA-approved global funds distributed through Hong Kong private banking channels (Standard Chartered HK, Citi HK, and similar). Packaged as a Claude skill.

---

## Disclaimer

> **This skill produces an AI-generated analysis. The reports it generates must not be used as investment advice.**
> All rankings and scores are derived from publicly available data and statistical models. Past performance does not guarantee future results. Data sources (SEC EDGAR, yfinance, fund prospectus PDFs) may contain errors or delays. Any investment decision is solely the user's responsibility.

The verbatim disclaimer in `assets/disclaimer.md` is embedded into every generated PDF (front and back pages) and printed in the chat response.

---

## What this skill does

Given **7–11 HKMA-approved global fund prospectus PDFs**, the skill runs a three-layer pipeline:

1. **Layer 1 — Extraction**: validates uploads, extracts US-listed equity holdings (including ADRs) from each fund via LLM-assisted PDF parsing, filters out non-US listings, deduplicates across funds.
2. **Layer 2 — Overlap & Screen**: builds a cross-fund overlap matrix, fetches fundamentals from SEC EDGAR (true PIT) with yfinance fallback, applies a quality screen (PASS/FAIL), computes a fundamental quality percentile score, and computes a consensus-with-crowding-discount signal.
3. **Layer 3 — Ranking & Advice**: composite-ranks the passed universe (50% fundamental quality + 50% crowding-discounted consensus), selects the top 15 stocks, organizes them into Tier A/B/C, and generates per-stock rationale cards with honest framing.

**Output**: three layered `.md` files and a single English-only PDF report (18–26 pages).

---

## What this skill is NOT

- **Not an alpha tool.** Rankings reflect HK distribution-channel preferences, not the global market.
- **Not a portfolio constructor.** Output is a ranked watchlist; no allocation weights.
- **Not a backtest engine.** Backtesting was removed in v0.2 (it produced misleading results given the small, biased input set).
- **Not a bilingual tool.** All output files are English-only.
- **Not a three-strategies tool.** One ranking, three display tiers.

---

## When the skill triggers

| Trigger |
|---|
| User uploads 7–11 fund prospectus PDFs and asks for analysis. |
| Phrases: *fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, fund prospectus analysis*, "analyze these fund PDFs". |
| Chinese phrases: 股票型基金分析, 基金研究, 個股評分, 多基金比較. |

If fewer than 7 PDFs are supplied, validation stops the pipeline and asks the user to resubmit.

---

## Pipeline overview

| Layer | Stages | Key scripts |
|---|---|---|
| Layer 1 — Extraction | 0–1e | `validate_uploads.py`, `extract_holdings.py`, `layer1_report.py` |
| Layer 2 — Overlap & Screen | 2a–2g | `overlap_analysis.py`, `providers/registry.py`, `quality_screen.py`, `compute_scores.py`, `crowding_signal.py`, `layer2_report.py` |
| Layer 3 — Ranking & Advice | 3a–3d + PDF | `build_rankings.py`, `layer3_report.py`, `build_report.py` |

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
│   ├── crowding_signal.md            # Signal formula and interpretation
│   ├── providers.md                  # Provider routing, EDGAR contract, confidence
│   └── honest_framing.md             # Framing template for Layer 3
└── scripts/                          # Deterministic computation (no LLM calls)
    ├── validate_uploads.py
    ├── extract_holdings.py
    ├── overlap_analysis.py
    ├── compute_scores.py
    ├── aggregate_funds.py
    ├── build_rankings.py
    ├── build_report.py
    ├── quality_screen.py
    ├── crowding_signal.py
    ├── layer1_report.py
    ├── layer2_report.py
    ├── layer3_report.py
    └── providers/
        ├── __init__.py
        ├── base.py                   # DataPoint, FundamentalsRecord, ABCs
        ├── edgar_provider.py         # True-PIT EDGAR fetcher (10-K + 20-F)
        ├── yfinance_provider.py      # Degraded-PIT fallback (sole yfinance import)
        ├── pdf_snapshot_provider.py  # Holdings from Stage 1 extraction
        ├── registry.py               # Provider routing orchestration
        ├── resolver.py               # Multi-source conflict resolution
        └── industry_map.py           # US-only industry bucket constants
```

---

## Installation

```bash
pip install -r requirements.txt --break-system-packages
```

No API keys required. EDGAR access uses an anonymous User-Agent hardcoded per SEC fair-use policy.

---

## Usage

This is a Claude skill — upload 7–11 HKMA-approved fund factsheet PDFs and ask Claude for fund analysis. The skill runs the full pipeline and surfaces a downloadable PDF report.

For local development, individual scripts can be run directly:

```bash
# Stage 0 — validate
python scripts/validate_uploads.py /path/to/uploads

# Stage 1b-d — filter and dedupe (after Claude writes holdings.json at Stage 1a)
python scripts/extract_holdings.py --input /home/claude/work/holdings.json --dedupe

# Stage 1e — Layer 1 report
python scripts/layer1_report.py --holdings /home/claude/work/holdings.json

# Stage 2a — overlap matrix
python scripts/overlap_analysis.py \
  --holdings /home/claude/work/holdings.json \
  --out /home/claude/work/overlap.json

# Stage 2d — quality screen (after fundamentals.json is written)
# Stage 2e — fundamental quality scores
python scripts/compute_scores.py \
  --fundamentals /home/claude/work/fundamentals.json \
  --screen /home/claude/work/screen_results.json \
  --out /home/claude/work/scores_per_stock.json

# Stage 3a — composite ranking
python scripts/build_rankings.py \
  --scores /home/claude/work/scores_per_stock.json \
  --crowding /home/claude/work/crowding_signals.json \
  --overlap /home/claude/work/overlap.json \
  --out /home/claude/work/rankings.json

# Stage 4 — PDF assembly
python scripts/build_report.py \
  --work-dir /home/claude/work/ \
  --out /mnt/user-data/outputs/financial_research_report.pdf
```

---

## Output

Three downloadable `.md` files plus a final English-only PDF:

| File | Content |
|---|---|
| `layer1_extraction.md` | Per-fund extraction summary, universe size, out-of-scope tickers |
| `layer2_screening.md` | Overlap matrix, quality screen results (pass + fail disclosed), data quality |
| `layer3_ranked_advice.md` | Honest framing, top-15 watchlist with rationale cards, methodology |
| `financial_research_report.pdf` | All of the above, assembled into 18–26 page English PDF |

---

## Key design decisions (v0.2 vs v1)

| Decision | v1 | v0.2 |
|---|---|---|
| Scope | Multi-market, claimed alpha | US equities, honestly scoped to HK channel |
| Strategies | 3 parallel (Growth / Conservative / Risk-avoidance) | 1 ranking, 3 display tiers |
| Backtest | Monthly-rebalanced with CAGR/Sharpe/MDD | Removed (misleading given inputs) |
| Output language | Bilingual (EN + 中文) | English-only |
| Data source | yfinance + FRED only | EDGAR (PIT, conf 0.9) + yfinance fallback (conf 0.5) |
| Quality metric | Continuous score (industry + growth + quality_value) | Binary screen + single ROE percentile rank |

---

## Dependencies

- `pypdf >= 4.0` — PDF parsing
- `yfinance >= 0.2.40` — market data fallback (only imported in `providers/yfinance_provider.py`)
- `requests >= 2.31` — EDGAR HTTP calls
- `pandas >= 2.0`, `numpy >= 1.24`
- `reportlab >= 4.0` — PDF generation (English layout, no CJK font needed)
- `matplotlib >= 3.7` — chart embedding

---

## Disclaimer (repeat)

> **The reports produced by this skill are AI-generated analyses and must not be used as investment advice.**
> Past performance does not guarantee future results. Data sources may contain errors or delays. Any investment decision made based on these reports is solely the user's responsibility.
