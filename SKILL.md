---
name: financial-research
description: End-to-end quantitative research for stock-type mutual funds. Parses 7-11 HKMA-approved fund prospectus PDFs distributed through Hong Kong private banking channels, extracts US-listed equity holdings (including ADRs), screens for fundamental quality, ranks by a composite signal (fundamental quality + consensus-with-crowding-discount), and outputs an English-only PDF report with a top-15 watchlist. Trigger when the user uploads multiple fund prospectus PDFs (7-11) and asks for fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, or investment watchlist. Phrases include fund analysis, holdings breakdown, fund prospectus analysis, "analyze these fund PDFs", 股票型基金分析, 基金研究. Prefer over generic PDF reading when 7+ fund PDFs are involved.
---

# Financial Research Skill v0.2

> **Every report must embed the disclaimer from `assets/disclaimer.md` verbatim (front and back).**

---

## Pipeline orchestration

| Stage | Script / Actor | Reads | Writes |
|---|---|---|---|
| 0 | `validate_uploads.py` | upload dir | stdout (errors) |
| 1a | Claude (LLM) | each PDF | `holdings.json` (one record per fund) |
| 1b–d | `extract_holdings.py --dedupe` | `holdings.json` | `holdings.json` (enriched) |
| 1e | `layer1_report.py` | `holdings.json` | `layer1_extraction.md` |
| 2a | `overlap_analysis.py` | `holdings.json` | `overlap.json` |
| 2b | `providers/registry.py` (via Claude) | `holdings.json` | `fundamentals.json` |
| 2c | `providers/resolver.py` (auto) | multi-source | `data_provenance.json` |
| 2d | `quality_screen.py` | `fundamentals.json` | `screen_results.json` |
| 2e | `compute_scores.py` | `fundamentals.json`, `screen_results.json` | `scores_per_stock.json` |
| 2f | `crowding_signal.py` (via Claude) | `overlap.json` | `crowding_signals.json` |
| 2g | `layer2_report.py` | overlap, screen, fundamentals, crowding | `layer2_screening.md` |
| 3a | `build_rankings.py` | `scores_per_stock.json`, `crowding_signals.json`, `overlap.json` | `rankings.json` |
| 3b | Claude (LLM, 3 batches of 5) | `rankings.json` | rationale cards |
| 3c | Claude (LLM) | all Layer 2 outputs | honest framing prose |
| 3d | `layer3_report.py` | `rankings.json`, framing, rationale | `layer3_ranked_advice.md` |
| 4 | `build_report.py` | three layer .md files | `financial_research_report.pdf` |

---

## Error decision tree

| Symptom | Action |
|---|---|
| Stage 0 fails (wrong PDF count, unreadable) | Stop; print educational guidance from `validate_uploads.py`; ask user to resubmit |
| Stage 1a: fund has < 5 US holdings or < 20% AUM weight | Reject that fund; continue if >= 7 remain; else halt |
| Post-rejection fund count < 7 | Halt; tell user which PDFs failed and why |
| EDGAR returns empty for ticker | Fall through to yfinance |
| yfinance also returns empty | Mark ticker as unscored; disclose in `layer2_screening.md` |
| Stage 3b batch fails | Retry that batch once; if still failing, write placeholder card with data only |
| PDF assembly (Stage 4) fails | Surface the three layer .md files directly; explain reportlab issue |

---

## Output contract

After a successful run, these files exist:

```
/home/claude/work/
  layer1_extraction.md       # Layer 1 summary
  layer2_screening.md        # Overlap + quality screen
  layer3_ranked_advice.md    # Top-15 watchlist + methodology
  fundamentals.json
  overlap.json
  screen_results.json
  scores_per_stock.json
  crowding_signals.json
  rankings.json
  data_provenance.json       # Conflict log from resolver

/mnt/user-data/outputs/
  financial_research_report.pdf
```

---

## Key constraints (non-negotiable)

- US-listed equities only. ADRs in scope. Non-US primary listings dropped at Stage 1b.
- English-only in all output files. Chat may be bilingual.
- One ranking (top 15). No parallel strategies. No backtest.
- Do not fabricate data. If EDGAR and yfinance both fail, mark unscored.
- Stage 3b: generate cards in 3 batches of 5, never all 15 at once.
- Disclaimer from `assets/disclaimer.md` must appear verbatim on PDF pages 2 and last.
- Bias note must appear on every ranked stock card.

---

*See `references/` for methodology details. No formulas live in this file.*
