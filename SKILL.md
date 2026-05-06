---
name: financial-research
description: 股票型基金量化分析全流程 / End-to-end quantitative research for stock-type mutual funds. Parses 7-11 fund prospectus PDFs, extracts holdings, fetches macro/fundamental data via yfinance + FRED, runs multi-factor scoring (industry, growth & EPS revision, quality & value), aggregates to fund level, analyzes cross-fund overlap and concentration risk, runs monthly-rebalanced backtest (CAGR / Sharpe / Max Drawdown / Win Rate) with stop-loss and 30% industry cap, produces Growth / Conservative / Risk-avoidance recommendations across 1y/3y/5y horizons, outputs a bilingual PDF report. Trigger when the user uploads multiple stock fund prospectuses (7-11 PDFs) and asks for fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, portfolio backtest, or investment recommendations. Phrases include 股票型基金分析, 基金研究, 個股評分, 基金回測, multi-fund report, fund prospectus analysis, or "analyze these fund PDFs". Prefer over generic PDF reading when 7+ fund PDFs are involved.
---

# Financial Research Skill / 金融分析技能

End-to-end research pipeline for stock-type mutual funds. Bilingual (中英) by default.

> **Critical:** Every report must include the disclaimer in `assets/disclaimer.md`.
> 每份報告都必須附上 `assets/disclaimer.md` 中的免責聲明。

---

## When this skill applies / 適用情境

User uploads **7 to 11 stock-type fund prospectus PDFs** and wants quantitative analysis.
用戶上傳 **7–11 份股票型基金產品文件 PDF**,要求量化分析。

This skill **depends on the `pdf` skill** for parsing — read `/mnt/skills/public/pdf/SKILL.md` before any PDF operation.
本 skill **依賴 `pdf` skill** 進行解析,任何 PDF 操作前先讀 `/mnt/skills/public/pdf/SKILL.md`。

---

## Pipeline overview / 流程總覽

```
Stage 0  Validate uploads          → scripts/validate_uploads.py
Stage 1  Extract holdings (LLM)    → SKILL.md §1, scripts/extract_holdings.py
Stage 2  Fetch market & macro data → scripts/fetch_market_data.py + fetch_macro_data.py
Stage 3  Per-stock scoring         → scripts/compute_scores.py + references/scoring_playbook.md
Stage 4  Strategy composite scores → scripts/strategy_weights.py + references/strategy_weights.md
Stage 5  Fund-level aggregation    → scripts/aggregate_funds.py
Stage 6  Risk & overlap analysis   → scripts/overlap_analysis.py
Stage 7  Rankings                  → scripts/build_rankings.py
Stage 8  Backtest                  → scripts/backtest.py + references/backtest_methodology.md
Stage 9  Forward investment view   → SKILL.md §9 (LLM synthesis)
Stage 10 PDF report                → scripts/build_report.py + references/report_template.md
```

All intermediate JSON is written to `/home/claude/work/` so each stage reads the previous stage's output. No need to keep large data structures in conversation context.
所有中間結果寫入 `/home/claude/work/`,後一階段讀前一階段的輸出,避免資料常駐對話上下文。

---

## Stage 0 — Validate uploads / 驗證輸入

```bash
python scripts/validate_uploads.py /mnt/user-data/uploads
```

The script checks:
1. Count of `.pdf` files is in `[7, 11]` (inclusive of 7, exclusive of 12).
2. Each PDF opens with `pypdf` and yields ≥ 1 page of extractable text.
3. Each PDF contains at least one of the keywords (case-insensitive): `holdings | portfolio | 持倉 | 持股 | 投資組合`.

**If validation fails, STOP and ask the user to resubmit.** Do not proceed silently.
**驗證失敗即停止,要求用戶重新提交。**

Failure messages should specify:
- Wrong count: `Got N PDFs; need 7–11. / 收到 N 份,須為 7–11 份。`
- Unreadable: `File X cannot be parsed (encrypted? scanned-only?). / 檔案 X 無法解析。`
- Not a fund document: `File X does not look like a fund prospectus. / 檔案 X 不像基金產品文件。`

---

## Stage 1 — Extract holdings / 抽取持倉

For each validated PDF:

1. Read full text using `pypdf` (see `pdf` skill for advanced cases like scanned PDFs).
2. Identify the holdings section (variants: "Top 10 Holdings", "投資組合", "持倉明細", "Portfolio Composition").
3. Parse each holding into a record:
   ```json
   {
     "ticker": "AAPL",
     "name": "Apple Inc.",
     "weight": 0.0723,
     "market": "US"
   }
   ```
4. Also extract fund metadata: `fund_name`, `fund_type` (e.g., 科技類 / Technology), `total_assets`, `currency`, `reporting_date`.

**LLM judgement is needed here** because holdings tables vary widely. Do NOT try to regex this — read the extracted text, locate the holdings section, transcribe it into JSON.

