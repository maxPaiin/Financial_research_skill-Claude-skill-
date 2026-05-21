"""
Stage 2f: Consensus-with-crowding-discount signal.

Produces a single signal that combines how widely held a stock is (consensus)
with a discount for HK-channel crowding. Two separate signals would imply
independence that does not exist (§6 D6 decision).

Formula and tuning constants are the canonical location per §5.3.

Inputs:
  --overlap   overlap.json (produced by overlap_analysis.py)
  --out       crowding_signals.json

Output schema — crowding_signals.json:
{
  "n_signals": 100,
  "signals": [
    {"ticker": "AAPL",
     "consensus_raw": 1.95,
     "crowding_discount": 0.12,
     "signal": 1.72,
     "is_high_crowding": false},
    ...
  ]
}
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlap", required=True, help="overlap.json from overlap_analysis.py")
    ap.add_argument("--out", required=True, help="Output crowding_signals.json path")
    args = ap.parse_args()

    overlap = json.loads(Path(args.overlap).read_text(encoding="utf-8"))
    rows = overlap.get("overlap", [])

    signals: list[dict] = []
    for r in rows:
        ticker = r.get("ticker")
        if not ticker:
            continue
        result = compute(
            ticker=ticker,
            n_funds_holding=int(r.get("n_funds_holding", 0)),
            avg_weight=float(r.get("avg_weight", 0.0)),
        )
        signals.append({
            "ticker": result.ticker,
            "consensus_raw": result.consensus_raw,
            "crowding_discount": result.crowding_discount,
            "signal": result.signal,
            "is_high_crowding": result.is_high_crowding,
        })

    out = {"n_signals": len(signals), "signals": signals}
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Crowding signals: {len(signals)} -> {out_path}")


if __name__ == "__main__":
    main()
