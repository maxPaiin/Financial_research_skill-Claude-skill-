# Iteration_0.2v — financial-research skill
# Vibe-coding prompt for Claude to iterate the skill against

**Status**: Implementation-ready prompt
**Audience**: Claude (this is a skill iterated by Claude, for Claude)
**Predecessor**: v1 (`financial-research-skill.skill`, shipped, deprecated upon v0.2 ship)
**Action**: Iterate v1 → v0.2 by reusing salvageable modules and rebuilding the rest

---

## 0. Read this first

This file is your specification, your decision log, and your acceptance contract — all three. Read it linearly the first time. Refer back to specific sections by §-number when implementing.

This skill runs end-to-end inside Claude.ai. No external orchestrator, no human-in-the-loop between stages. When this document says "Claude does X," it means the same Claude instance that loaded this skill at conversation time.

If you find this document contradicting itself, the higher-numbered section wins. If a contradiction is between an early "what & why" statement and a later "how" statement, the what & why wins — the how exists to serve it. Surface contradictions immediately rather than silently picking one.

---

## 1. What this skill is — and is not

### 1.1 Core goal

> Given 7–11 HKMA-approved global fund prospectus PDFs distributed through Hong Kong private banking channels (Standard Chartered HK, Citi HK, and similar), produce an English-language report that filters and ranks the **US-listed equities** held across those funds, and presents a watchlist of high-quality candidates for the user's own further research.

### 1.2 What this skill IS

- A **filter and ranking tool** for stocks the user can plausibly buy through their HK bank
- A **consensus-discovery instrument** — finds stocks that multiple HK-channel funds independently chose to hold, **adjusted for crowding risk**
- A **quality screen** — removes companies with clear fundamental problems before ranking
- An **honesty-forward report generator** that surfaces methodology limits next to its conclusions

### 1.3 What this skill IS NOT

The following are deliberate non-goals. Do not implement them, even if asked. Do not let them sneak in as "small additions."

- **NOT an alpha-generation tool.** The starting universe (HK channel fund picks) is a distribution-preference set, not the global equity market. Ranking outputs cannot be interpreted as market-beating signals.
- **NOT a portfolio construction tool.** It outputs a ranked watchlist, not weights. The user decides allocation according to their own risk profile.
- **NOT a backtest engine.** v1 had a monthly-rebalanced backtest with three strategies. v0.2 **removes** this entirely. Reasoning: with HK-channel input bias and small fund sample size, backtest results are misleading rather than informative. Any "validation" of methodology happens through prose disclosure in the Honest Framing section (§7.3.3), not numerical backtesting.
- **NOT a global equity tool.** US-listed equities only. Non-US holdings in fund prospectuses are **dropped at Stage 1b** and reported as out-of-scope.
- **NOT a bilingual tool.** All output is English. The chat interaction with the user may remain bilingual at Claude's discretion, but every generated `.md`, `.pdf`, and persisted file is English-only.
- **NOT a three-strategies tool.** v1 had Growth/Conservative/Risk-avoidance. v0.2 produces **one ranking**. Different user risk profiles are addressed by the ranked card's rationale, not by parallel rankings.

### 1.4 Known biases the report must surface

These four are accepted limitations baked into the input. The report's Honest Framing section makes them explicit:

1. **HK distribution-channel bias.** Funds approved by HKMA and distributed through HK private banking are a curated subset chosen for sellability to HK retail/private clients. They cluster around well-known large-caps.
2. **Top-N disclosure lag.** Fund prospectuses typically disclose only top-10 to top-20 holdings, and disclosure dates run 30–60 days behind. We see a partial, stale picture.
3. **Small sample size.** 7–11 funds is statistically small. We do not claim statistical significance for any signal.
4. **Survivorship in the fund universe.** Funds we see are by definition operating funds. Failed funds and their losing picks are absent from input.

### 1.5 Why these choices

- v1 attempted to be all things and ended up over-claiming alpha. v0.2 narrows scope to what is honestly defensible given input constraints.
- The HK channel is a real, useful, narrow universe. Telling the user "here are the best US stocks held in your purchasable fund universe, with caveats" is a different and more honest service than "here is alpha."
- Removing backtest removes the largest source of token cost and the largest source of false confidence. Both wins align.

---

## 2. Inheritance from v1

v0.2 is an **iteration** of v1, not a rewrite. v1's source is at `/home/claude/financial-research-skill/` (or whatever path the working v1 is restored to before iteration begins). The following table is the contract — when a row says "Keep" or "Reuse," the implementation must read v1's code first and reuse logic where it works, rather than rewriting from scratch.

