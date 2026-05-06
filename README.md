# Financial Research Skill / 金融分析技能

End-to-end quantitative research pipeline for stock-type mutual funds, packaged as a Claude skill. Bilingual (English / 中文) by default.

針對股票型基金的端對端量化研究流程,封裝為 Claude skill,預設輸出中英雙語報告。

---

## ⚠️ Disclaimer / 免責聲明

> **This skill produces an AI-generated analysis. The reports it generates MUST NOT be used as investment advice.**
> All scores, rankings, backtest metrics, and forward views are derived from publicly available data and statistical models. Past performance does not guarantee future results. Data sources (yfinance, FRED, fund prospectus PDFs) may contain errors or delays. Any investment decision is solely the user's responsibility.

> **本技能所產出之報告為人工智能生成之分析,不得作為投資建議使用。**
> 所有評分、排名、回測指標與前瞻觀點皆源自公開資料與統計模型。歷史表現不保證未來結果。資料來源(yfinance、FRED、基金產品文件 PDF)可能存在錯誤或延遲。任何投資決定均由使用者自行負責。

The verbatim disclaimer in `asstes/disclaimer.md` is embedded into every generated PDF (front and back pages) and printed in the chat response.
完整免責聲明位於 `asstes/disclaimer.md`,會嵌入每份產出的 PDF(首頁與末頁)並於對話回覆中印出。

---

## What this skill does / 功能簡介

Given **7–11 stock-type fund prospectus PDFs**, the skill runs an 11-stage pipeline: parses holdings, fetches market and macro data, scores every unique stock on three factor families (industry, growth/EPS revision, quality/value), aggregates to fund level, analyses cross-fund overlap and concentration, runs a monthly-rebalanced backtest with stop-loss and a 30% industry cap, and emits a bilingual PDF report covering Growth / Conservative / Risk-avoidance strategies across 1y / 3y / 5y horizons.

收到 **7–11 份股票型基金產品文件 PDF** 後,本技能會執行 11 個階段的流程:抽取持倉、抓取行情與宏觀資料、對每檔股票計算三大因子(產業、成長 / EPS 修正、品質與價值)的評分、匯總至基金層、分析交叉持倉與集中度、執行帶停損與 30% 產業上限的月度再平衡回測,並產出涵蓋三套策略(積極成長 / 穩健 / 風險規避)× 三個期間(1 年 / 3 年 / 5 年)的中英雙語 PDF 報告。

---

## When the skill triggers / 觸發情境

| Trigger | 觸發條件 |
| --- | --- |
| User uploads 7–11 fund prospectus PDFs and asks for analysis. | 使用者上傳 7–11 份基金產品文件並要求分析。 |
| Phrases like *fund analysis, holdings breakdown, individual-stock scoring, multi-fund comparison, portfolio backtest*. | 出現「股票型基金分析、基金研究、個股評分、基金回測、多基金比較」等字眼。 |

If fewer than 7 or more than 11 PDFs are supplied, validation stops the pipeline and asks the user to resubmit.
若 PDF 數量不在 7–11 範圍內,Stage 0 驗證會中止流程並請使用者重新提交。

---

## Pipeline overview / 流程總覽

| Stage | Script | Purpose | 用途 |
| --- | --- | --- | --- |
| 0 | `validate_uploads.py` | Validate PDF count, readability, fund-document keywords | 驗證 PDF 數量、可讀性、是否為基金文件 |
| 1 | `extract_holdings.py` | LLM-assisted holdings extraction + dedupe | LLM 抽取持倉並去重 |
| 2 | `fetch_market_data.py`, `fetch_macro_data.py` | Pull market data via yfinance, macro via FRED | 透過 yfinance 取行情、FRED 取宏觀資料 |
| 3 | `compute_scores.py` | Per-stock factor scores (0–100) | 個股因子評分(0–100) |
| 4 | `strategy_weights.py` | Three strategy composite scores | 三套策略複合評分 |
| 5 | `aggregate_funds.py` | Roll stock scores up to fund level | 將個股評分匯總至基金層 |
| 6 | `overlap_analysis.py` | Cross-fund overlap matrix + industry concentration | 交叉持倉矩陣與產業集中度 |
| 7 | `build_rankings.py` | Ranking tables (stocks & funds) | 排行表(個股與基金) |
| 8 | `backtest.py` | Monthly-rebalanced backtest with stop-loss & industry cap | 帶停損與產業上限的月度再平衡回測 |
| 9 | LLM synthesis | Forward investment view (3 strategies × 3 horizons) | 前瞻投資觀點(3 策略 × 3 期間) |
| 10 | `build_report.py` | Bilingual PDF report (ReportLab) | 產出中英雙語 PDF 報告 |

