"""
Provider registry — selects and routes data fetching per ticker.

Call order per ticker:
  1. EDGAR (true PIT, confidence 0.9)
  2. yfinance (degraded PIT, confidence 0.5) — for fill-in and conflict resolution
  3. mark as unscored if both fail

Overlapping fields (debt_equity, latest-year ROE) are merged through
`resolver.resolve()`, which logs any disagreement to a module-level provenance
log. The owner of the registry should call `flush_provenance()` at end of
processing to write the log to disk.
"""

from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

from .base import DataPoint, FundamentalsRecord
from .edgar_provider import EDGARProvider
from .resolver import flush_provenance as _flush_provenance, resolve
from .yfinance_provider import yfinanceProvider

log = logging.getLogger(__name__)


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


class ProviderRegistry:
    """Orchestrates provider calls in priority order with multi-source resolution."""

    def __init__(self, contact_email: Optional[str] = None):
        # B1 (v0.3): the SEC contact email flows into the EDGAR User-Agent.
        # kwarg wins; otherwise EDGARProvider falls back to EDGAR_CONTACT_EMAIL.
        self._edgar = EDGARProvider(contact_email=contact_email)
        self._yfinance = yfinanceProvider()

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

        # Fields EDGAR doesn't reliably provide — yfinance fills in
        if edgar_rec.ev_ebitda is None:
            edgar_rec.ev_ebitda = yf_rec.ev_ebitda
        if edgar_rec.market_cap is None:
            edgar_rec.market_cap = yf_rec.market_cap
        if edgar_rec.adv is None:
            edgar_rec.adv = yf_rec.adv
        if (edgar_rec.industry in (None, "other")
                and yf_rec.industry not in (None, "other")):
            edgar_rec.industry = yf_rec.industry

        # Overlapping fields — resolve through the conflict log
        edgar_rec.debt_equity = _merge_dp(
            edgar_rec.debt_equity, yf_rec.debt_equity
        )

        # ROE: EDGAR has 5y annual; yfinance has trailing only (broadcast x5).
        # Only the latest year is comparable — resolve against [-1].
        if edgar_rec.roe_5y and yf_rec.roe_5y:
            edgar_latest = edgar_rec.roe_5y[-1]
            yf_latest = yf_rec.roe_5y[-1]
            if (edgar_latest is not None and yf_latest is not None
                    and edgar_latest.value is not None
                    and yf_latest.value is not None):
                edgar_rec.roe_5y[-1] = _merge_dp(edgar_latest, yf_latest)

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
