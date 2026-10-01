# Providers Reference

This file explains provider routing, confidence rationale, and the EDGAR contract.
It is a reader — no executable rules. Canonical locations are per §5.3 of Iteration_0.2v.md.

---

## Provider routing order

For each ticker, the registry (`scripts/providers/registry.py`) tries providers in this order:

1. **EDGARProvider** — true point-in-time fundamentals from SEC EDGAR filings.
   Baseline confidence: 0.9 (canonical in `providers/base.py` `DEFAULT_CONFIDENCE`).

2. **yfinanceProvider** — degraded-PIT fallback. Current values projected back;
   not true point-in-time.
   Baseline confidence: 0.5 (canonical in `providers/base.py`).

3. **Mark as unscored** — if both fail, the ticker is excluded from ranking.
   No fabrication of data.

## DataPoint shape

Every provider returns `DataPoint` objects with these fields (defined in `providers/base.py`):

```
DataPoint:
  value            — float or None
  confidence       — float 0.0–1.0
  source           — string, e.g. "edgar:10-K-2024" or "yfinance:2025-05"
  asof             — date of the data point
  n_sources_agreed — int, number of sources that agreed (default 1)
```

## EDGAR contract (canonical in `providers/edgar_provider.py`)

- User-Agent: `"FinancialResearchSkill-v0.3 <contact-email>"` (B1, v0.3). SEC requires a
  contact email in the request header; without it EDGAR returns **403 Forbidden**. The email
  is user-supplied, gated at Stage 0 (`validate_uploads.py --email`), and injected via the
  `contact_email=` kwarg on `ProviderRegistry` / `EDGARProvider` or the `EDGAR_CONTACT_EMAIL`
  env var — **never hardcoded**. It is placed ONLY into this header (SEC's stated use:
  contacting the operator if the script misbehaves); it is not stored or transmitted
  elsewhere.
- Throttle: minimum 100 ms between requests (≤ 10 req/s, SEC's published fair-access
  rate). SEC publishes a rate limit, not a daily quota (v0.34): there is no daily budget,
  only a 10,000-request runaway guard that logs a WARNING.
- Ticker map (v0.34): `https://www.sec.gov/files/company_tickers_exchange.json` —
  ticker → CIK, issuer name and listing exchange, parsed by field name. Cached under
  `ticker_exchange_map` and refreshed when older than 7 days (an operational TTL with no
  effect on scores). `data.sec.gov` serves only the companyfacts and submissions
  endpoints. Share classes resolve in either form: `BRK.B` (internal) and `BRK-B` (SEC).
- Cache: companyfacts and submissions by CIK.
- Retry on HTTP 429: exponential backoff 1s → 2s → 4s, then fall through to yfinance.
- Filers: 10-K (US domestic) and 20-F / 40-F (foreign private issuers). The annual form
  is the newest one in the submissions list.
- Taxonomies (v0.34): `us-gaap` first, then `ifrs-full`; for each item the first
  candidate concept with current data wins (`CONCEPTS` in `edgar_provider.py`).
- Units (v0.34): a ratio (ROE, D/E) is built only from a numerator and a denominator in
  the **same unit for the same period end**. Ratios are dimensionless, so a TWD- or
  EUR-reporting filer needs no conversion, and units never mix within a series or a ratio.
  The shared unit carrying the most facts — the reporting currency — is used; USD only
  breaks ties. Recorded filings showed why "USD whenever present" is wrong: TSMC also tags
  a USD convenience translation of each 20-F year (9 facts against 25 in TWD), and SAP
  carries one USD fact against 41 in EUR. The record carries `taxonomy` and
  `reporting_currency` for display only.
- Stale tags and taxonomies: issuers change tags (`NetIncomeLoss` → `ProfitLoss`) and even
  taxonomies (Toyota and Sony moved from US GAAP to IFRS in 2020–21). A candidate whose
  latest period ends more than two years before the request never beats a current one.
- Negative or zero equity (v0.34): that year's ROE is left undefined and listed in
  `roe_undefined_years` (a loss over negative equity would otherwise read as a positive
  ROE), and D/E is undefined whenever the latest equity is ≤ 0.
- No usable facts → the provider returns nothing, so the registry falls back to yfinance.

## ADR handling

ADRs (`BABA`, `TSM`, `ASML` in US ADR form, etc.) are in scope — they trade on US exchanges.

- EDGAR: 20-F and 40-F filers are read through `ifrs-full` (or `us-gaap` when they file
  under it), in their reporting currency; if EDGAR has nothing usable, fall through to
  yfinance with degraded confidence.
- yfinance: ADR detection via `info["country"]` ≠ "United States".
- ADR status is flagged in FundamentalsRecord and surfaces in Layer 3 cards.

## Conflict resolution

When multiple providers return values for the same (ticker, field):

| diff_pct | Action |
|---|---|
| < 5% | Mean; confidence = max of inputs |
| 5–20% | Higher-confidence source; log dispersion warning |
| >= 20% | Higher-confidence source; confidence × 0.5; log to `data_provenance.json` severity=high |

3+ sources: median; halve confidence if max−min > 20% of median.

Canonical thresholds in `providers/resolver.py`.