| v1 file | v0.2 action | Notes |
|---|---|---|
| `validate_uploads.py` | **Keep, simplify** | Remove Chinese strings. Strengthen "what should this PDF contain" guidance per §3.1.3. |
| `extract_holdings.py` | **Keep, extend** | Add PIT snapshot grouping (§3.1.4). Strengthen ticker normalization for ADR handling (§3.1.2). |
| `overlap_analysis.py` | **Keep, restructure** | Promote from appendix-level to core. Extract risk-tiering into separate concern. |
| `fetch_market_data.py` | **Refactor into** `providers/yfinance_provider.py` | Behavior preserved; interface changes (returns `DataPoint`, not raw dict). |
| `fetch_macro_data.py` | **Delete** | No macro tilt in v0.2's scoring. |
| `compute_scores.py` | **Heavy rewrite** | Reuse `percentile()` utility. Replace formula stack per §3.2.3 and §3.2.4. |
| `strategy_weights.py` | **Delete** | No three-strategies in v0.2. |
| `aggregate_funds.py` | **Light rewrite** | Reuse `weighted_avg()`. Reshape output to match Layer 2 contract. |
| `build_rankings.py` | **Rewrite** | One ranking, not three. New ranking formula per §3.3.1. |
| `backtest.py` | **Delete** | Backtest removed entirely. |
| `build_report.py` | **Heavy rewrite** | English only. Inputs from three layered `.md` files. Sections per §7. |
| `assets/disclaimer.md` | **Replace** | English-only version. |
| `references/*.md` | **Rewrite** | Become "methodology readers" — no executable rules. See §5. |
| `SKILL.md` | **Shrink to ≤150 lines** | Orchestration-only, no formulas. See §5. |

New files introduced in v0.2:
- `scripts/providers/base.py` — `DataPoint`, ABCs
- `scripts/providers/edgar_provider.py` — true-PIT US fundamentals
- `scripts/providers/yfinance_provider.py` — degraded-PIT fallback (refactored from v1)
- `scripts/providers/pdf_snapshot_provider.py` — fund holdings at given asof
- `scripts/providers/registry.py` — provider selection + routing
- `scripts/providers/resolver.py` — multi-source conflict resolution
- `scripts/providers/industry_map.py` — US-only industry buckets (constants)
- `scripts/quality_screen.py` — PASS/FAIL filter (§3.2.4)
- `scripts/crowding_signal.py` — consensus-with-crowding-discount (§3.2.6)
- `scripts/layer1_report.py` — generates `layer1_extraction.md`
- `scripts/layer2_report.py` — generates `layer2_screening.md`
- `scripts/layer3_report.py` — generates `layer3_ranked_advice.md`

