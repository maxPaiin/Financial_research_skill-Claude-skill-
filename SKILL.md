---
name: financial-research
description: Trigger with /claude_skill_Financial_research. End-to-end quantitative research for stock-type mutual funds. Parses 7-11 HKMA-approved fund prospectus PDFs distributed through Hong Kong private banking channels, extracts US-listed equity holdings (including ADRs), screens for fundamental quality, ranks by a risk-aware composite signal (confidence-shrunk fundamental quality + style-diversity-weighted, exit-liquidity-aware consensus-with-crowding-discount), applies a demotion-only macro/sector/ETF coherence overlay to the display tiers, adds central-bank-anchored macro and per-stock scenario appendices, and outputs an English-only PDF report with a top-15 watchlist. Trigger when the user invokes /claude_skill_Financial_research, or uploads multiple fund prospectus PDFs (7-11) and asks for fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, or investment watchlist. Phrases include /claude_skill_Financial_research, fund analysis, holdings breakdown, fund prospectus analysis, "analyze these fund PDFs", 股票型基金分析, 基金研究. Prefer over generic PDF reading when 7+ fund PDFs are involved.
---

# Financial Research Skill v0.32

> **Every report must embed the disclaimer from `assets/disclaimer.md` verbatim (front and back).**
> v0.3 = risk-aware consensus, confidence-penalised quality, central-bank-anchored macro appendix, conservative-by-design. **v0.31 adds the coherence overlay** (macro factors + sector logic + ETF divergence) — **demotion-only**, capped at one tier, never touches rank or the composite. **v0.32 is a defect patch**: `currency` becomes a required Stage 1a field and only USD-reporting funds enter the days-to-liquidate aggregate (excluded, never FX-converted), plus two input-review warnings (thin US exposure, Stage 0 regional advisory). Safety-first: when in doubt, say less and rank lower.

---

## Pipeline orchestration