Output: `/home/claude/work/holdings.json` with shape:
```json
{
  "funds": [
    {
      "fund_id": "F1",
      "fund_name": "...",
      "fund_type": "...",
      "currency": "USD",
      "reporting_date": "2025-Q4",
      "holdings": [{...}, ...]
    },
    ...
  ]
}
```

After writing the JSON, run:
```bash
python scripts/extract_holdings.py --input /home/claude/work/holdings.json --dedupe
```
This adds a `unique_universe` array (deduped tickers across all funds, with which-funds-hold-it tracking).

---

## Stage 2 — Fetch market & macro data / 取得行情與宏觀資料

```bash
python scripts/fetch_market_data.py  --universe /home/claude/work/holdings.json --out /home/claude/work/market.json
python scripts/fetch_macro_data.py   --out /home/claude/work/macro.json
```

`fetch_market_data.py` uses **yfinance** to pull, for each unique ticker:
- Current price, market_cap, industry, sector
- Trailing PE, PBR, EV/EBITDA, ROE
- EPS estimate (current and prior period — for revision calc)
- Industry ETF mapping + last-12m return
- Past 6m return (for optional momentum signal)

`fetch_macro_data.py` uses **yfinance + FRED** to pull:
- Interest rate (10Y treasury, FED funds)
- Inflation (CPI YoY)
- FX (DXY, USD/JPY for Japanese holdings, etc.)
- Index returns (SPY, QQQ, etc. as benchmarks)

**Caching**: scripts cache to `/home/claude/work/cache/` keyed by ticker+date. Re-running within the same day is free.
**快取**: 同日重跑不重新呼叫 API。

If a ticker is unmappable (e.g., obscure HK or TW listing), the script writes `{"status": "missing", "reason": "..."}` instead of failing. Stage 3 will mark that stock as `score: null` and flag it in the report.

> **API setup**: `pip install yfinance fredapi pandas pandas-datareader --break-system-packages`. FRED requires a free API key in `FRED_API_KEY` env var; if absent, `fetch_macro_data.py` falls back to yfinance proxies and notes the degradation in `macro.json`.

---

## Stage 3 — Per-stock scoring / 個股評分

```bash
python scripts/compute_scores.py \
  --market /home/claude/work/market.json \
  --macro  /home/claude/work/macro.json \
  --out    /home/claude/work/scores_per_stock.json
```

This implements the formulas in `references/scoring_playbook.md`. Each stock gets:
- `industry_score` (0–100)
- `growth_score` (0–100)
- `quality_value_score` (0–100)
- `momentum_score` (0–100, optional)
- raw inputs preserved for audit (PE, PBR, EV/EBITDA, ROE, EPS revision, etc.)

**Read `references/scoring_playbook.md` if you need to debug a specific stock's score** — it has the full formula set with worked examples.

---

## Stage 4 — Strategy composite scores / 策略複合評分

```bash
python scripts/strategy_weights.py \
  --scores /home/claude/work/scores_per_stock.json \
  --out    /home/claude/work/scores_strategies.json
```

Applies three weight schemes to produce three composite scores per stock:

| Strategy | industry | growth | quality_value | + momentum |
|---|---:|---:|---:|---:|
| Growth | 0.20 | 0.60 | 0.20 | +0.10 |
| Conservative | 0.30 | 0.20 | 0.50 | 0 |
| Risk-avoidance | 0.40 | 0.10 | 0.50 | -industry_concentration penalty |

Full rationale and tuning guidance in `references/strategy_weights.md`.

---

## Stage 5 — Fund-level aggregation / 基金層匯總

```bash
python scripts/aggregate_funds.py \
  --holdings /home/claude/work/holdings.json \
  --scores   /home/claude/work/scores_strategies.json \
  --out      /home/claude/work/fund_scores.json
```

For each fund, weight each stock score by its holding weight to get fund-level:
- industry / growth / quality_value / total per strategy
- average risk metrics
- top-5 contributing positive holdings, top-5 dragging holdings

---

## Stage 6 — Risk & overlap analysis / 風險與集中度分析

```bash
python scripts/overlap_analysis.py \
  --holdings /home/claude/work/holdings.json \
  --out      /home/claude/work/risk_report.json
```

Outputs:
1. **Cross-fund overlap matrix** — which stocks appear in multiple funds (concentration risk if user holds several).
2. **Industry concentration per fund** — flag funds where a single industry exceeds 30% (the §9 rule from Requirements).
3. **Per-stock risk rating** — based on volatility, beta, and industry concentration. Five tiers: Very Low / Low / Medium / High / Very High.
4. **Risk-avoidance suggestions** — generated narratively from the above (LLM step in Stage 9).

---

## Stage 7 — Rankings / 排行

```bash
python scripts/build_rankings.py --work-dir /home/claude/work/
```

