"""
Stage 2f: Consensus-with-crowding-discount signal.

Produces a single signal that combines how widely held a stock is (consensus)
with a discount for HK-channel crowding. Two separate signals would imply
independence that does not exist (§6 D6 decision).

Formula and tuning constants are the canonical location per §5.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

# Canonical tuning constants — do not duplicate elsewhere.
# Tuning notes: starting defaults, may be calibrated later.
_AVG_WEIGHT_THRESHOLD = 0.02    # below this, no crowding discount applies
_WEIGHT_RANGE = 0.08            # range to full discount: at avg_weight = 10%, full discount
_FUND_DENOMINATOR = 5.0         # 5+ funds at moderate weight starts to suggest crowding
_MAX_DISCOUNT = 0.60            # cap crowding discount at 60%


@dataclass
class CrowdingResult:
    ticker: str
    consensus_raw: float
    crowding_discount: float
    signal: float               # consensus_raw * (1 - crowding_discount)
    is_high_crowding: bool      # True when crowding_discount >= 0.30


def compute(
    ticker: str,
    n_funds_holding: int,
    avg_weight: float,
) -> CrowdingResult:
    """
    Compute the consensus-with-crowding-discount signal for one ticker.

    Args:
        ticker: stock ticker
        n_funds_holding: number of funds in the universe holding this ticker
        avg_weight: mean weight across funds where the ticker is held (as decimal, e.g. 0.05)
    """
    consensus_raw = math.log(1 + n_funds_holding)

    crowding_raw = (
        max(0.0, (avg_weight - _AVG_WEIGHT_THRESHOLD) / _WEIGHT_RANGE)
        * (n_funds_holding / _FUND_DENOMINATOR)
    )
    crowding_discount = min(crowding_raw, _MAX_DISCOUNT)

    signal = consensus_raw * (1 - crowding_discount)

    return CrowdingResult(
        ticker=ticker,
        consensus_raw=round(consensus_raw, 4),
        crowding_discount=round(crowding_discount, 4),
        signal=round(signal, 4),
        is_high_crowding=crowding_discount >= 0.30,
    )
