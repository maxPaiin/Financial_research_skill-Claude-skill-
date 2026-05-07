# Financial-Research Skill — Iteration Plan 
---

## 0. Context

### 0.1 v1 recap

The v1 skill (already shipped as `financial-research-skill.skill`, ~3050 lines) implements an 11-stage pipeline that:

- Validates 7-11 fund prospectus PDFs
- Extracts holdings into a unified universe
- Scores stocks on industry / growth / quality_value (+ optional momentum)
- Produces three strategy composites (Growth / Conservative / Risk-avoidance)
- Aggregates to fund level
- Analyzes cross-fund overlap and concentration
- Runs a monthly-rebalanced backtest
- Synthesizes a forward investment view
- Produces a bilingual PDF report

It works end-to-end on smoke tests but has **four structural debts** identified in code review.

### 0.2 The four debts (and the user's decisions)

| # | Debt | User's v2 decision |
|---|---|---|
| 1 | SKILL.md mixes orchestration with business rules; references duplicate script logic | Slim SKILL.md to orchestration only |
| 2 | yfinance is hard-coded across multiple scripts; cannot mock, swap, or run offline | Adapter-based pluggable data sources |
| 3 | Backtest uses current fundamentals as proxy for entire window (lookahead bias); monthly granularity is finer than free PIT data supports | Yearly granularity; true PIT; **US-only**; **PDF multi-period snapshots count as a PIT source** |
| 4 | Missing-data handling collapses to renormalization, treating partial coverage as full coverage; no multi-source conflict policy | Per-factor confidence weighting; explicit conflict resolution policy |

### 0.3 Critical scope reduction (NEW in v2)

> **The skill targets US equities only.** Non-US tickers in fund holdings will be flagged as out-of-scope and excluded from scoring/backtest. The fund-level rollup will still report total AUM and disclose the excluded portion.

This is a major simplification — it removes the FX regime logic, multi-market industry mapping, and ADR/dual-listing edge cases that bloated v1's `INDUSTRY_MAP` and `fetch_macro_data.py`.

### 0.4 Critical scope expansion (NEW in v2)

> **PDF prospectuses themselves are a PIT data source.** When a user uploads multiple quarterly snapshots of the same fund (or different funds with overlapping report dates spanning years), the holdings extracted from each PDF become point-in-time data points. This is the strongest available PIT signal for fund-level analysis and replaces the lookahead-biased "current holdings as proxy" assumption.

---

## 1. Assessment of the four-point strategy

### 1.1 What this strategy gets right