**Estimated final LOC**: ~2,400 (down from v1's 3,055).

---

## 3. Pipeline specification

Three layers, ten stages. Each layer produces a downloadable `.md`. Stage 4 (PDF assembly) combines them.

### 3.1 Layer 1 — Extraction

Cheap, deterministic where possible. Claude (LLM) only invoked for PDF holdings parsing because table formats vary across fund issuers.

#### 3.1.1 Stage 0 — Validation

**Script**: `validate_uploads.py`

**Checks**:
- 7 ≤ count of `.pdf` files < 12
- Each PDF opens with `pypdf`, yields ≥ 1 page of extractable text
- Each PDF contains at least one of: "holdings", "portfolio", "top holdings", "持倉", "持股" (Chinese terms accepted because some HK funds publish bilingual factsheets, but **all downstream processing is English-only**)
- Each PDF contains a date pattern likely to be the asof date

**Failure messages** must educate the user on what a valid input looks like:

> "Your PDF should be a fund factsheet or prospectus that includes: (1) top-N holdings table with at least 10 entries, (2) reporting date (asof), (3) ticker or ISIN per holding, (4) weight % per holding, and ideally (5) total fund AUM. If your PDF lacks these — for example, if you uploaded a marketing brochure, an annual letter, or a regulatory filing without holdings disclosure — please replace it with the fund's monthly or quarterly factsheet."

#### 3.1.2 Stage 1a — PDF holdings extraction (LLM step)

**Done by Claude directly**, not a script. Claude reads each PDF (via `view` tool on the upload path or via pypdf extraction) and produces one JSON record per fund:

```json
{
  "fund_id": "F1",
  "fund_name": "...",
  "issuer": "Standard Chartered HK / Citi HK / ...",
  "asof": "YYYY-MM-DD",
  "currency": "USD",
  "total_aum": 12345678901.0,
  "holdings": [
    {"ticker_raw": "AAPL", "name": "Apple Inc.", "weight": 0.0723, "isin": "US0378331005"}
  ]
}
```

**Token discipline**: process one PDF at a time. Write the JSON to disk immediately. Do not retain previous PDFs' text in working context. If a PDF is long (>10 pages), use `view_range` to focus on the holdings table region.

**Failure handling** (per §6 D2 decision):
- If holdings extracted has fewer than 5 entries OR total extracted weight sums to less than 20% of fund AUM (sanity check that the holdings table was found), **reject this fund entirely**. Log the rejection in `layer1_extraction.md`. Continue with remaining funds.
- If after rejections the fund count drops below 7, halt the pipeline and tell the user which PDFs failed and how to fix them.

#### 3.1.3 Stage 1b — Ticker normalization & US filtering

**Script**: `extract_holdings.py` (extended from v1)

**Rules**:
- Strip exchange suffixes from US tickers: `AAPL US` → `AAPL`, `AAPL.O` → `AAPL`
- Resolve ISIN-only entries by lookup (LLM judgement + ISIN prefix: `US...` indicates US listing)
- **ADRs are in scope**: `BABA`, `TSM`, `ASML` (ADR), etc. They trade on US exchanges; they count as US-listed.
- **Drop and report** non-US primary listings: `.T` (Tokyo), `.HK` (Hong Kong), `.TW` (Taiwan), `.L` (London), `.SS`/`.SZ` (mainland China), `.PA` (Paris), `.DE` (Frankfurt), etc.
- **Drop and report** non-equity holdings: cash, derivatives, bonds, ETFs of indices.

**Output** adds per-fund:
```json
{
  "...": "...",
  "scope_summary": {
    "n_holdings_total": 25,
    "n_holdings_kept_us_equity": 18,
    "n_dropped_non_us": 5,
    "n_dropped_non_equity": 2,
    "weight_kept": 0.72,
    "weight_dropped": 0.28
  }
}
```

#### 3.1.4 Stage 1c — Universe deduplication

**Script**: `extract_holdings.py` (existing `dedupe()` function, reused)

Produces `unique_universe` array: each unique ticker, with `held_by[fund_ids]`, `weights_by_fund{}`, `n_funds_holding`, `max_weight`, `avg_weight`. Already implemented in v1 and works correctly; keep as-is.

#### 3.1.5 Stage 1d — PIT snapshot grouping

**New logic** within `extract_holdings.py`.

Groups fund snapshots by `(fund_family, asof)`. Used by Stage 2's PDFSnapshotProvider.

Reality: most users upload one snapshot per fund. In that case, `single_snapshot_mode = True` for that fund — the snapshot is treated as valid for all asof queries, with `confidence = 0.5` (degraded). Multi-snapshot mode upgrades confidence to 0.7.

#### 3.1.6 Layer 1 output

**Script**: `layer1_report.py`

Writes `layer1_extraction.md` to `/home/claude/work/`:

```markdown
# Layer 1: Extraction Summary

## Input
- Funds uploaded: N
- Funds successfully parsed: M
- Funds rejected (insufficient holdings data): K  [if any]

## Per-fund extraction
| Fund ID | Name | Issuer | asof | AUM | Holdings kept | % AUM kept |
| ... | ... | ... | ... | ... | ... | ... |

## Universe summary
- Unique US-listed tickers: P
- Stocks held by ≥2 funds: Q (Q/P %)
- Stocks held by ≥5 funds: R

## Out-of-scope summary
- Non-US listings dropped: X tickers across all funds (Y% of total AUM)
- Non-equity dropped: Z tickers (W% of total AUM)

## PIT snapshot availability
| Fund | Snapshots available | Date range | Mode |
| ... | ... | ... | single_snapshot / multi_snapshot |

## Next layer
The unique universe (P tickers) advances to Layer 2 for fundamental fetch and quality screening.
```

### 3.2 Layer 2 — Overlap & Screen

Mid-cost. Provider API calls (EDGAR, yfinance), deterministic computation, no LLM.

#### 3.2.1 Stage 2a — Overlap matrix

**Script**: `overlap_analysis.py` (refactored from v1)

For each unique ticker, compute:
```python
{
  "ticker": str,
  "name": str,
  "held_by": [fund_ids],
  "weights_by_fund": {fund_id: float},
  "n_funds_holding": int,
  "sum_of_weights": float,    # sum across all funds (proxy for "total commitment")
  "avg_weight": float,        # mean weight where held
  "max_weight": float
}
```

This is v1 logic, working. Refactor only to clean naming and to feed Stage 2d.

#### 3.2.2 Stage 2b — Fundamental fetch via provider routing

**Scripts**: `providers/registry.py` orchestrates; individual providers do the work.

Provider call order per ticker:
1. **EDGARProvider** — true PIT, baseline confidence 0.9
2. **yfinanceProvider** — degraded PIT, baseline confidence 0.5
3. **Mark as unscored** if both fail (no fabrication)

Each provider returns `DataPoint` objects per field:

```python
@dataclass(frozen=True)
class DataPoint:
    value: float | None
    confidence: float            # 0.0 to 1.0
    source: str                  # "edgar:10-K-2024" / "yfinance:2025-05" / "pdf:F1-2024Q4"
    asof: date
    n_sources_agreed: int = 1
```

Fields fetched (all PIT, asof = latest fund snapshot date):
- ROE for the past 5 fiscal years (annual array)
- EV/EBITDA (latest)
- Debt/Equity (latest)
- Net income for past 5 years (for "persistent negative earnings" check)
- Industry (Yahoo or SEC SIC code, mapped via `industry_map.py`)
- Market cap, average daily volume (ADV) — for crowding signal

##### EDGAR-specific contract

`providers/edgar_provider.py` MUST implement:

- Hardcoded User-Agent: `"FinancialResearchSkill-v0.2 anthropic-claude-skill"`
- Hardcoded throttle: minimum 100 ms between requests (≤ 10 req/s, per SEC fair-use policy)
- Hardcoded daily budget per session: 600 requests max (well below SEC ceilings)
- Permanent cache by `(ticker, filing_id)` — filings are immutable
- Retry policy on HTTP 429: exponential backoff at 1s, 2s, 4s, then abort and fall through to yfinance
- Support both 10-K (US domestic) and 20-F (foreign filers including most ADRs) parsing

##### ADR handling specifics

ADRs (BABA, TSM, ASML in US form, etc.):
- Try 20-F first via EDGAR — many file annually
- If 20-F absent, fall through to yfinance with degraded confidence
- Either way, flag as ADR in output for the Honest Framing section

#### 3.2.3 Stage 2c — Conflict resolution (when applicable)

**Script**: `providers/resolver.py`

For fields where multiple providers return values for the same (ticker, asof):

```
diff_pct = |v1 - v2| / max(|v1|, |v2|, 1e-9)

if diff_pct < 0.05:    return mean, confidence = max(c1, c2)
elif diff_pct < 0.20:  return higher-confidence source, log dispersion warning
else:                  return higher-confidence source, confidence *= 0.5,
                       log to data_provenance.json with severity="high"
```

Three+ sources: take median; halve confidence if `max - min > 0.20 × median`.

#### 3.2.4 Stage 2d — Quality screen (PASS / FAIL)

**Script**: `quality_screen.py`

Per the agreed methodology: **quality is a filter, not a ranker**. Output is binary.

PASS criteria — **all** must hold:
- ROE positive in ≥ 3 of last 5 fiscal years
- Debt/Equity available and < 5.0 (sanity ceiling — distress filter)
- No 3 consecutive years of negative net income
- At least 2 of the 3 key metrics (ROE 5y, EV/EBITDA, Debt/Equity) available with confidence ≥ 0.4

FAIL → marked `screened_out` with reason string. Excluded entirely from Layer 3 ranking.

Per §6 decision: **all screened-out stocks are disclosed in `layer2_screening.md`** with their failure reasons, so the user can audit the screen.

#### 3.2.5 Stage 2e — Fundamental quality percentile

For PASSED stocks only, compute:
```python
fundamental_quality_score = percentile_rank(
    metric = ROE_5y_average,
    distribution = ROE_5y_averages_of_all_passed_stocks
)  # 0–100
```

Why ROE 5y average as the single quality metric:
- Most discriminating single number for "is this a quality business"
- 5y average dampens single-year noise
- More universally available than EV/EBITDA across ADRs
- Already screened against negative-ROE persistence in §3.2.4

#### 3.2.6 Stage 2f — Consensus-with-crowding-discount

**Script**: `crowding_signal.py`

Implements the agreed single signal (no two separate consensus/crowding numbers).

```python
def consensus_with_crowding_discount(ticker_overlap_row, market_cap, adv):
    consensus_raw = log(1 + ticker_overlap_row.n_funds_holding)

    avg_weight = ticker_overlap_row.avg_weight        # mean weight where held
    n_funds    = ticker_overlap_row.n_funds_holding

    # Crowding discount: how concentrated is the position?
    # Heuristic: avg_weight > 5% AND n_funds >= 5 indicates HK-channel crowding
    crowding_raw = max(0, (avg_weight - 0.02) / 0.08) * (n_funds / 5.0)
    crowding_discount = min(crowding_raw, 0.6)        # cap at 60% discount

    return consensus_raw * (1 - crowding_discount)
```

Tuning notes (these are starting defaults, may be calibrated later):
- 2% avg weight threshold: below this, no crowding discount
- 8% range to full discount: stocks at 10% avg weight get strong discount
- 5-fund denominator: 5+ funds at moderate weight starts to suggest crowding

#### 3.2.7 Layer 2 output

**Script**: `layer2_report.py`

Writes `layer2_screening.md`:

```markdown
# Layer 2: Overlap and Quality Screen

## Universe state
- Entered Layer 2: P tickers
- Passed quality screen: P_pass (P_pass / P %)
- Failed quality screen: P_fail
- Unscored (data unavailable): P_unscored

## Overlap matrix (top 30 by n_funds_holding)
| Ticker | Name | Industry | # funds | Sum weight | Avg weight | Max weight |
| ... |

## Quality screen results

### Passed (P_pass tickers)
| Ticker | ROE 5y avg | EV/EBITDA | D/E | Confidence |
| ... |

### Screened out (P_fail tickers)  [disclosed per §6 Q5 decision]
| Ticker | Reason | Detail |
| AAA | persistent_negative_earnings | Net income negative 2022, 2023, 2024 |
| BBB | distress_debt_ratio | D/E = 7.2 exceeds 5.0 ceiling |
| ... |

### Unscored (P_unscored tickers)
| Ticker | Reason |
| CCC | No EDGAR filing, yfinance returned empty |
| ... |

## Data quality summary
- EDGAR coverage: X tickers (X/P %), avg confidence 0.9
- yfinance coverage: Y tickers (Y/P %), avg confidence 0.5
- Conflict events resolved: Z
- See `data_provenance.json` for full provenance

## Consensus-with-crowding-discount distribution
(brief histogram describing the signal range across passed universe)

## Next layer
P_pass tickers advance to Layer 3 for composite ranking.
```

### 3.3 Layer 3 — Ranking & Advice

LLM-driven where appropriate. Composite ranking is deterministic; per-stock rationale cards and honest framing are Claude prose.

#### 3.3.1 Stage 3a — Composite ranking

**Script**: `build_rankings.py` (rewritten)

For each PASSED ticker:
```python
composite_score = 0.50 * fundamental_quality_score                # 0-100, from Stage 2e
                + 0.50 * normalize(consensus_with_crowding_discount, to_0_100=True)
```

Normalize the crowding signal to a 0–100 scale using the min/max within the passed universe.

Sort descending; top N=15 advances to Stage 3b.

**Tier grouping** (within top 15):
- Tier A: top 5
- Tier B: ranks 6–10
- Tier C: ranks 11–15

These are display groupings; they do not change the rationale generation.

#### 3.3.2 Stage 3b — Per-stock rationale cards (Claude does this)

For each of the 15 ranked stocks, Claude generates a structured markdown card.

**Implementation discipline**: do NOT generate all 15 in one Claude turn. Process in **3 batches of 5**, writing each batch to disk before generating the next. This avoids per-message token ceilings and lets the pipeline recover gracefully if a single batch fails.

Card template (markdown):

```markdown
### #{rank}   {ticker}   {name}

**Held by:** {n_funds_holding} of {total_funds} funds ({pct}%) {crowding_flag_if_applicable}

**Avg weight where held:** {avg_weight}%  |  **Max weight:** {max_weight}%  |  **Latest asof:** {latest_asof}

**Quality screen:** PASS (confidence {overall_confidence})
- ROE 5y avg: {roe_avg}% {visual_marker}
- EV/EBITDA: {ev_ebitda} (industry median {ind_median})
- Debt/Equity: {de} {flag_if_elevated}

**Composite rank:** {rank} of {n_passed} screened   |   **Tier:** {tier}

**Rank rationale:**
- + {positive_factor_1}
- + {positive_factor_2}
- - {risk_factor_1}
- - {risk_factor_2}

**Bias note:** This rank reflects HK distribution channel preference. It is not a market-wide alpha signal.
```

**The crowding_flag**: present when `crowding_discount >= 0.3` in the signal calculation. Text: `⚠ HIGH CROWDING — multiple funds hold large positions; vulnerable to coordinated unwind.`

Claude's job for each card:
- Read the structured numeric data from Stage 2 outputs
- Pick the 2 most salient positive factors from the data
- Pick the 2 most salient risk factors from the data
- Write each factor in plain English, ≤ 15 words
- Do not embellish, do not predict prices, do not opine on macro

#### 3.3.3 Stage 3c — Honest framing (Claude does this)

Claude generates the standardized framing paragraph at the top of `layer3_ranked_advice.md`. Template-driven, ~500–800 tokens of prose. Content covers §1.2, §1.3, §1.4 of this document, customized with the actual numbers from this run (sample size, dropped %, etc.).

#### 3.3.4 Layer 3 output

**Script**: `layer3_report.py`

Writes `layer3_ranked_advice.md`:

```markdown
# Layer 3: Ranked Watchlist

## What this analysis is and is not
{honest_framing_paragraph from Stage 3c}

## Top 15 ranked watchlist
{15 cards from Stage 3b, organized by Tier A / B / C}

## Methodology disclosure
- Universe: {N} HKMA-approved global funds, distributed through HK private banking
- Filter: US-listed equities only (including ADRs)
- Quality screen: ROE persistence, debt sanity, earnings continuity
- Ranking signal: 50% fundamental quality + 50% consensus-with-crowding-discount

## Important caveats
- Sample size of N funds is small; rankings are not statistically significant
- Top-N disclosure in fund prospectuses introduces 30–60 day staleness
- HK channel bias is not corrected for; absolute and relative rankings reflect that bias

## Disclaimer
{disclaimer text}
```

### 3.4 Stage 4 — PDF assembly

**Script**: `build_report.py` (rewritten)

Reads the three layer `.md` files plus supporting JSON, assembles into a single English PDF using ReportLab. Estimated final length: **18–26 pages, typically 20–22 pages**.

PDF section order:
1. Cover (1 page)
2. Disclaimer (1 page)
3. Honest framing (1–2 pages, from Layer 3 header)
4. Executive summary (1 page) — auto-generated bullet summary
5. Layer 1: Extraction summary (1–2 pages)
6. Layer 2: Overlap matrix (2–3 pages with heatmap visualization)
7. Layer 2: Quality screen results including disclosed screened-out list (1–2 pages)
8. Layer 2: Data quality summary (1 page)
9. Layer 3: Ranked watchlist with cards (5 pages, 3 cards per page)
10. Layer 3: Tier groupings visualization (1 page)
11. Methodology disclosure (1–2 pages)
12. Disclaimer (1 page)

PDF styling:
- A4, 18mm margins
- 10pt body, sans-serif (system default is fine — no CJK fonts needed since English-only)
- Charts via matplotlib, embedded as PNG
- No color requirements beyond legibility; v1's heavy color palette is removed

---

## 4. Token budget and feasibility

### 4.1 Claude's output across the pipeline

| Stage | Claude output | Tokens (est.) |
|---|---|---|
| Stage 1a (per PDF) | One JSON record | ~1,000 |
| Stage 1a × 8 PDFs | 8 JSON records, across multiple turns | ~8,000 |
| Stage 3b (15 cards) | 3 batches × ~1,500 tokens | ~4,500 |
| Stage 3c (framing) | One prose block | ~800 |
| **Total Claude output** | | **~13,000–15,000 tokens** |

### 4.2 Context window usage

| Item | Tokens (est.) |
|---|---|
| 8 fund PDFs as input text (worst case ~10KB each) | ~80,000 |
| Stage outputs accumulated in conversation | ~15,000 |
| Stage 2 outputs read by Stage 3 | ~10,000 |
| Other interaction overhead | ~15,000 |
| **Total context window** | **~120,000 / 200,000 (60%)** |

### 4.3 Discipline to stay within budget

- **Stage 1a**: process one PDF at a time. Write output to disk. Tell Claude explicitly that prior PDF text need not be retained.
- **Stage 1a with large PDFs**: if a PDF exceeds 8K tokens of text, use `view` with `view_range` to focus on the holdings table region (typically mid-to-late in the document).
- **Stage 3b**: batch in 3 × 5, never 1 × 15.
- **All deterministic stages**: results streamed to disk, not retained in conversation.

### 4.4 Why this works

The pipeline uses the file system as memory. Claude's working context only holds the "current step's task" at any time, not the full data set. The 20-page final PDF is binary content assembled by Python from on-disk markdown — it does not pass through Claude's token budget.

---

## 5. Documentation discipline

### 5.1 SKILL.md (≤ 150 lines)

Contains **only**:
- YAML frontmatter (name, description)
- One-paragraph mission statement
- Pipeline orchestration table (which script runs when, what file it reads, what file it writes)
- Error decision tree (what to do when stage N fails)
- Output contract (what files appear at end)

Does **NOT** contain:
- Any formulas
- Any weights or thresholds
- Any provider implementation details
- Any business-rule explanations

### 5.2 references/ (methodology readers)

Each `.md` in `references/` is a **reader** explaining methodology to a human or another LLM, with **no executable rules**.

- `references/methodology.md` — what the skill does, why, what it does not do
- `references/quality_screen.md` — what passes, what fails, why
- `references/crowding_signal.md` — what the signal means, why this form
- `references/providers.md` — provider routing, confidence rationale, EDGAR contract
- `references/honest_framing.md` — the framing prose template and rationale

Any formula or threshold in these files must be a **quote of** the canonical location (script docstring or module constant), not the source of truth.

### 5.3 Single source of truth table

| Fact | Canonical location |
|---|---|
| Ranking weights (0.50 / 0.50) | `build_rankings.py` module constant |
| Quality screen thresholds | `quality_screen.py` module constants |
| Crowding signal formula | `crowding_signal.py` docstring + module constants |
| Industry buckets | `providers/industry_map.py` constant |
| Confidence baselines per source | `providers/base.py` `DEFAULT_CONFIDENCE` dict |
| EDGAR contract (UA, throttle, etc.) | `providers/edgar_provider.py` module header |
| Disclaimer text | `assets/disclaimer.md` |
| Conflict resolution thresholds | `providers/resolver.py` |

---

## 6. Decision log

This section records why v0.2 made the choices it made. Implementers should not relitigate these without surfacing the change explicitly.

| # | Decision | Reasoning | Rejected alternative |
|---|---|---|---|
| D1 | Scope: HK-channel filter, not alpha tool | v1 over-claimed alpha; HK channel is honest, useful, narrow | "Universal stock screener" — out of scope, dishonest given inputs |
| D2 | US-listed equities only (ADRs in scope) | Free reliable PIT data exists for US only via EDGAR | Multi-market — would require non-existent free PIT data sources |
| D3 | One ranking, not three strategies | v1's three strategies implied parallel alpha sources we cannot defend | Three strategies — encourages over-interpretation |
| D4 | Quality as filter (PASS/FAIL), not ranker | Bottom-ranked stocks are not user-relevant; filtering is honest about not using them | Quality as continuous score — wastes precision on irrelevant stocks |
| D5 | Backtest removed entirely | v1's backtest claimed alpha validation it could not deliver given HK input bias | Reduced backtest — still misleading, removed honestly |
| D6 | Single crowding-discounted consensus signal | Two separate signals (consensus + crowding) would be highly correlated, suggesting independence we don't have | Two separate signals — false independence |
| D7 | Top N = 15 | Balance: enough to be useful (>10), few enough to read carefully (<20) | N=20 or N=10 — outside readability balance |
| D8 | English-only output | v1 bilingual doubled report length and complicated CJK rendering | Bilingual — token cost, font complexity, lower density |
| D9 | PDF rejection threshold: 5 holdings or 20% AUM | Below this, we have no signal from this fund; better to drop than fake | Lower threshold — risks including garbage data |
| D10 | Atomic delivery, no phase-by-phase ship | Real failure mode is structural (methodology issues), not local; partial ship would mislead | Phased ship — implies parts are useful in isolation |
| D11 | Hardcoded EDGAR UA + throttle, not env var | Skill must work in Claude.ai env where users can't set env vars | Env-var-required UA — would break for most users |
| D12 | v1 as iteration base, not from-scratch rebuild | ~30–40% of v1 modules are sound; rewriting them wastes effort | Full rewrite — wastes salvageable assets |

---

## 7. Report structure (English only)

### 7.1 Three layer markdown files

Each is independently readable and downloadable. Each ends with a "Next layer" pointer when applicable.

- `layer1_extraction.md` — Layer 1 output per §3.1.6
- `layer2_screening.md` — Layer 2 output per §3.2.7
- `layer3_ranked_advice.md` — Layer 3 output per §3.3.4

### 7.2 Final PDF: `financial_research_report.pdf`

Assembled from the three `.md` files plus cover/disclaimer wrappers. See §3.4 for section order. Estimated 20–22 pages typical.

### 7.3 Required prose sections

These are content-bearing sections that **must** appear, with **must-include** statements.

#### 7.3.1 Disclaimer (front and back)

Verbatim from `assets/disclaimer.md`. Must state:
- AI-generated, not investment advice
- Past data does not predict future returns
- Data sources may contain errors
- User assumes all responsibility for investment decisions

#### 7.3.2 Honest framing

Must include all four bias acknowledgments from §1.4 with the specific numbers from this run.

#### 7.3.3 Methodology disclosure

Must include:
- The exact ranking weights (0.50 / 0.50)
- The exact quality screen criteria
- Provider routing order and confidence baselines
- Sample size statement
- Explicit "this is not statistical significance" disclaimer

---

## 8. Acceptance criteria

v0.2 is complete only when **all** of the following pass. There is no partial ship.

### 8.1 Structural

- [ ] SKILL.md ≤ 150 lines
- [ ] No formula appears in two places (canonical location only)
- [ ] `import yfinance` appears in exactly one file (`providers/yfinance_provider.py`)
- [ ] `backtest.py`, `strategy_weights.py`, `fetch_macro_data.py` do not exist
- [ ] All `references/*.md` files contain zero executable code blocks

### 8.2 Functional

- [ ] Validation rejects non-fund PDFs with the educational message in §3.1.1
- [ ] PDF rejection threshold (5 holdings / 20% AUM) is enforced
- [ ] Sub-7-fund post-rejection halts pipeline with clear user message
- [ ] Non-US tickers are dropped at Stage 1b and reported in `layer1_extraction.md`
- [ ] ADRs (`BABA`, `TSM`, `ASML`, etc.) are kept and routed correctly
- [ ] Quality screen produces PASS/FAIL only, not a continuous score
- [ ] Screened-out stocks are disclosed in `layer2_screening.md` with reasons
- [ ] Composite ranking is a single number, not three
- [ ] Top N produced is exactly 15
- [ ] Cards are organized into Tier A / B / C groupings

### 8.3 Provider contract

- [ ] EDGARProvider hardcoded UA matches §3.2.2
- [ ] EDGARProvider throttle ≥ 100ms enforced
- [ ] EDGARProvider cache persists across runs (filings are immutable)
- [ ] EDGARProvider supports both 10-K and 20-F parsing
- [ ] yfinanceProvider is the only fallback path
- [ ] DataPoint shape includes value/confidence/source/asof/n_sources_agreed
- [ ] resolver.py implements the conflict resolution table in §3.2.3

### 8.4 Output

- [ ] Three layer `.md` files generated in `/home/claude/work/`
- [ ] Final PDF written to `/mnt/user-data/outputs/financial_research_report.pdf`
- [ ] PDF is English-only (no Chinese characters)
- [ ] PDF page count is in range [18, 26]
- [ ] Disclaimer appears on page 2 and on the final page
- [ ] Honest framing section appears before any ranking content
- [ ] Methodology disclosure section appears before the final disclaimer

### 8.5 Honest constraint

- [ ] No prose anywhere in output claims the ranking is "alpha"
- [ ] No prose anywhere in output claims statistical significance
- [ ] HK channel bias is named explicitly in at least three locations (framing, methodology, each card's bias note)

---

## 9. Out of scope (do not implement)

If asked to add any of these during implementation, surface the request and ask explicitly before proceeding. They are out of v0.2 scope by deliberate design:

- Non-US equities of any kind (foreign primary listings, foreign mutual funds, FX hedging)
- Backtest engine of any form
- Three or more strategy variants
- Portfolio weight construction (only ranking, no allocations)
- Real-time / intraday data
- Options, futures, fixed income, alternatives
- Sentiment / news / social media factors
- ESG scoring
- Multi-currency analysis (USD only)
- Bilingual outputs in any `.md`, `.pdf`, or persisted file
- Custom user-defined factor weights or thresholds (constants only)
- Live trading integration
- v1 backwards compatibility for outputs

---

## 10. Implementation order suggestion (not mandatory gates)

Per §6 D10: there is no phase-by-phase ship. The work is one atomic delivery. The order below is **suggested** to minimize rework, **not enforced** as gates.

1. **Read v1.** Walk through `/home/claude/financial-research-skill/` to map what exists.
2. **Delete and shrink first.** Remove backtest, strategy_weights, fetch_macro. Shrink SKILL.md per §5.1. This is fast and clarifies what remains.
3. **Build providers/.** Establish `DataPoint`, ABCs, registry, resolver. Refactor v1's yfinance code into `yfinance_provider.py`.
4. **Build EDGARProvider.** This is the highest-risk new component. Test against AAPL, MSFT, BABA (10-K and 20-F paths).
5. **Build PDFSnapshotProvider.** Lower risk; mostly bookkeeping.
6. **Reshape extraction.** Extend `extract_holdings.py` with US filtering, ADR handling, snapshot grouping.
7. **Build quality_screen.py and crowding_signal.py.** Both are small and independent.
8. **Rewrite build_rankings.py.** One formula, top 15, three tiers.
9. **Write the three layer report generators.** layer1, layer2, layer3.
10. **Rewrite build_report.py for PDF assembly.** Read three `.md` files, English-only output.
11. **Write references/ methodology readers.** With no code blocks.
12. **Walk through §8 acceptance criteria.** Fix gaps until every box ticks.

If, during step 4 or 6, you discover that EDGAR coverage or PDF extraction quality is materially worse than expected for HK-channel funds (e.g., <50% coverage), **stop and surface the problem before continuing**. This is the "structural failure" failure mode mentioned in §6 D10 — it requires methodology reconsideration, not local fixes.

---

## 11. Quick reference for implementation

**Working directory**: `/home/claude/financial-research-skill-v0.2/` (new path; keep v1 untouched at `/home/claude/financial-research-skill/` until v0.2 ships)

**Output paths**:
- Layered `.md`s: `/home/claude/work/layer{1,2,3}_*.md`
- Final PDF: `/mnt/user-data/outputs/financial_research_report.pdf`
- Provenance log: `/home/claude/work/data_provenance.json`

**Cache directory**: `/home/claude/work/cache/`
- EDGAR filings cached permanently by `(ticker, filing_id)`
- yfinance daily cache by `(ticker, date)`

**Skill packaging**: when v0.2 implementation is complete and all acceptance boxes tick, package via `python /mnt/skills/examples/skill-creator/scripts/package_skill.py /home/claude/financial-research-skill-v0.2/ /mnt/user-data/outputs/`.

---

## 12. Closing note

The most important word in this document is **honest**. v1 was technically functional but over-claimed alpha. v0.2 exists to deliver real value within real constraints — and to say so plainly when those constraints matter.

If during implementation you find yourself writing prose that hedges an honest limitation, stop and re-read §1.3 and §1.4. The right answer is almost always: state the limit, ship the value that remains.