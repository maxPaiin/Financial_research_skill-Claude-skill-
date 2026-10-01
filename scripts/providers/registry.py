"""
Provider registry — selects and routes data fetching per ticker.

Call order per ticker:
  1. EDGAR (true PIT, confidence 0.9)
  2. yfinance (degraded PIT, confidence 0.5) — for fill-in and conflict resolution
  3. mark as unscored if both fail

v0.34 (A4) — field-level fallback. Each field takes the EDGAR value when EDGAR
has one, otherwise the yfinance value. The ROE series is a field too: when
EDGAR has fewer than two defined years and yfinance has two or more, the
yfinance series is used whole, with its own confidence and source tags — so an
issuer EDGAR cannot read (or reads only partly) is scored on real yfinance
annual data instead of dropping out of the ranking unseen (F7).

Overlapping fields (debt_equity, the latest fiscal year of ROE) are merged
through `resolver.resolve()`, which logs any disagreement to a module-level
provenance log. A fiscal year is reconciled only against the same fiscal year:
SEC's companyfacts can lag a filing (TSMC's FY2025 20-F, filed 2026-04, was
not yet in it in 2026-10), and comparing EDGAR's FY2024 with yfinance's FY2025
would log a conflict that does not exist. The owner of the registry should call
`flush_provenance()` at end of processing to write the log to disk.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

from .base import DataPoint, FundamentalsRecord
from .edgar_provider import EDGARProvider
from .resolver import flush_provenance as _flush_provenance, resolve
from .yfinance_provider import yfinanceProvider

log = logging.getLogger(__name__)

# Two period ends name the same fiscal year when they are this close (Yahoo
# reports month ends: Apple's 2025-09-27 year end arrives as 2025-09-30).
_SAME_PERIOD_DAYS = 31
_MIN_ROE_YEARS = 2


def _merge_dp(
    primary: Optional[DataPoint],
    secondary: Optional[DataPoint],
) -> Optional[DataPoint]:
    """Reconcile two DataPoints for the same field.

    - Both None → None
    - One present → that one
    - Both present → resolver.resolve() (logs conflict if values disagree)
    """
    candidates = [p for p in (primary, secondary) if p is not None]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    return resolve(candidates)


def _defined(series: list[Optional[DataPoint]]) -> int:
    return sum(1 for dp in series or [] if dp is not None and dp.value is not None)


def _same_period(a: Optional[date], b: Optional[date]) -> bool:
    return a is not None and b is not None and abs((a - b).days) <= _SAME_PERIOD_DAYS


def _counterpart(latest: DataPoint, series: list[Optional[DataPoint]]) -> Optional[DataPoint]:
    """yfinance's value for EDGAR's latest fiscal year, if it has one.

    A lone trailing point (no period) is compared as v0.33 did; an annual
    value for a different fiscal year is not a counterpart at all.
    """
    defined = [dp for dp in series or [] if dp is not None and dp.value is not None]
    for dp in defined:
        if _same_period(dp.period_end, latest.period_end):
            return dp
    if len(series or []) == 1 and defined and defined[0].period_end is None:
        return defined[0]
    return None


class ProviderRegistry:
    """Orchestrates provider calls in priority order with multi-source resolution."""

    def __init__(self, contact_email: Optional[str] = None, edgar=None, yfinance=None):
        # B1 (v0.3): the SEC contact email flows into the EDGAR User-Agent.
        # kwarg wins; otherwise EDGARProvider falls back to EDGAR_CONTACT_EMAIL.
        # `edgar=` / `yfinance=` inject providers (tests, replayed runs).
        self._edgar = edgar if edgar is not None else EDGARProvider(contact_email=contact_email)
        self._yfinance = yfinance if yfinance is not None else yfinanceProvider()

    def fetch(
        self, ticker: str, asof: date
    ) -> tuple[Optional[FundamentalsRecord], str]:
        """
        Returns (record, source_name) where source_name is one of:
          - "edgar"           — EDGAR succeeded, yfinance unavailable or unused
          - "edgar+yfinance"  — EDGAR succeeded and yfinance contributed
                                fill-in fields or conflict-resolved values
          - "yfinance"        — EDGAR failed, yfinance served the record
          - "none"            — both providers returned nothing
        """
        edgar_rec: Optional[FundamentalsRecord] = None
        try:
            edgar_rec = self._edgar.fetch(ticker, asof)
        except Exception as e:
            log.warning("EDGAR failed for %s: %s", ticker, e)

        # EDGAR failed entirely → yfinance alone (no resolver needed)
        if edgar_rec is None:
            try:
                yf_rec = self._yfinance.fetch(ticker, asof)
            except Exception as e:
                log.warning("yfinance failed for %s: %s", ticker, e)
                yf_rec = None
            if yf_rec is None:
                return None, "none"
            return yf_rec, "yfinance"

        # EDGAR succeeded → fetch yfinance for fill-in + conflict resolution
        yf_rec: Optional[FundamentalsRecord] = None
        try:
            yf_rec = self._yfinance.fetch(ticker, asof)
        except Exception as e:
            log.warning("yfinance fill-in failed for %s: %s", ticker, e)

        if yf_rec is None:
            return edgar_rec, "edgar"

        # Field level: EDGAR when present, otherwise yfinance.
        for attr in ("ev_ebitda", "market_cap", "adv"):
            if getattr(edgar_rec, attr) is None:
                setattr(edgar_rec, attr, getattr(yf_rec, attr))
        if (edgar_rec.industry in (None, "other")
                and yf_rec.industry not in (None, "other")):
            edgar_rec.industry = yf_rec.industry
        if not any(dp is not None and dp.value is not None
                   for dp in edgar_rec.net_income_5y or []):
            edgar_rec.net_income_5y = list(yf_rec.net_income_5y or [])

        # Overlapping field — resolve through the conflict log
        edgar_rec.debt_equity = _merge_dp(
            edgar_rec.debt_equity, yf_rec.debt_equity
        )

        # ROE series: too thin on EDGAR, real on yfinance -> yfinance, whole.
        if (_defined(edgar_rec.roe_5y) < _MIN_ROE_YEARS
                and _defined(yf_rec.roe_5y) >= _MIN_ROE_YEARS):
            edgar_rec.roe_5y = list(yf_rec.roe_5y)
            edgar_rec.roe_undefined_years = list(yf_rec.roe_undefined_years or [])
        elif edgar_rec.roe_5y:
            # The latest fiscal year, reconciled against the same fiscal year.
            latest = edgar_rec.roe_5y[-1]
            if latest is not None and latest.value is not None:
                other = _counterpart(latest, yf_rec.roe_5y)
                if other is not None:
                    edgar_rec.roe_5y[-1] = _merge_dp(latest, other)

        return edgar_rec, "edgar+yfinance"

    def fetch_batch(
        self, tickers: list[str], asof: date
    ) -> dict[str, tuple[Optional[FundamentalsRecord], str]]:
        """Fetch a list of tickers. Returns dict of ticker → (record, source)."""
        return {tkr: self.fetch(tkr, asof) for tkr in tickers}

    def flush_provenance(self, path: Optional[Path] = None) -> Path:
        """Persist accumulated conflict log to data_provenance.json.

        Returns the path written (defaults to the resolver's canonical path).
        """
        return _flush_provenance(path) if path is not None else _flush_provenance()