- **Provider abstraction first** is the correct sequencing. Without it, PIT (#3) and confidence (#4) cannot land cleanly.
- **US-only** is honest. Free, reliable PIT data exists for US equities (SEC EDGAR XBRL filings). For non-US it does not. Pretending otherwise was v1's main intellectual fragility.
- **Yearly granularity** matches what free PIT data can actually deliver (10-K filings are annual; 10-Q quarterly). Monthly was over-promising.
- **PDF as PIT source** is the design insight that turns this skill's input constraint into a data advantage. Most quant tools throw the prospectus PDF away after extracting holdings; we keep the asof-date metadata and use it.
- **Confidence weighting** fixes a real bug: a stock with only 1 of 4 factors available currently scores the same as one with 4 of 4, because the renormalization step erases the information.

### 1.2 What this strategy under-specifies

These are points the plan needs to commit to before implementation, not after:

1. **Definition of "PIT"** — strict ("all data must have asof ≤ portfolio decision date") or pragmatic ("fundamentals from filings ≤ asof; price data may include 1-day lag")? The standard pragmatic definition is what we'll use; making this explicit prevents religious arguments later.

2. **Survivorship handling** — yfinance is survivorship-biased; EDGAR is not (delisted filings persist). The plan must specify when each is consulted, because mixing them silently re-introduces survivorship bias even with EDGAR.

3. **What happens when EDGAR doesn't have a ticker** — small caps, recent IPOs, OTC. Three options: (a) drop, (b) fall back to yfinance with `pit_quality=degraded`, (c) fail loudly. The plan picks (b) with explicit reporting. This needs to be enforced in the provider interface, not improvised.

4. **Fund-level vs stock-level PIT** — fund holdings PDFs give a PIT snapshot of *what the fund held on date X*. This is fund-level PIT. Individual stock fundamentals at date X come from EDGAR (true PIT) or yfinance (degraded PIT). These are different signals, used in different stages, and the plan must keep them visually distinct in code and in the report.

5. **Backwards-compatibility break** — going from monthly to yearly backtest invalidates v1's stored backtest results. Anyone who shipped v1 reports cannot reconcile them with v2 reports. v2 must explicitly version the report format and refuse to merge v1 outputs.

### 1.3 Risks accepted with this plan

| Risk | Mitigation |
|---|---|
| EDGAR rate-limits or schema changes | Cache aggressively; pin XBRL parser to specific element names; fall back to yfinance with explicit degradation flag |
| Yearly backtest produces only 1-5 data points for the 1y/3y/5y windows — statistical significance is poor | Disclose loudly in the report; supplement with rolling 1-year windows where data length allows |
| Users may paste in non-US fund prospectuses anyway | Stage 0 validation rejects upfront with bilingual message; do NOT silently filter |
| PDF-as-PIT extraction is messy in practice (different fund issuers format differently) | Per-issuer extraction templates; LLM-driven extraction with structured-output validation; if neither works for a given PDF, fall back to "current snapshot only" with degradation flag |
| Confidence weighting math can produce unintuitive results when most factors are missing | Floor: if `overall_confidence < 0.4`, output `score: null` with `reason: "insufficient_data"` instead of a misleading number |

### 1.4 Strategy verdict

The four-point strategy is **directionally correct and tightly scoped**. The two scope decisions (US-only + PDF-as-PIT) materially improve feasibility. Provider abstraction sequencing is right. The main execution risks are EDGAR robustness and PDF-extraction template maintenance, both of which I'll handle with explicit fallbacks and degradation flags rather than by hiding the problem.

---

## 2. Target architecture

### 2.1 Layer diagram

```
┌──────────────────────────────────────────────────────────────┐
│  SKILL.md (~120 lines)                                       │
│  Orchestration only: pipeline order, output paths, error     │
│  recovery decision tree. NO formulas, NO weights, NO buckets.│
└──────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  scripts/ (deterministic computation)                        │
│                                                              │
│  Each script's docstring is THE source of truth for its      │
│  formulas. references/ explains, never duplicates.           │
└──────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  scripts/providers/ (NEW)                                    │
│  ┌─────────────────────┐    ┌─────────────────────┐          │
│  │ MarketDataProvider  │◄──┤ EDGARProvider       │ true PIT │
│  │ (ABC)               │   │ YFinanceProvider    │ degraded │
│  │                     │   │ CSVProvider         │ user PIT │
│  │                     │   │ PDFSnapshotProvider │ fund PIT │
│  └─────────────────────┘   └─────────────────────┘          │
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────┐          │
│  │ MacroDataProvider   │◄──┤ FREDProvider        │           │
│  │ (ABC)               │   │ YFinanceMacroProv.  │           │
│  └─────────────────────┘   └─────────────────────┘          │
└──────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  All values flow as DataPoint{value, confidence, source,     │
│  asof, n_sources_agreed} — never as raw floats.              │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Single source of truth: where each fact lives

| Fact | v1 location (problematic) | v2 location (canonical) |
|---|---|---|
| Strategy weights (0.20/0.60/0.20...) | `references/strategy_weights.md` AND `scripts/strategy_weights.py` | `scripts/strategy_weights.py` docstring + module constants only |
| Industry bucket map | `references/data_sources.md` AND `scripts/fetch_market_data.py` | `scripts/providers/industry_map.py` (constants module) |
| Stop-loss / industry cap thresholds | `references/backtest_methodology.md` AND `scripts/backtest.py` | `scripts/backtest.py` constants section |
| Scoring formulas | `references/scoring_playbook.md` AND `scripts/compute_scores.py` | `scripts/compute_scores.py` docstring |
| Disclaimer text | `assets/disclaimer.md` | unchanged (asset by definition) |

`references/` becomes a **methodology reader** — it explains *why* the formulas are what they are and points to the script. It contains no executable rules.

---

## 3. The core data type

Every value crossing a provider boundary uses this:

```python
@dataclass(frozen=True)
class DataPoint:
    value: float | None
    confidence: float            # 0.0 to 1.0
    source: str                  # e.g., "edgar:10-K-2024Q4", "yfinance:2025-05-06"
    asof: date                   # the date the value was true / reported
    n_sources_agreed: int = 1    # how many sources gave a consistent value

    def with_confidence(self, c: float) -> "DataPoint": ...
    def is_usable(self, threshold: float = 0.3) -> bool: ...
```

### 3.1 Confidence baseline by source

| Source | Default confidence |
|---|---|
| User-uploaded CSV (explicit override) | 1.0 |
| EDGAR XBRL (10-K / 10-Q parsed clean) | 0.9 |
| Fund prospectus PDF (holdings/asof clearly stated) | 0.85 |
| EDGAR XBRL (parsed with warnings) | 0.7 |
| yfinance current fundamentals | 0.6 |
| yfinance historical fundamentals (degraded PIT) | 0.4 |
| Computed/derived (e.g., revision = (t - t-1) / t-1) | min(input confidences) |

### 3.2 Conflict resolution

When two sources give different values for the same (ticker, field, asof):

```
diff_pct = |v1 - v2| / max(|v1|, |v2|)

if diff_pct < 0.05:
    return mean, confidence = max(c1, c2)
elif diff_pct < 0.20:
    return source with higher confidence, log dispersion warning
else:
    if either source is "user csv":
        return user csv value, confidence = 1.0
    else:
        return value from source with higher confidence,
        confidence *= 0.5  # because we found a real disagreement
        log to data_provenance.json with severity="high"
```

Three+ sources: take median, halve confidence if max-min > 0.20 × median.

---

## 4. Phased roadmap

### Phase A — Slim SKILL.md, deduplicate references (1-2 hours)

**Scope**: pure refactoring. Move executable content out of SKILL.md and references; turn references into methodology readers.

**Deliverables**:
- SKILL.md goes from 327 lines to ~120 lines (orchestration table, error decision tree, output contract — that's it)
- `references/scoring_playbook.md` becomes a "what these scores mean and why" doc, no Python snippets
- `references/strategy_weights.md` similar
- `references/backtest_methodology.md` similar
- `references/data_sources.md` rewritten as "provider contract" (replaces the yfinance-specific cookbook)
- All formulas live in `scripts/*.py` docstrings only

**Tests**:
- v1 smoke tests still pass (`validate_uploads.py` empty dir, `extract_holdings.py` synthetic 2-fund)
- `quick_validate.py` still passes
- Diff review: every formula in the deleted reference content is verified to exist in a script docstring

**Risk**: Low. No behavior change.

**Acceptance**: SKILL.md ≤ 150 lines AND no formula appears in two places.

---

### Phase B — Provider abstraction (4-6 hours)

**Scope**: introduce `scripts/providers/` with ABCs and refactor existing fetch scripts to use them. Behavior unchanged at this phase — yfinance is still the only real provider.

**Deliverables**:

```
scripts/providers/
├── __init__.py
├── base.py                  # MarketDataProvider, MacroDataProvider, DataPoint
├── industry_map.py          # US-only industry buckets (constants)
├── yfinance_provider.py     # wraps existing yfinance logic, returns DataPoints
├── csv_provider.py          # loads /home/claude/work/user_data/*.csv if present
├── pdf_snapshot_provider.py # extracts asof-keyed holdings (Phase C will deepen this)
└── registry.py              # discover & instantiate providers per config
```

`fetch_market_data.py` and `fetch_macro_data.py` become thin shells that:
1. Read `config.yaml` (or default) to pick provider
2. Iterate the universe
3. Call `provider.get_fundamentals(ticker, asof=today)` for each
4. Write the same `market.json` shape as before (now with confidence/source metadata)

**Cross-cutting**: `compute_scores.py` updated to read DataPoint shape (with backwards-compatible fallback for raw floats during transition).

**Tests**:
- Unit: mock provider returns canned values → scoring produces expected output
- Integration: yfinance provider against 5 known tickers → market.json matches v1 shape (plus new metadata fields)
- New smoke: `CSVProvider` loaded from a test CSV → end-to-end pipeline runs offline

**Risk**: Medium. Refactor touches every fetch path. Gated by full smoke-test pass.

**Acceptance**: yfinance import appears in exactly one file (`yfinance_provider.py`); pipeline runs offline with `CSVProvider` only.

---

### Phase C — Yearly granularity + true PIT (1 day)

**Scope**: rebuild the time dimension. Backtest goes monthly→yearly; fundamentals at any asof date come from a real PIT source when available.

**C.1 — EDGARProvider** (the new true-PIT source)

- Fetches 10-K and 10-Q filings via SEC EDGAR's free XBRL API (`data.sec.gov`)
- Returns `DataPoint(asof=filing_date, confidence=0.9)` for: PE, ROE, EV/EBITDA proxies, EPS
- Required: `User-Agent` header per SEC policy (skill contract: skill author must set `EDGAR_USER_AGENT` env var, format `"AppName email@domain"`)
- Cache aggressively: filings don't change once filed; cache by `(ticker, filing_id)` permanently
- Fallback: if a ticker has no EDGAR coverage (most small caps, ADRs, OTC), return `None` and let registry try yfinance with degraded confidence
- US-only by design; this matches the v2 scope decision

**C.2 — PDFSnapshotProvider** (the new fund-level PIT source)

- Reads all uploaded PDFs and groups them by `(fund_family, reporting_date)`
- Each fund's holdings at each reporting date becomes a PIT snapshot at `asof = reporting_date`
- For backtest purposes: at each yearly rebalance date, look up the most recent snapshot ≤ that date
- Confidence 0.85 (we trust the prospectus, but it's only top-N holdings, not full portfolio)
- If only one snapshot per fund is uploaded, this provider returns it for all asof dates with `pit_quality="single_snapshot"` flag

**C.3 — Backtest rewrite**

- Granularity changes: monthly → yearly rebalance
- Window definitions: 1y = last 12 months from today; 3y = last 36 months; 5y = last 60 months
- For each yearly rebalance date, score every stock using `provider.get_fundamentals(ticker, asof=rebalance_date)`
- Stop-loss check: still daily-monitored conceptually, but applied at next yearly rebalance (acknowledged limitation, flagged in report)
- Industry cap (30%): unchanged
- Equal-weight top 20%: unchanged
- New output field: `pit_quality_per_period`, listing what fraction of universe got true-PIT vs degraded data per rebalance date

**C.4 — Statistical-significance disclosure**

- 1y window = 1 yearly observation. Sharpe is meaningless. Report only CAGR with a "single-period" warning.
- 3y = 3 observations. Still poor; report CAGR + simple stdev with caveat.
- 5y = 5 observations. Marginal; report CAGR + Sharpe with caveat.
- Add rolling-1y-windows analysis: if we have 5y of data, we have 5 overlapping rolling 1y windows for each rebalance — gives more statistical heft, with autocorrelation disclosed.

**Tests**:
- EDGARProvider against AAPL — verify 5y of 10-K filings parse cleanly
- PDFSnapshotProvider with synthetic 2-snapshot fund — verify asof routing
- Backtest end-to-end: yearly granularity produces sensible CAGR and the `pit_quality_per_period` field is populated
- Backwards-incompat test: refuse to consume v1 backtest.json (schema version check)

**Risk**: High. This is the largest change. EDGAR XBRL parsing has corner cases. Yearly backtests have low statistical power and may produce uncomfortable result variance — that's *correct* but users may misinterpret.

**Acceptance**: For at least one US-equity-only fund prospectus, the backtest reports `pit_quality_per_period` with ≥ 80% of universe-stocks having true-PIT data at each rebalance, and the report explicitly states statistical-significance caveats.

---

### Phase D — Confidence propagation (4-6 hours)

**Scope**: turn DataPoint's confidence field from informational metadata into something that affects scores.

**D.1 — Scoring with confidence**

```python
def confidence_weighted_score(factor_pairs):
    """factor_pairs: List[(value, weight, confidence)]"""
    usable = [(v, w, c) for v, w, c in factor_pairs if v is not None and c >= 0.3]
    if not usable:
        return None, 0.0
    total_w = sum(w * c for _, w, c in usable)
    weighted = sum(v * w * c for v, w, c in usable)
    score = weighted / total_w
    overall_conf = total_w / sum(w for _, w, _ in factor_pairs)
    return score, overall_conf
```

Floor: if `overall_conf < 0.4`, output `None` with reason — don't pretend to score a stock with only 1 of 4 factors.

**D.2 — Conflict resolver**

`scripts/providers/resolver.py`:
```python
def resolve(datapoints: list[DataPoint]) -> DataPoint:
    """Merge multiple DataPoints for the same (ticker, field, asof)."""
    # Implements §3.2 of this doc
```

**D.3 — Provenance tracking**

New file `/home/claude/work/data_provenance.json`:
```json
{
  "AAPL": {
    "pe": {
      "value": 28.4,
      "confidence": 0.9,
      "sources": [{"name": "edgar:10-K-2024Q4", "value": 28.4, "asof": "2024-09-28"}],
      "asof": "2024-09-28"
    },
    "roe": {
      "value": 0.171,
      "confidence": 0.45,
      "sources": [
        {"name": "edgar:10-K-2024Q4", "value": 0.171, "asof": "2024-09-28"},
        {"name": "yfinance:2025-05-06", "value": 0.198, "asof": "2025-05-06"}
      ],
      "conflict": {"diff_pct": 0.158, "policy": "took_higher_confidence"},
      "asof": "2024-09-28"
    }
  }
}
```

**D.4 — Report changes**

- Each score in the per-stock appendix shows `score (confidence)`: e.g., `growth_score: 65 (0.78)`
- Stocks with low overall confidence get a row-level warning icon
- New report section: "Data quality summary" listing per-source coverage, conflict count, low-confidence stocks
- Methodology section gets a paragraph on confidence weighting

**Tests**:
- Stock with 1/4 factors → score = None, reason logged
- Stock with 4/4 high-confidence factors → score matches v1 unweighted-version output
- Two providers conflict by 25% → resolver picks higher-confidence source, halves confidence, logs to provenance
- Two providers conflict by 3% → resolver returns mean, keeps confidence

**Risk**: Medium. The math is simple. The interaction with v1's `safe_blend` renormalization is the trap — must remove `safe_blend` and use `confidence_weighted_score` everywhere, no half-migrations.

**Acceptance**: Provenance file exists for every report run; no score is reported without an associated confidence; conflict resolution policy is exercised by at least one test case.

---

### Phase E — Evals and acceptance (4-6 hours)

**Scope**: write the test cases that prove the four debts are paid down.

**E.1 — Test corpus**

Synthetic fund PDFs covering:
1. Single fund, single snapshot, 5 well-covered US large caps
2. Single fund, 4 quarterly snapshots over 1 year (tests PDFSnapshotProvider)
3. 8 funds, 1 snapshot each, mixed large/mid-cap US (tests universe dedup + scoring)
4. 8 funds with 1 small-cap that has no EDGAR coverage (tests degraded fallback)
5. 8 funds where 2 list the same stock with different asof dates (tests resolver)
6. 8 funds, one with a non-US holding (tests US-only scope rejection)
7. 8 funds, full 5y of quarterly snapshots for 3 funds (tests PDF-as-PIT richness)

**E.2 — Evaluation criteria**

| Criterion | Metric | Target |
|---|---|---|
| Orchestration purity | grep `0\.20\|0\.60\|0\.30` in SKILL.md and references/ | 0 hits |
| Provider isolation | grep `import yfinance` outside `scripts/providers/` | 0 hits |
| PIT honesty | every score in scores_per_stock.json has a non-null `asof` and `confidence` | 100% |
| US-only scope | non-US tickers in test 6 are rejected at Stage 0 with bilingual message | yes |
| PDF-as-PIT works | test 2 produces 4 distinct snapshots in PDFSnapshotProvider output | yes |
| Conflict resolution | test 5 produces a `conflicts` entry in data_provenance.json | yes |
| Confidence floor | test 4's small-cap with only 1 factor available gets `score: null, reason: "insufficient_data"` | yes |
| Report integrity | test 3's PDF includes "Data quality summary" section | yes |
| Backwards compat | running v2 on test 3 produces no NaNs in the report | yes |

**E.3 — Skill-creator integration**

Use `/mnt/skills/examples/skill-creator/` framework:
- Test prompts in `evals/prompts.jsonl`
- Quantitative scoring per criterion above
- `eval-viewer/generate_review.py` to surface results

**Risk**: Low (this is just measurement). The tests will likely surface 1-2 bugs; budget time to fix them before declaring v2 done.

---

## 5. Out of scope for v2

Documented here so they don't accidentally creep in:

- Non-US equities (no JP/HK/TW/CN/EU support)
- Real-time intraday data
- Options / futures / fixed income
- ESG scoring
- Sentiment / news / social media factors
- Custom user-defined factors (users can edit scripts; v2 doesn't expose a config DSL)
- Multi-currency portfolios (US-only implies USD-only)
- Tax-aware backtesting
- Live trading integration
- Backtest result comparison against v1 (schema break is intentional)

---

## 6. Effort and sequencing

| Phase | Effort | Blocked by |
|---|---|---|
| A — Slim SKILL.md | 1-2h | Nothing |
| B — Provider abstraction | 4-6h | A (cleaner refactor surface) |
| C — Yearly + PIT | 1 day | B |
| D — Confidence | 4-6h | B (uses DataPoint) |
| E — Evals | 4-6h | A, B, C, D |

**Total**: ~3 working days, sequential.

C and D can be partially parallel if I split a single working day into "C in the morning, D in the afternoon" — they share the DataPoint type but touch different scripts. I'll keep them sequential for the first pass to avoid merge conflicts, but flag this as an optimization for a second hand.

---

## 7. Open questions for the user before Phase A starts

The strategy is locked, but two execution-level questions remain:

### Q1. EDGAR User-Agent

SEC requires a real `User-Agent` (e.g., `"FinancialResearchSkill operator-name@email.com"`). The skill itself has no operator email. Options:

- **(a)** Generic UA `"FinancialResearchSkill claude-user@anthropic.com"` — works but technically violates SEC's "identifying" requirement
- **(b)** Require the skill user to set `EDGAR_USER_AGENT` env var; fail loudly if absent
- **(c)** Document the UA requirement in SKILL.md and have Stage 2 prompt the user once if env var is missing

My default would be **(b)** with clear error messaging. Acceptable?

### Q2. Reverting v1 PDF reports

Once v2 ships, anyone re-running on inputs that previously produced a v1 report will get materially different numbers (yearly vs monthly, EDGAR vs yfinance fundamentals, US-only filtering). Options:

- **(a)** v2 silently overwrites; user notices the difference
- **(b)** v2 detects v1 outputs in `/home/claude/work/` and refuses to overwrite without `--force`
- **(c)** v2 writes to `/home/claude/work_v2/` to preserve v1 outputs

My default would be **(b)** — explicit user action required. Acceptable?

---

## 8. Definition of done

v2 is complete when:

1. SKILL.md is under 150 lines and contains no formulas, weights, or thresholds
2. `import yfinance` appears in exactly one file
3. Every score in the output has a `confidence` and `asof` field
4. The backtest's `pit_quality_per_period` field shows ≥ 80% true-PIT coverage on the EDGAR-eligible US universe
5. All 7 eval test cases in §E.1 pass
6. Report includes a "Data quality summary" section
7. v2 refuses to consume v1 outputs (schema versioning works)
8. Documentation (this file + updated references/) describes the new architecture without referring to the old one

Anything short of all 8 is not v2 — it's a partial migration, which is the worst of both worlds.
