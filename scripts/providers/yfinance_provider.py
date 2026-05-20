"""
yfinance provider — degraded-PIT fallback (refactored from v1 fetch_market_data.py).

Confidence baseline: 0.5 (current values projected back, not true PIT).
This is the only file that imports yfinance — canonical per §8.1 acceptance criteria.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import yfinance as yf

from .base import DataPoint, FundamentalsRecord, FundamentalsProvider, DEFAULT_CONFIDENCE
from .industry_map import normalize as normalize_industry

log = logging.getLogger(__name__)


class yfinanceProvider(FundamentalsProvider):
    """Fetches fundamentals and market data from yfinance with degraded PIT confidence."""

    @property
    def name(self) -> str:
        return "yfinance"

    @property
    def base_confidence(self) -> float:
        return DEFAULT_CONFIDENCE["yfinance"]

    def supports(self, ticker: str) -> bool:
        try:
            info = yf.Ticker(ticker).info
            return bool(info.get("symbol"))
        except Exception:
            return False

    def fetch(self, ticker: str, asof: date) -> Optional[FundamentalsRecord]:
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
            if not info.get("symbol"):
                return None

            source_tag = f"yfinance:{asof.strftime('%Y-%m')}"
            conf = self.base_confidence

            # ROE 5y — yfinance exposes only trailing ROE; approximate all years same
            roe_val = info.get("returnOnEquity")
            if roe_val is not None:
                roe_dp = DataPoint(value=round(roe_val, 4), confidence=conf,
                                   source=source_tag, asof=asof)
                roe_5y = [roe_dp] * 5
            else:
                roe_5y = [DataPoint(value=None, confidence=0.0, source=source_tag, asof=asof)] * 5

            # EV/EBITDA
            ev_ebitda_val = info.get("enterpriseToEbitda")
            ev_ebitda = DataPoint(
                value=round(ev_ebitda_val, 4) if ev_ebitda_val is not None else None,
                confidence=conf, source=source_tag, asof=asof,
            ) if ev_ebitda_val is not None else None

            # Debt/Equity
            de_val = info.get("debtToEquity")
            if de_val is not None:
                de_val = de_val / 100.0  # yfinance returns as percentage
            debt_equity = DataPoint(
                value=round(de_val, 4) if de_val is not None else None,
                confidence=conf, source=source_tag, asof=asof,
            ) if de_val is not None else None

            # Net income 5y — yfinance gives trailing only; approximate all years same
            ni_val = info.get("netIncomeToCommon")
            ni_5y = [
                DataPoint(value=ni_val, confidence=conf, source=source_tag, asof=asof)
                if ni_val is not None else None
            ] * 5

            # Industry
            raw_sector = info.get("sector") or info.get("industry")
            industry = normalize_industry(raw_sector)

            # Market cap and ADV
            mkt_cap = info.get("marketCap")
            market_cap = DataPoint(value=mkt_cap, confidence=conf, source=source_tag, asof=asof) \
                if mkt_cap else None

            adv_val = info.get("averageDailyVolume10Day") or info.get("averageVolume10days")
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            adv_usd = (adv_val * price) if (adv_val and price) else None
            adv = DataPoint(value=adv_usd, confidence=conf, source=source_tag, asof=asof) \
                if adv_usd else None

            # ADR detection heuristic
            country = info.get("country", "")
            is_adr = country.upper() not in ("UNITED STATES", "US", "")

            return FundamentalsRecord(
                ticker=ticker,
                asof=asof,
                roe_5y=roe_5y,
                ev_ebitda=ev_ebitda,
                debt_equity=debt_equity,
                net_income_5y=ni_5y,
                industry=industry,
                market_cap=market_cap,
                adv=adv,
                is_adr=is_adr,
            )
        except Exception as e:
            log.warning("yfinance fetch failed for %s: %s", ticker, e)
            return None