All intermediate outputs are written as JSON to `/home/claude/work/`, so each stage reads only the previous stage's output and large data structures stay out of the conversation context.

每個階段的中間結果以 JSON 寫入 `/home/claude/work/`,後階段只讀取前階段輸出,避免大型資料常駐對話上下文。

Detailed orchestration logic, per-stage prompts, and error recovery rules live in [`SKILL.md`](./SKILL.md).
詳細編排邏輯、各階段提示與錯誤處理規則,請參閱 [`SKILL.md`](./SKILL.md)。

---

## Project structure / 專案結構

```
.
├── SKILL.md                     # Skill orchestration spec / 技能總覽與流程規範
├── requirements.txt             # Python deps / Python 依賴
├── asstes/                      # Skill assets (see "Known issues") / 技能資產(見「已知問題」)
│   └── disclaimer.md            # Verbatim bilingual disclaimer / 中英雙語免責聲明原文
├── references/                  # Deep references loaded only when needed / 各階段詳參考,按需載入
│   ├── scoring_playbook.md      # Per-stock scoring formulas / 個股評分公式
│   ├── strategy_weights.md      # Strategy weight schemes / 策略權重方案
│   ├── backtest_methodology.md  # Backtest rules & limitations / 回測規則與限制
│   ├── data_sources.md          # yfinance / FRED field map / 資料來源欄位對照
│   └── report_template.md       # PDF report layout / PDF 報告版型
└── scripts/                     # Deterministic computation (no LLM calls) / 確定性運算(無 LLM 呼叫)
    ├── validate_uploads.py
    ├── extract_holdings.py
    ├── fetch_market_data.py
    ├── fetch_macro_data.py
    ├── compute_scores.py
    ├── strategy_weights.py
    ├── aggregate_funds.py
    ├── overlap_analysis.py
    ├── build_rankings.py
    ├── backtest.py
    └── build_report.py
```

---

## Installation / 安裝

```bash
pip install -r requirements.txt --break-system-packages
```

Optional but recommended — set a free FRED API key for richer macro data:
建議(非必要)— 設定免費的 FRED API key 以取得更完整的宏觀資料:

```bash
export FRED_API_KEY="your_free_key_from_fred.stlouisfed.org"
```

If `FRED_API_KEY` is unset, `fetch_macro_data.py` falls back to yfinance proxies and flags the degradation in `macro.json`.
若未設定,本技能會改用 yfinance 代理欄位,並在 `macro.json` 中標註資料降級。

The PDF builder (Stage 10) requires a CJK font (Noto Sans CJK preferred, WenQuanYi Zen Hei as fallback) to render Chinese text.
產出 PDF 時(Stage 10)需安裝中日韓字體(優先 Noto Sans CJK,備援 WenQuanYi Zen Hei)以正確渲染中文。

---

## Usage / 使用方式

This is a Claude skill — invoke it by uploading 7–11 stock-type fund prospectus PDFs and asking Claude for fund analysis. The skill runs the full pipeline and surfaces a bilingual PDF report.

本專案為 Claude skill — 上傳 7–11 份股票型基金產品文件 PDF 並請 Claude 進行基金分析,即會自動執行整個流程並產出中英雙語 PDF 報告。

For local development or debugging, individual scripts can be run directly. Example end-to-end sequence:
若要在本機開發或除錯,可直接執行各腳本,範例如下:

```bash
# Stage 0
python scripts/validate_uploads.py /path/to/uploads

# Stage 1 — after writing holdings.json from PDF text extraction
python scripts/extract_holdings.py --input /home/claude/work/holdings.json --dedupe

# Stage 2
python scripts/fetch_market_data.py --universe /home/claude/work/holdings.json --out /home/claude/work/market.json
python scripts/fetch_macro_data.py --out /home/claude/work/macro.json

# Stages 3–7
python scripts/compute_scores.py    --market /home/claude/work/market.json --macro /home/claude/work/macro.json --out /home/claude/work/scores_per_stock.json
python scripts/strategy_weights.py  --scores /home/claude/work/scores_per_stock.json --out /home/claude/work/scores_strategies.json
python scripts/aggregate_funds.py   --holdings /home/claude/work/holdings.json --scores /home/claude/work/scores_strategies.json --out /home/claude/work/fund_scores.json
python scripts/overlap_analysis.py  --holdings /home/claude/work/holdings.json --out /home/claude/work/risk_report.json
python scripts/build_rankings.py    --work-dir /home/claude/work/

# Stage 8 — high token / wall-clock cost
python scripts/backtest.py --universe /home/claude/work/holdings.json --out /home/claude/work/backtest.json \
    --periods 1y,3y,5y --strategies growth,conservative,risk_avoidance

# Stage 10 — produce the PDF
python scripts/build_report.py --work-dir /home/claude/work/ \
    --template references/report_template.md \
    --out /mnt/user-data/outputs/financial_research_report.pdf
```

