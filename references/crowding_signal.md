# Crowding Signal Reference

This file explains the consensus-with-crowding-discount signal.
It is a reader — no executable rules. The canonical formula and constants are in
`scripts/crowding_signal.py`.

---

## What the signal is

A single number that captures:
- How widely held a stock is across the fund universe (**consensus**)
- Discounted for the risk that high consensus at large positions represents HK-channel
  crowding (**crowding discount**)

Two separate signals would imply independence that does not exist — consensus and crowding
are highly correlated. One combined signal is more honest (§6 D6 decision).

## Formula

```
consensus_raw      = log(1 + n_funds_holding)

crowding_raw       = max(0, (avg_weight - AVG_WEIGHT_THRESHOLD) / WEIGHT_RANGE)
                     * (n_funds_holding / FUND_DENOMINATOR)

crowding_discount  = min(crowding_raw, MAX_DISCOUNT)

signal             = consensus_raw * (1 - crowding_discount)
```

Constants (canonical in `crowding_signal.py`):
- `AVG_WEIGHT_THRESHOLD = 0.02` — below this, no crowding discount applies
- `WEIGHT_RANGE = 0.08` — range over which discount increases from 0 to full
- `FUND_DENOMINATOR = 5.0` — 5+ funds at moderate weight starts to suggest crowding
- `MAX_DISCOUNT = 0.60` — discount capped at 60%

## Interpretation

- A stock held by 10 funds at 0.5% average weight scores high consensus, near-zero discount.
- A stock held by 8 funds at 9% average weight scores high consensus, near-maximum discount.
- The crowding flag (`is_high_crowding`) is set when `crowding_discount >= 0.30`.
  Cards for high-crowding stocks display a visible warning to the user.

## Why this form

- `log(1 + n)` compresses the consensus signal: going from 1 to 3 funds matters more than
  going from 9 to 11.
- The crowding discount is heuristic, not derived from statistical estimation. The tuning
  constants are starting defaults; they may be calibrated as more fund data becomes available.
- This signal is normalized to 0–100 before combining with the fundamental quality score.
  Normalization is per-run (min/max of the passed universe), not an absolute scale.