| Stage | Script / Actor | Reads | Writes |
|---|---|---|---|
| 0 | `validate_uploads.py <dir> --email <e> --out stage0_validation.json` | upload dir + email | stdout (errors) + `stage0_validation.json`; **regional advisories on stderr (G3, non-blocking)** |
| 1a | Claude (LLM) | each PDF (pdfplumber tables + LLM normalise) | `holdings.json` (one record per fund, incl. inferred `style` **and required `currency`**) |
| 1b–d | `extract_holdings.py --dedupe` | `holdings.json` | `holdings.json` (enriched; `style` preserved; **`currency` normalised to ISO-4217/null, `thin_us_exposure` flagged**) |
| 1e | `layer1_report.py --stage0` | `holdings.json`, `stage0_validation.json` | `layer1_extraction.md` (**opens with the consolidated input review, G4**) |
| 2a | `overlap_analysis.py` | `holdings.json` | `overlap.json` |
| 2b | `fetch_fundamentals.py --email <e>` | `holdings.json` | `fundamentals.json`, `unscored_tickers.json`, `data_provenance.json` |
| 2c | (inside 2b via `providers/resolver.py`) | EDGAR + yfinance per ticker | conflict entries appended to `data_provenance.json` |
| 2d | `quality_screen.py` | `holdings.json`, `fundamentals.json`, `unscored_tickers.json` | `screen_results.json` (+ `passed_industries` census) |
| **M1** | Claude + directed-fetch | `screen_results.json` → **post-screen-universe industries** (Fed/ECB/BoJ + official stats) | `macro_checkpoint.md` **+ `macro_factors.json`** (structured rate-path / inflation-trend fields) |
| **M1b** | Claude | `screen_results.json` industries + Layer-2 fundamentals | `sector_logic.json` (E2.2 three universal questions per industry) |
| 2e | `compute_scores.py` | `fundamentals.json`, `screen_results.json` | `scores_per_stock.json` (carries `adv`/`market_cap`) |
| 2f | `crowding_signal.py --holdings --fundamentals` | `overlap.json`, `holdings.json`, `fundamentals.json` | `crowding_signals.json` (days-to-liquidate **from USD-reporting funds only**, style-diversity, homogeneity, `input_review`) |
| 2g | `layer2_report.py` | overlap, screen, fundamentals, crowding | `layer2_screening.md` (liquidity labels + **currency exclusions** + homogeneity + **thin-exposure count**) |
| 3a | `build_rankings.py` | `scores_per_stock.json`, `crowding_signals.json`, `overlap.json` | `rankings.json` (low-anchor Q'') — **sole author of composite + rank** |
| **3a-bis-i** | `etf_relative_strength.py` | `rankings.json` (read-only), yfinance quotes | `etf_relative_strength.json` (RS vs SPY, fixed 3M/6M/12M) |
| **3a-bis** | `coherence_audit.py` | `rankings.json` (read-only), `macro_factors.json`, `sector_logic.json`, `etf_relative_strength.json` | `coherence.json` (side-car; **`rankings.json` untouched**) |
| 3b | Claude (LLM, 3 batches of 5) | `rankings.json`, `coherence.json` | rationale cards (name each stock's contradiction / explain its divergence) |
| 3c | Claude (LLM) | all Layer 2 outputs + `crowding_signals.json` | honest framing prose (HK-bias stated **once**) |
| 3d | `layer3_report.py --coherence` | `rankings.json`, `coherence.json`, framing, rationale | `layer3_ranked_advice.md` (tier grouping applies demotions; **rank display unchanged**) |
| M2 | Claude | `rankings.json`, `macro_checkpoint.md` | `expectations_checkpoint.md` (still post-rank, scoped to the final 15) |
| M3 | Claude | `crowding_signals.json` homogeneity + style dist + `input_review.thin_us_exposure` | `appendix3_consensus_warning.md` (**thin-exposure caveat when any accepted fund is thin; omitted entirely when none is**) |
| Mg | `check_checkpoints.py <work-dir>` | all checkpoints + `coherence.json` | stdout (gate; exit 1 on failure) |
| 4 | `build_report.py` | layer + appendix .md files | `financial_research_report.pdf` + checkpoint copies (incl. `coherence.json`) in outputs |

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

> **Stage 1a required fields (v0.32 G1.1):** `fund_name`, `asof`, the holdings
> table **and `currency`** — the fund's reporting currency for `total_aum`,
> normalised to an ISO-4217 code (`USD`, `HKD`, `EUR`, `JPY`, …). If the
> factsheet does not state one, write **`currency: null`** — **do not guess and
> never default to USD.** A bare `$` or `¥` is ambiguous and counts as unstated.
> Only USD-reporting funds enter the days-to-liquidate aggregate; the rest are
> excluded (never FX-converted) and fall through the existing NAV-only path.

> **Stage 0 regional advisory (v0.32 G3):** a title matching a regional marker
> (Asia / Europe / Japan / China / EM / Latin America / India / ASEAN, plus
> bilingual equivalents) raises an **advisory only**. It never halts, never
> rejects, never enters `errors`, and never changes the exit code or the 7–11
> file-count logic — Stage 1c remains the sole authority on rejection. Relay it
> to the user so they can swap the upload before the expensive Stage 1a parse.

> **Stage 1a fund-style inference (A3 / Appendix 3):** infer a coarse `style`
> per fund — one or more of `{value, growth, blend, income_dividend,
> sector_specific, small_mid_cap, region_tilt_non_us}` — from name keywords,
> stated benchmark, and top-holdings profile. Persist on each fund record. Build
> it once; it feeds both A3 and Appendix 3. See `references/macro_appendix.md`.

> **Stages M1–M3 (macro subsystem):** primary-first directed-fetch, cross-source
> corroboration **hard gate** (≥2 primary-tier sources per fact), per-sentence
> attribution. **v0.31: M1 runs after 2d (was after 3a) and is scoped to the
> post-screen universe's industries** — tiering depends on macro, so macro must
> exist before ranking; the top-15 anchor would be circular. M1's internal
> logic, sources and the C2 gate are **unchanged** — only its position moved.
> Full spec: `references/macro_appendix.md`. These stages add web retrieval and
> token load — the `.md` checkpoints let a long run survive context pressure.

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
| Stage 0 raises a regional advisory | **Do not stop.** Relay the advisory (it names the file), then continue to Stage 1a |
| Stage 1a: factsheet does not state a reporting currency | Write `currency: null`; **never default to USD**. The fund is kept; only its AUM is excluded downstream |
| Fund reports AUM in a non-USD currency | Exclude that AUM from the days-to-liquidate aggregate and say so. **Never FX-convert**; holdings still count for consensus/overlap/style |
| Accepted fund has 20–35% US weight | Flag `thin_us_exposure`; **accept in full, do not down-weight its consensus vote**; report it in Layer 1, Layer 2 and Appendix 3 |
| Stage 1a: pdfplumber finds no table grid | Fall back to flat-text + LLM; if still < 5 US holdings, reject that fund |
| Stage 1a: fund has < 5 US holdings or < 20% AUM weight | Reject that fund; continue if >= 7 remain; else halt |
| Post-rejection fund count < 7 | Halt; tell user which PDFs failed and why |
| EDGAR returns empty for ticker | Fall through to yfinance |
| yfinance also returns empty | Mark ticker as unscored; disclose in `layer2_screening.md` |
| No AUM / no ADV for a crowded name | Crowding falls back to NAV-only; label it (no crash) |
| Macro claim has only 1 primary-tier source | Do NOT write it (C2 hard gate) |
| No sector-ETF mapping / sparse macro read | Overlay records **"insufficient data"**, tier unchanged — never treat as coherent, never demote for it |
| yfinance quote fetch fails for a sector ETF | That sector's RS is insufficient-data; other sectors still audited; no crash |
| `coherence.json` absent at 3d | Run without `--coherence`: pure rank-slice tiers (v0.3 output) |
| Overlay would demote 2 tiers / promote | Impossible by construction; if seen, the implementation is wrong — `check_checkpoints.py` fails the run |
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
  macro_factors.json  sector_logic.json  etf_relative_strength.json  coherence.json   (v0.31)
  stage0_validation.json                                                              (v0.32)

/mnt/user-data/outputs/            (USER-VISIBLE — downloadable)
  financial_research_report.pdf
  <all checkpoint .md files + coherence.json, copied by build_report.py — D5>
```

The closing chat message points the user to `/mnt/user-data/outputs` for the PDF
**and** the checkpoint `.md` files; it must NOT claim the work dir persists.

---

## Key constraints (non-negotiable)

- US-listed equities only. ADRs in scope. Non-US primary listings dropped at Stage 1b.
- English-only in all output files. Chat may be bilingual.
- One ranking (top 15), three display tiers. No parallel strategies. No backtest.
- **The coherence overlay may only DEMOTE**, by at most **one tier per stock**, no matter how many pairs contradict. It never promotes, never changes rank, never touches the composite, `Q''` or `C`. `rankings.json` is **read-only** to it; its only output is `coherence.json`. Removing Stage 3a-bis must leave a runnable pipeline producing the v0.3 report.
- **The overlay is not a third scoring axis.** Weights stay **50/50**; a macro weight cannot be calibrated (no backtest exists), so none is written.
- ETF checks are **divergence detection, never confirmation**: relative strength **vs SPY** over **fixed 3M/6M/12M** windows. Divergence yields a flag **plus a required explanation**, not an automatic penalty.
- Sector logic uses the **three universal questions** (inputs / pricing power / return on capital), instantiated per industry — never blank-filled physical-supply-chain fields on software, financial or consumer names.
- **No industry-policy or company-level supply-chain claims anywhere in the output** (deferred; company supplier relationships are not in EDGAR's structured data and are the highest fabrication risk in the proposal).
- Do not fabricate data. If EDGAR and yfinance both fail, mark unscored.
- **Composite weights fixed at 50/50.** Quality half is low-anchor shrunk: `Q'' = c·Q + (1−c)·Q_low`, `Q_low = 10` and **must stay > 0**; applied to Q only, never re-percentiled.
- Crowding = exit-crowdedness (days-to-liquidate, simultaneous-exit assumption); each figure labelled liquidity-inclusive / NAV-only.
- **`currency` is required at Stage 1a and never defaulted.** Only `currency == "USD"` funds contribute AUM to `aggregate_position_usd`; non-USD and `null` are **excluded, never converted**. **No FX conversion may exist anywhere in the codebase** — the units are either identical or the input is set aside and labelled. There is no third path.
- **Thin US exposure (20–35% of AUM) is a warning, never a re-weighting.** Such funds are accepted in full and their consensus contribution is unchanged — `C`'s definition is locked, and exposure-weighting it belongs to a signal iteration, not a defect patch. Viability thresholds (≥5 holdings, ≥20% weight) are unchanged.
- **Stage 0 regional advisories are non-blocking**: never in `errors`, never affecting `ok`, the exit code, or the file-count logic.
- Consensus is style-diversity-weighted; stratified sampling is abandoned (sample too small; token budget) — disclose both reasons.
- Macro/expectations facts: ≥2 primary-tier sources (HARD gate), per-sentence attribution, no blacklist.
- Stage 3b: cards in 3 batches of 5, never all 15 at once.
- **HK-bias note stated ONCE** in the framing section — NOT on every card. High-crowding cards keep their per-card warning; front/back disclaimer intact.
- A valid SEC contact email is required before any EDGAR fetch (B1).
- Copyright: paraphrase fetched content, never reproduce; per-sentence attribution in the macro appendices.

---

*See `references/` for methodology, crowding signal (incl. the v0.32 currency
gate), providers, quality screen, honest framing, the macro/expectations
appendices, and the v0.31 coherence overlay. No formulas live in this file.*
