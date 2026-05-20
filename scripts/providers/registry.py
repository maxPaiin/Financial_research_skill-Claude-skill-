"""
Provider registry — selects and routes data fetching per ticker.

Call order per ticker: EDGARProvider → yfinanceProvider → mark as unscored.
No fabrication: if both fail, the ticker is returned as None.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from .base import FundamentalsRecord
from .edgar_provider import EDGARProvider
from .yfinance_provider import yfinanceProvider

log = logging.getLogger(__name__)


class ProviderRegistry:
    """Orchestrates provider calls in priority order."""

    def __init__(self):
        self._edgar = EDGARProvider()
        self._yfinance = yfinanceProvider()

    def fetch(self, ticker: str, asof: date) -> tuple[Optional[FundamentalsRecord], str]:
        """
        Returns (record, source_name) where source_name is "edgar" | "yfinance" | "none".
        """
        # 1. Try EDGAR (true PIT, confidence 0.9)
        try:
            record = self._edgar.fetch(ticker, asof)
            if record is not None:
                # EDGAR may have missing EV/EBITDA — fill from yfinance if available
                if record.ev_ebitda is None or record.market_cap is None:
                    yf_record = self._yfinance.fetch(ticker, asof)
                    if yf_record:
                        if record.ev_ebitda is None:
                            record.ev_ebitda = yf_record.ev_ebitda
                        if record.market_cap is None:
                            record.market_cap = yf_record.market_cap
                        if record.adv is None:
                            record.adv = yf_record.adv
                        if record.industry == "other" and yf_record.industry != "other":
                            record.industry = yf_record.industry
                return record, "edgar"
        except Exception as e:
            log.warning("EDGAR failed for %s, falling through to yfinance: %s", ticker, e)

        # 2. Fall through to yfinance (degraded PIT, confidence 0.5)
        try:
            record = self._yfinance.fetch(ticker, asof)
            if record is not None:
                return record, "yfinance"
        except Exception as e:
            log.warning("yfinance also failed for %s: %s", ticker, e)

        return None, "none"

    def fetch_batch(
        self, tickers: list[str], asof: date
    ) -> dict[str, tuple[Optional[FundamentalsRecord], str]]:
        """Fetch a list of tickers. Returns dict of ticker → (record, source)."""
        results = {}
        for tkr in tickers:
            results[tkr] = self.fetch(tkr, asof)
        return results