> **Stage 8 is the most expensive step.** First run typically takes 5–15 minutes wall-clock and 200k–500k tokens. yfinance responses are cached to `/home/claude/work/cache/` keyed by ticker + date, so re-running within a day is free.
> **Stage 8(回測)為成本最高階段。** 首次執行約需 5–15 分鐘、20–50 萬 token。yfinance 結果會以「ticker + 日期」為 key 寫入快取,同日重跑不會再呼叫 API。

---

## Output / 產出

A bilingual PDF report at `/mnt/user-data/outputs/financial_research_report.pdf`, structured as:
中英雙語 PDF 報告,輸出於 `/mnt/user-data/outputs/financial_research_report.pdf`,結構如下:

1. Cover / 封面
2. Disclaimer (front) / 免責聲明(首頁)
3. Executive summary / 執行摘要
4. Per-fund profiles / 各基金檔案(每基金一頁)
5. Cross-fund overlap & concentration heatmap / 交叉持倉與集中度熱圖
6. Per-stock score appendix / 個股評分附表
7. Strategy rankings (3 pages) / 策略排行(共三頁)
8. Backtest results (table + equity curves) / 回測結果(表格與淨值曲線)
9. Forward investment view (3 × 3 matrix) / 前瞻投資觀點(3 × 3 矩陣)
10. Methodology notes (limitations table) / 方法論說明(限制表)
11. Disclaimer (back) / 免責聲明(末頁)

---

## Strategies / 三套策略

| Strategy | industry | growth | quality_value | momentum | concentration penalty |
| --- | ---: | ---: | ---: | ---: | ---: |
| Growth / 積極成長 | 0.20 | 0.60 | 0.20 | +0.10 | — |
| Conservative / 穩健 | 0.30 | 0.20 | 0.50 | — | — |
| Risk-avoidance / 風險規避 | 0.40 | 0.10 | 0.50 | — | up to −20 |

Full rationale, calibration notes, and per-strategy formulas live in [`references/strategy_weights.md`](./references/strategy_weights.md).
完整設計理由、校準說明與公式,請見 [`references/strategy_weights.md`](./references/strategy_weights.md)。

---

## Known issues / 已知問題

- **Lookahead bias in fundamentals.** The backtest uses *current* PE / ROE / EV-EBITDA across the entire historical window because yfinance does not provide clean point-in-time fundamentals. This optimistically biases value/growth strategies and is disclosed in the PDF's methodology section.
  **基本面前視偏差。** yfinance 無法提供乾淨的 point-in-time 基本面,回測對整個區間都使用「當前」的 PE / ROE / EV-EBITDA,會對價值 / 成長策略造成樂觀偏差;此事實會在 PDF 方法論章節揭露。

- **Survivorship bias.** yfinance does not include delisted tickers; results are biased upward and this is disclosed.
  **倖存者偏差。** yfinance 不含已下市股票,結果偏正向,並在報告中揭露。

See [`references/backtest_methodology.md`](./references/backtest_methodology.md) §6 for the full limitations table.
完整限制清單請見 [`references/backtest_methodology.md`](./references/backtest_methodology.md) §6。

---

## Dependencies / 相依套件

- `pypdf` ≥ 4.0 — PDF parsing / PDF 解析
- `yfinance` ≥ 0.2.40 — market data / 行情資料
- `fredapi` ≥ 0.5.1 — macro data (optional) / 宏觀資料(選用)
- `pandas` ≥ 2.0, `pandas-datareader` ≥ 0.10, `numpy` ≥ 1.24
- `reportlab` ≥ 4.0 — PDF generation / PDF 產出
- `matplotlib` ≥ 3.7 — chart rendering / 圖表渲染

This skill also depends on the public `pdf` skill at `/mnt/skills/public/pdf/SKILL.md` for advanced PDF cases such as scanned / OCR documents.
本技能也依賴公開 `pdf` skill(位於 `/mnt/skills/public/pdf/SKILL.md`)處理掃描 / OCR 等進階 PDF 情況。

---

## ⚠️ Disclaimer (repeat) / 免責聲明(再次強調)

> **The reports produced by this skill are AI-generated analyses and MUST NOT be used as investment advice.**
> Past performance does not guarantee future results. Data sources may contain errors or delays. Any investment decision made based on these reports is solely the user's responsibility.

> **本技能所產出之報告為人工智能生成之分析,絕不可作為投資建議使用。**
> 歷史表現不保證未來結果。資料來源可能存在錯誤或延遲。基於本報告所做之任何投資決定,均由使用者自行承擔全部責任。
