---
name: financial-research
description: End-to-end quantitative research for stock-type mutual funds. Parses 7-11 HKMA-approved fund prospectus PDFs distributed through Hong Kong private banking channels, extracts US-listed equity holdings (including ADRs), screens for fundamental quality, ranks by a risk-aware composite signal (confidence-shrunk fundamental quality + style-diversity-weighted, exit-liquidity-aware consensus-with-crowding-discount), adds central-bank-anchored macro and per-stock scenario appendices, and outputs an English-only PDF report with a top-15 watchlist. Trigger when the user uploads multiple fund prospectus PDFs (7-11) and asks for fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, or investment watchlist. Phrases include fund analysis, holdings breakdown, fund prospectus analysis, "analyze these fund PDFs", 股票型基金分析, 基金研究. Prefer over generic PDF reading when 7+ fund PDFs are involved.
---

# Financial Research Skill v0.3

> **Every report must embed the disclaimer from `assets/disclaimer.md` verbatim (front and back).**
> v0.3 = risk-aware consensus, confidence-penalised quality, central-bank-anchored macro appendix, conservative-by-design. Safety-first: when in doubt, say less and rank lower.

---

## Pipeline orchestration

| Stage | Script / Actor | Reads | Writes |
|---|---|---|---|
| 0 | `validate_uploads.py <dir> --email <e>` | upload dir + email | stdout (errors) |
| 1a | Claude (LLM) | each PDF (pdfplumber tables + LLM normalise) | `holdings.json` (one record per fund, incl. inferred `style`) |
| 1b–d | `extract_holdings.py --dedupe` | `holdings.json` | `holdings.json` (enriched; `style` preserved) |
| 1e | `layer1_report.py` | `holdings.json` | `layer1_extraction.md` |
| 2a | `overlap_analysis.py` | `holdings.json` | `overlap.json` |
| 2b | `fetch_fundamentals.py --email <e>` | `holdings.json` | `fundamentals.json`, `unscored_tickers.json`, `data_provenance.json` |
| 2c | (inside 2b via `providers/resolver.py`) | EDGAR + yfinance per ticker | conflict entries appended to `data_provenance.json` |
| 2d | `quality_screen.py` | `holdings.json`, `fundamentals.json`, `unscored_tickers.json` | `screen_results.json` |
| 2e | `compute_scores.py` | `fundamentals.json`, `screen_results.json` | `scores_per_stock.json` (carries `adv`/`market_cap`) |
| 2f | `crowding_signal.py --holdings --fundamentals` | `overlap.json`, `holdings.json`, `fundamentals.json` | `crowding_signals.json` (days-to-liquidate, style-diversity, homogeneity) |
| 2g | `layer2_report.py` | overlap, screen, fundamentals, crowding | `layer2_screening.md` (liquidity labels + homogeneity state) |
| 3a | `build_rankings.py` | `scores_per_stock.json`, `crowding_signals.json`, `overlap.json` | `rankings.json` (low-anchor Q'') |
| 3b | Claude (LLM, 3 batches of 5) | `rankings.json` | rationale cards |
| 3c | Claude (LLM) | all Layer 2 outputs + `crowding_signals.json` | honest framing prose (HK-bias stated **once**) |
| 3d | `layer3_report.py` | `rankings.json`, framing, rationale | `layer3_ranked_advice.md` |
| M1 | Claude + directed-fetch | top-15 industries (Fed/ECB/BoJ + official stats) | `macro_checkpoint.md` |
| M2 | Claude | `rankings.json`, `macro_checkpoint.md` | `expectations_checkpoint.md` |
| M3 | Claude | `crowding_signals.json` homogeneity + style dist | `appendix3_consensus_warning.md` |
| Mg | `check_checkpoints.py <work-dir>` | all checkpoints | stdout (gate; exit 1 on failure) |
| 4 | `build_report.py` | layer + appendix .md files | `financial_research_report.pdf` + checkpoint .md copies in outputs |

> **Stage 2c (multi-source resolution):** Runs implicitly inside Stage 2b. For
> each ticker EDGAR and yfinance are consulted; overlapping fields are merged via
> `providers/resolver.py` (first source wins on agreement; higher-confidence wins
> on disagreement, confidence halved when diff > 20%). Conflicts → `data_provenance.json`.

> **Stage 0 email gate (B1):** SEC requires a contact email in the EDGAR
> User-Agent; without it EDGAR returns 403. In-conversation, ask the user for a
> usable email and tell them **why** (403 without it) and the **privacy**
> position (placed ONLY in the SEC request header; not stored or sent anywhere
> else). Pass it via `--email` to `validate_uploads.py` and `fetch_fundamentals.py`
> (or set `EDGAR_CONTACT_EMAIL`). No valid email → **halt**.

