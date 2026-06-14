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

## Formula (v0.3)

```
consensus_raw       = log(1 + n_funds_holding)

# A3 — style-diversity weighting of consensus
diversity           = (n_distinct_holder_styles - 1) / (n_funds_holding - 1)   # [0,1]
style_factor        = STYLE_MIN_FACTOR + (1 - STYLE_MIN_FACTOR) * diversity     # [0.5,1]
consensus_weighted  = consensus_raw * style_factor        # 1.0 if styles unavailable

crowding_raw        = max(0, (avg_weight - AVG_WEIGHT_THRESHOLD) / WEIGHT_RANGE)
                      * (n_funds_holding / FUND_DENOMINATOR)

# A2 — exit-crowdedness (days-to-liquidate), only when AUM + ADV are present
aggregate_position_$ = Σ_funds (fund_AUM × weight_in_fund)
days_to_liquidate    = aggregate_position_$ / ADV_usd
liq                  = clamp(days_to_liquidate / DTL_FULL, 0, 1)
crowding_raw'        = crowding_raw * (1 + LIQ_WEIGHT * liq)   # else crowding_raw (NAV-only)

crowding_discount    = min(crowding_raw', MAX_DISCOUNT)
signal               = consensus_weighted * (1 - crowding_discount)
```

Constants (canonical in `crowding_signal.py`):
- `AVG_WEIGHT_THRESHOLD = 0.02` — below this, no crowding discount applies
- `WEIGHT_RANGE = 0.08` — range over which discount increases from 0 to full
- `FUND_DENOMINATOR = 5.0` — 5+ funds at moderate weight starts to suggest crowding
- `MAX_DISCOUNT = 0.60` — discount capped at 60%
- `DTL_FULL = 10.0` — days-to-liquidate at which the illiquidity amplifier saturates
- `LIQ_WEIGHT = 0.50` — max fractional uplift to crowding from full illiquidity
- `STYLE_MIN_FACTOR = 0.50` — consensus weight retained by a fully style-homogeneous holder set
- `HOMOGENEITY_THRESHOLD = 0.80` — dominant input-style share that triggers the homogeneity warning

## A2 — exit-crowdedness (days-to-liquidate)

The reflexive "everyone exits the same door" risk is position size *relative to exit
liquidity*, not relative to NAV. ADV is the door width. The formula deliberately assumes
**simultaneous exit by all holders** — the tail-risk framing the tool surfaces. When AUM
(per fund) or ADV (per ticker) is missing, the signal **falls back to the v0.2 pure-weight
discount** and the figure is labelled **NAV-only** (vs **liquidity-inclusive**); it never
crashes on missing inputs.

## A3 — style-diversity-weighted consensus + homogeneity warning

"AAPL held by 9/9 tech funds" carries ~zero information — the consensus is measuring the
input bias. Weighting consensus by holder style-diversity pushes within-style agreement down
and cross-style agreement up. **Stratified sampling is abandoned** (sample too small to
stratify at 7–11 funds; token budget). At the run level, if the input set is style-homogeneous
(dominant style share ≥ `HOMOGENEITY_THRESHOLD`), a prominent warning fires — its payload is
Appendix 3. The style label per fund is inferred at Stage 1a (`_KNOWN_STYLES`).

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
