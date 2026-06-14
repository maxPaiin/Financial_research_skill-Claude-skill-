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
- Throttle: minimum 100 ms between requests (≤ 10 req/s, per SEC fair-use policy).
- Daily budget: 600 requests per session.
- Cache: permanent by `(ticker, filing_id)` — filings are immutable.
- Retry on HTTP 429: exponential backoff 1s → 2s → 4s, then fall through to yfinance.
- Supports: 10-K (US domestic) and 20-F (ADR / foreign filers).

## ADR handling

ADRs (`BABA`, `TSM`, `ASML` in US ADR form, etc.) are in scope — they trade on US exchanges.

- EDGAR: try 20-F first; if absent, fall through to yfinance with degraded confidence.
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
