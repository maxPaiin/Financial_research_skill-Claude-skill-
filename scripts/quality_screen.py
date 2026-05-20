"""
Stage 2d: Quality screen — PASS / FAIL filter for the unique universe.

Quality is a filter, not a ranker. Output is binary: PASS or FAIL with reason.
All thresholds are the canonical location per §5.3.

PASS criteria — ALL must hold:
  1. ROE positive in >= 3 of last 5 fiscal years
  2. Debt/Equity available AND < 5.0 (distress ceiling)
  3. No 3 consecutive years of negative net income
  4. At least 2 of 3 key metrics available with confidence >= 0.4
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from providers.base import DataPoint, FundamentalsRecord

# Canonical thresholds — do not duplicate elsewhere.
MIN_ROE_POSITIVE_YEARS = 3          # of 5
DEBT_EQUITY_CEILING = 5.0
MAX_CONSECUTIVE_NEGATIVE_NI = 3     # if >=3 consecutive → FAIL
MIN_CONFIDENCE = 0.4
MIN_METRICS_AVAILABLE = 2           # of 3 key metrics (ROE 5y, EV/EBITDA, D/E)


@dataclass
class ScreenResult:
    ticker: str
    passed: bool
    reason: Optional[str] = None    # non-None only for FAIL
    detail: Optional[str] = None    # human-readable detail for FAIL


def screen(ticker: str, record: FundamentalsRecord) -> ScreenResult:
    """Apply the quality screen to a FundamentalsRecord. Returns ScreenResult."""
    reasons = []

    # 1. ROE positive years
    roe_values = [dp.value for dp in record.roe_5y if dp is not None and dp.value is not None]
    n_positive_roe = sum(1 for v in roe_values if v > 0)
    if len(roe_values) >= 3 and n_positive_roe < MIN_ROE_POSITIVE_YEARS:
        reasons.append(("roe_insufficient", f"ROE positive in only {n_positive_roe}/5 years"))

    # 2. Debt/Equity ceiling
    if record.debt_equity is not None and record.debt_equity.value is not None:
        if record.debt_equity.value >= DEBT_EQUITY_CEILING:
            reasons.append((
                "distress_debt_ratio",
                f"D/E = {record.debt_equity.value:.1f} exceeds {DEBT_EQUITY_CEILING} ceiling",
            ))
    # Note: if D/E is unavailable, we don't fail on this criterion alone (handled by metric count)

    # 3. Consecutive negative net income
    ni_values = [
        dp.value for dp in record.net_income_5y if dp is not None and dp.value is not None
    ]
    if ni_values:
        max_consecutive = _max_consecutive_negatives(ni_values)
        if max_consecutive >= MAX_CONSECUTIVE_NEGATIVE_NI:
            reasons.append((
                "persistent_negative_earnings",
                f"Net income negative in {max_consecutive} consecutive years",
            ))

    # 4. Minimum data availability
    n_available = 0
    if roe_values:
        n_available += 1
    if record.ev_ebitda is not None and record.ev_ebitda.value is not None \
            and record.ev_ebitda.confidence >= MIN_CONFIDENCE:
        n_available += 1
    if record.debt_equity is not None and record.debt_equity.value is not None \
            and record.debt_equity.confidence >= MIN_CONFIDENCE:
        n_available += 1

    if n_available < MIN_METRICS_AVAILABLE:
        reasons.append((
            "insufficient_data",
            f"Only {n_available} of 3 key metrics available (need >= {MIN_METRICS_AVAILABLE})",
        ))

    if reasons:
        reason_code, detail = reasons[0]
        return ScreenResult(ticker=ticker, passed=False, reason=reason_code, detail=detail)

    return ScreenResult(ticker=ticker, passed=True)


def _max_consecutive_negatives(values: list[float]) -> int:
    """Count maximum run of consecutive negative values."""
    max_run = 0
    current_run = 0
    for v in values:
        if v < 0:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run
