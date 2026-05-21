"""
Base types and ABCs for the provider layer.

DataPoint is the canonical unit of data returned by every provider.
All confidence values are in [0.0, 1.0].
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

# Default confidence baselines per source — canonical location per §5.3.
DEFAULT_CONFIDENCE: dict[str, float] = {
    "edgar": 0.9,       # True point-in-time SEC filing
    "yfinance": 0.5,    # Degraded PIT; current values projected back
}


@dataclass(frozen=True)
class DataPoint:
    """Single data value with provenance metadata."""
    value: Optional[float]
    confidence: float               # 0.0–1.0
    source: str                     # e.g. "edgar:10-K-2024", "yfinance:2025-05"
    asof: date
    n_sources_agreed: int = 1


@dataclass
class FundamentalsRecord:
    """Aggregated fundamentals for one ticker at a given asof date.

    `asof` is the *request* date (when the data was fetched).
    `data_asof` is the *data* date — the latest filing period-end (EDGAR) or
    the snapshot date (yfinance). The two diverge: a request on 2025-05-21
    against EDGAR returns 10-K data whose period ended 2024-12-31. Reports
    show `data_asof` to disclose actual fundamental-data freshness per stock.
    """
    ticker: str
    asof: date
    roe_5y: list[Optional[DataPoint]] = field(default_factory=list)   # annual, oldest→newest
    ev_ebitda: Optional[DataPoint] = None
    debt_equity: Optional[DataPoint] = None
    net_income_5y: list[Optional[DataPoint]] = field(default_factory=list)
    industry: Optional[str] = None
    market_cap: Optional[DataPoint] = None
    adv: Optional[DataPoint] = None                                   # avg daily volume USD
    is_adr: bool = False
    data_asof: Optional[date] = None                                  # M4 Level 2


class FundamentalsProvider(ABC):
    """Abstract base for all fundamental data providers."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def base_confidence(self) -> float: ...

    @abstractmethod
    def fetch(self, ticker: str, asof: date) -> Optional[FundamentalsRecord]:
        """Return a FundamentalsRecord or None if this provider cannot serve the ticker."""
        ...

    @abstractmethod
    def supports(self, ticker: str) -> bool:
        """Quick pre-check before a full fetch attempt."""
        ...
