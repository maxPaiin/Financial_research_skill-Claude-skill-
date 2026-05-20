# Quality Screen Reference

This file explains the quality screen methodology.
It is a reader — no executable rules. The canonical thresholds live in `scripts/quality_screen.py`.

---

## What the screen is

A binary PASS/FAIL filter applied to every stock in the US equity universe before ranking.
Quality is a filter, not a ranker — bottom-ranked stocks are not user-relevant.

## PASS criteria (ALL must hold)

1. **ROE positive in >= 3 of last 5 fiscal years.**
   Ensures the company has a persistent record of generating returns, not a fluke year.
   Threshold: `MIN_ROE_POSITIVE_YEARS = 3` in `quality_screen.py`.

2. **Debt/Equity < 5.0** (if available).
   A sanity ceiling for financial distress. Highly leveraged companies pose unacceptable
   default risk for a conservative channel screen.
   Threshold: `DEBT_EQUITY_CEILING = 5.0` in `quality_screen.py`.

3. **No 3 consecutive years of negative net income.**
   Distinguishes a temporarily loss-making company (acceptable) from one with structural
   inability to turn a profit (not acceptable).
   Threshold: `MAX_CONSECUTIVE_NEGATIVE_NI = 3` in `quality_screen.py`.

4. **At least 2 of 3 key metrics available with confidence >= 0.4.**
   Ensures we have enough data to make the screen meaningful. If a stock is so opaque
   we can't retrieve basic fundamentals, we cannot honestly rank it.
   Threshold: `MIN_METRICS_AVAILABLE = 2`, `MIN_CONFIDENCE = 0.4` in `quality_screen.py`.

## FAIL behavior

Stocks that fail are:
- Excluded entirely from Layer 3 ranking.
- Disclosed in `layer2_screening.md` with their specific failure reason and detail.
  This allows the user to audit the screen and understand what was removed.

## What the screen does NOT do

- It does not rank screened-out stocks against each other.
- It does not consider price momentum, sentiment, or ESG factors.
- It does not filter by industry (industry caps are not applied at screen time).
- It does not use the crowding signal.

## Why ROE 5y average as the single quality metric for ranking (Stage 2e)

After passing the binary screen, stocks are scored on ROE 5y average alone:
- Most discriminating single number for "is this a quality business."
- 5-year average dampens single-year noise without requiring 10+ years of data.
- More universally available across ADRs than EV/EBITDA.
- Already screened against persistent-negative-ROE, so ROE avg is meaningful.

The percentile rank formula is in `scripts/compute_scores.py`.