Produces three ranking tables in JSON:
- Stocks ranked by `growth_score`
- Stocks ranked by aggregate risk (ascending: lowest risk first)
- Funds ranked by each strategy's composite score (3 separate rankings)

---

## Stage 8 — Backtest / 回測

```bash
python scripts/backtest.py \
  --universe /home/claude/work/holdings.json \
  --out      /home/claude/work/backtest.json \
  --periods  1y,3y,5y \
  --strategies growth,conservative,risk_avoidance
```

For each (strategy, period) pair:
1. Universe = all unique stocks held across the 7–11 funds.
2. Each month, recompute scores using point-in-time data (where available; uses current ratios as approximation if historical fundamentals missing — flagged in output).
3. Select top 20% by strategy composite score.
4. Equal-weight portfolio.
5. Apply rules: `-10%` per-stock stop-loss → cash; `30%` industry cap.
6. Rebalance monthly.
7. Compute CAGR, Sharpe, Max Drawdown, Win Rate.

**Read `references/backtest_methodology.md` for the exact rebalancing logic, slippage assumptions, and known limitations.**

> ⚠️ **High token cost stage.** Backtesting fetches up to 5 years × monthly snapshots × all unique tickers. The script batches yfinance calls and caches aggressively — but on first run, expect this stage to take 5–15 minutes wall-clock and use 200k–500k tokens depending on universe size.
> ⚠️ **本階段 token 成本最高。** 首次執行需 5–15 分鐘,用量 20–50 萬 token,視個股數量而定。

---

## Stage 9 — Forward investment view / 前瞻投資觀點

This stage is **LLM-driven synthesis**, not a script. Read all prior outputs:
- `fund_scores.json` — current state of each fund
- `risk_report.json` — risk landscape
- `backtest.json` — historical strategy performance
- `macro.json` — current macro regime

For **each strategy** (Growth / Conservative / Risk-avoidance) × **each horizon** (1y / 3y / 5y), produce:

1. **Top 3 recommended funds** from the user's 7–11, with reasoning.
2. **Expected return range** — anchored on the backtest CAGR ± backtest stdev, adjusted for current macro regime. Express as a range, not a point estimate.
3. **Key risks** — drawn from `risk_report.json`, ranked by relevance to that strategy.
4. **Trigger conditions to revisit** — e.g., "if 10Y yield rises above X" or "if EPS revision turns negative for top holdings".

Output as structured markdown in `/home/claude/work/forward_view.md`. The PDF builder will absorb it.

---

## Stage 10 — Build PDF report / 產出 PDF 報告

```bash
python scripts/build_report.py \
  --work-dir /home/claude/work/ \
  --template references/report_template.md \
  --out      /mnt/user-data/outputs/financial_research_report.pdf
```

Report sections (per `references/report_template.md`):
1. Executive summary / 執行摘要
2. Disclaimer / 免責聲明 (also at end)
3. Fund-by-fund profile (one page each)
4. Cross-fund overlap & concentration heatmap
5. Per-stock score appendix
6. Strategy rankings (3 sets)
7. Backtest results (table + equity curves)
8. Forward investment view (3 strategies × 3 horizons matrix)
9. Methodology notes
10. Disclaimer (repeat)

Use `present_files` to surface the PDF after creation.

---

## Stage 11 — Disclaimer / 免責聲明

The disclaimer in `assets/disclaimer.md` MUST appear in:
- The chat response after report generation
- The first page of the PDF (after exec summary)
- The final page of the PDF
免責聲明須出現於:對話回覆、PDF 首頁(摘要後)、PDF 末頁。

Verbatim text — do not paraphrase.
原文照錄,不可改寫。

---

## Error recovery / 錯誤處理

| Symptom | Action |
|---|---|
| Stage N script returns non-zero | Read its stderr; if it's a missing-data issue, fall back per the script's `--lenient` flag and note the degradation in the report's methodology section |
| yfinance returns empty for a ticker | Mark stock as `unscored`; include in report appendix with reason |
| FRED API key missing | Use yfinance proxies (TNX for 10Y, etc.); note in macro.json that proxies were used |
| User's PDFs are scanned images | Invoke OCR via the `pdf` skill (see its FORMS.md / OCR section); if OCR fails, ask user for text-based versions |
| Total token budget exceeding 800k for the run | Skip the optional momentum factor; reduce backtest universe to top 50 by holding-weight; note both in methodology |

---

## What lives where / 各檔案定位

- **This file (SKILL.md)**: orchestration. Keep under ~500 lines. Defer details to references/.
- **scripts/**: all deterministic computation. Pure Python, no LLM calls.
- **references/**: deep formulas, weight rationale, backtest assumptions, report template. Loaded only when the corresponding stage runs.
- **assets/**: the bilingual disclaimer. Verbatim asset.

When in doubt about a formula or weight, **read the matching reference file before guessing**.