> **Stage 1a fund-style inference (A3 / Appendix 3):** infer a coarse `style`
> per fund — one or more of `{value, growth, blend, income_dividend,
> sector_specific, small_mid_cap, region_tilt_non_us}` — from name keywords,
> stated benchmark, and top-holdings profile. Persist on each fund record. Build
> it once; it feeds both A3 and Appendix 3. See `references/macro_appendix.md`.

> **Stages M1–M3 (macro subsystem):** primary-first directed-fetch, cross-source
> corroboration **hard gate** (≥2 primary-tier sources per fact), per-sentence
> attribution, sector scope bounded to the top-15 industries. Full spec:
> `references/macro_appendix.md`. These stages add web retrieval and token load —
> the `.md` checkpoints let a long run survive context pressure.

---

## Error decision tree

| Symptom | Action |
|---|---|
| Stage 0: no/invalid email | Halt; print the why+privacy message; ask user to supply an email |
| Stage 0 fails (wrong PDF count, unreadable) | Stop; print guidance from `validate_uploads.py`; ask user to resubmit |
| Stage 1a: pdfplumber finds no table grid | Fall back to flat-text + LLM; if still < 5 US holdings, reject that fund |
| Stage 1a: fund has < 5 US holdings or < 20% AUM weight | Reject that fund; continue if >= 7 remain; else halt |
| Post-rejection fund count < 7 | Halt; tell user which PDFs failed and why |
| EDGAR returns empty for ticker | Fall through to yfinance |
| yfinance also returns empty | Mark ticker as unscored; disclose in `layer2_screening.md` |
| No AUM / no ADV for a crowded name | Crowding falls back to NAV-only; label it (no crash) |
| Macro claim has only 1 primary-tier source | Do NOT write it (C2 hard gate) |
| `check_checkpoints.py` exits 1 | Fix the flagged checkpoint before building the PDF |
| Stage 3b batch fails | Retry that batch once; else write placeholder card with data only |
| PDF assembly (Stage 4) fails | Surface the layer .md files directly; explain reportlab issue |

---

## Output contract

```
/home/claude/work/                 (EPHEMERAL — resets between sessions)
  layer1_extraction.md  layer2_screening.md  layer3_ranked_advice.md
  macro_checkpoint.md   expectations_checkpoint.md  appendix3_consensus_warning.md
  holdings.json  overlap.json  fundamentals.json  unscored_tickers.json
  data_provenance.json  screen_results.json  scores_per_stock.json
  crowding_signals.json  rankings.json

/mnt/user-data/outputs/            (USER-VISIBLE — downloadable)
  financial_research_report.pdf
  <all checkpoint .md files, copied by build_report.py — D5>
```

The closing chat message points the user to `/mnt/user-data/outputs` for the PDF
**and** the checkpoint `.md` files; it must NOT claim the work dir persists.

---

## Key constraints (non-negotiable)

- US-listed equities only. ADRs in scope. Non-US primary listings dropped at Stage 1b.
- English-only in all output files. Chat may be bilingual.
- One ranking (top 15), three display tiers. No parallel strategies. No backtest.
- Do not fabricate data. If EDGAR and yfinance both fail, mark unscored.
- **Composite weights fixed at 50/50.** Quality half is low-anchor shrunk: `Q'' = c·Q + (1−c)·Q_low`, `Q_low = 10` and **must stay > 0**; applied to Q only, never re-percentiled.
- Crowding = exit-crowdedness (days-to-liquidate, simultaneous-exit assumption); each figure labelled liquidity-inclusive / NAV-only.
- Consensus is style-diversity-weighted; stratified sampling is abandoned (sample too small; token budget) — disclose both reasons.
- Macro/expectations facts: ≥2 primary-tier sources (HARD gate), per-sentence attribution, no blacklist.
- Stage 3b: cards in 3 batches of 5, never all 15 at once.
- **HK-bias note stated ONCE** in the framing section — NOT on every card. High-crowding cards keep their per-card warning; front/back disclaimer intact.
- A valid SEC contact email is required before any EDGAR fetch (B1).
- Copyright: paraphrase fetched content, never reproduce; per-sentence attribution in the macro appendices.

---

*See `references/` for methodology, crowding signal, providers, quality screen,
honest framing, and the macro/expectations appendices. No formulas live in this file.*
