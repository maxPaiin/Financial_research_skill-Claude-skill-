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

## Formula (v0.3, amended by v0.32 G1)

```
consensus_raw       = log(1 + n_funds_holding)

# A3 — style-diversity weighting of consensus
diversity           = (n_distinct_holder_styles - 1) / (n_funds_holding - 1)   # [0,1]
style_factor        = STYLE_MIN_FACTOR + (1 - STYLE_MIN_FACTOR) * diversity     # [0.5,1]
consensus_weighted  = consensus_raw * style_factor        # 1.0 if styles unavailable

crowding_raw        = max(0, (avg_weight - AVG_WEIGHT_THRESHOLD) / WEIGHT_RANGE)
                      * (n_funds_holding / FUND_DENOMINATOR)

# A2 — exit-crowdedness (days-to-liquidate), only when AUM + ADV are present
# G1 (v0.32): the sum runs over USD-REPORTING funds only. ADV is always USD.
aggregate_position_usd = Σ_{funds with currency == "USD"} (fund_AUM × weight_in_fund)
days_to_liquidate      = aggregate_position_usd / ADV_usd
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
(per fund) or ADV (per ticker) is missing — **or the fund's AUM is not reported in USD**
(v0.32 G1, below) — the signal **falls back to the v0.2 pure-weight discount** and the
figure is labelled **NAV-only** (vs **liquidity-inclusive**); it never crashes on missing
inputs.

## G1 (v0.32) — the currency gate: exclude, never convert

`days_to_liquidate` divides an AUM-derived numerator by a USD denominator. ADV is always
USD; a fund's AUM is whatever the factsheet reports. Before v0.3 this did not matter — the
only AUM-dependent check compared a *weight sum* to a *fraction*, so the currency cancelled.
The days-to-liquidate metric removed that cancellation, and the failure mode is **silent**:
an HKD-reporting fund overstates days-to-liquidate by roughly 7.8×, with no error and no
flag. This matters disproportionately here because the target input is the **Hong Kong
distribution channel**, where HKD-denominated share classes are routine.

The gate is in `fund_aum_map()`:

- A fund's `total_aum` enters the map **only if `currency == "USD"`**.
- A non-USD or `null` currency means the fund is **omitted from the AUM map** — nothing
  else. It still contributes to `n_funds_holding`, to weights, and to style diversity. Its
  holdings are data; only its AUM is in unknown units.
- No new fallback logic was needed: A2 already drops a fund without usable AUM from the
  aggregate, and a ticker left with none falls back to **NAV-only**. G1 simply routes
  non-USD funds down that existing path.

**No FX conversion exists anywhere in this codebase, by design.** Converting would require
an FX source, a rate-date policy (the fund's `asof`? the run date?) and a new
provenance/confidence path — three new failure modes to repair a metric that already
degrades cleanly. Exclusion is consistent with safety-first and with A4's treatment of
low-confidence inputs. **Units are either identical or the input is set aside and labelled;
there is no third path**, and an unstated currency is never assumed to be USD.

Because the map is USD-only by construction, the name `aggregate_position_usd` is accurate
rather than aspirational. Do not widen the map without converting — and conversion is out
of scope.

## G2 (v0.32) — thin US exposure: warn, do not re-weight

The viability gate is binary: ≥5 US holdings **and** ≥20% US weight. A global fund with
exactly 5 US holdings at 21% of AUM passes fully, then votes in the consensus signal with
**the same weight** as a 95%-US fund — because `n_funds_holding` counts funds, not exposure.
This is the A3 false-consensus problem seen from the exposure angle instead of the style
angle.

Funds whose `scope_summary.weight_kept` falls in **20–35%** are flagged `thin_us_exposure`
at Stage 1b and reported in Layer 1, Layer 2 and Appendix 3. They are **not rejected and not
down-weighted**: down-weighting would alter `C`, whose definition is locked, and any change
to `C` belongs in a signal iteration rather than a defect patch. Warning surfaces the issue
without touching the score.

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
