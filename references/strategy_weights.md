# Strategy Weights

Implementation reference for `scripts/strategy_weights.py`. Defines how the three strategies in Structure §2.8 map to different weight combinations of the four sub-scores from `scoring_playbook.md`.

## 1. Why three different weight schemes

Requirements §6 originally proposed a single composite (`0.3 industry + 0.3 growth + 0.4 quality_value`). With three strategies, we need three. The design principle:

- **Growth-seeking investors** weight forward-looking signals (growth, revision, momentum) higher and tolerate richer valuations.
- **Conservative investors** weight fundamentals (ROE, EV/EBITDA) higher and want a cheap-but-strong tilt.
- **Risk-averse investors** weight industry diversification (via concentration penalty) and high-quality balance sheets, accepting lower expected return for lower drawdowns.

## 2. The three weight schemes

| Sub-score | Growth | Conservative | Risk-avoidance |
|---|---:|---:|---:|
| industry_score | 0.20 | 0.30 | 0.40 |
| growth_score | 0.60 | 0.20 | 0.10 |
| quality_value_score | 0.20 | 0.50 | 0.50 |
| **+ momentum_score** | +0.10 (additive)* | 0 | 0 |
| **− industry concentration penalty** | 0 | 0 | up to −20 |

*Growth strategy's composite can therefore exceed 100 — that's intentional, used as a relative-ranking signal, not a literal probability.

### 2.1 Growth strategy formula

```python
def growth_strategy_score(stock):
    base = (
        0.20 * stock.industry_score
      + 0.60 * stock.growth_score
      + 0.20 * stock.quality_value_score
    )
    if stock.momentum_score is not None:
        base += 0.10 * stock.momentum_score
    return base   # range roughly 0..110
```

### 2.2 Conservative strategy formula

```python
def conservative_strategy_score(stock):
    return (
        0.30 * stock.industry_score
      + 0.20 * stock.growth_score
      + 0.50 * stock.quality_value_score
    )
```

### 2.3 Risk-avoidance strategy formula

```python
def risk_avoidance_strategy_score(stock, fund_industry_concentration):
    """
    fund_industry_concentration: float in [0, 1] — the highest single-industry
    weight in any fund holding this stock. Computed by aggregate_funds.py.
    """
    base = (
        0.40 * stock.industry_score
      + 0.10 * stock.growth_score
      + 0.50 * stock.quality_value_score
    )
    # Penalty: if the stock contributes to a fund whose top industry > 30%,
    # subtract proportionally up to 20 points.
    if fund_industry_concentration > 0.30:
        excess = fund_industry_concentration - 0.30
        penalty = min(excess * 100, 20)   # 1% excess => 1 point penalty, capped at 20
        base -= penalty
    return max(base, 0)
```

## 3. Why these specific numbers

| Decision | Rationale |
|---|---|
| Growth gets 0.60 on growth_score | EPS revision is the strongest near-term alpha factor in cross-sectional studies; this is where Growth must overweight |
| Growth still gets 0.20 on quality_value | Pure-momentum without quality screen blew up in 2000 and 2022; minimum floor |
| Conservative caps growth at 0.20 | We don't want Conservative to go pure deep-value — some forward earnings strength is required |
| Risk-avoidance takes industry to 0.40 | This is the strategy where regime-risk matters most; macro/industry score overweighted |
| Risk-avoidance keeps quality at 0.50 | Strong balance sheets correlate with smaller drawdowns |
| The concentration penalty caps at -20 | Even a 50% single-industry fund shouldn't be auto-rejected — but it should be heavily penalized |

## 4. Calibration notes

These weights are starting defaults. In production they'd be calibrated via the backtest results (see `backtest_methodology.md` §6, "Weight calibration"). For this skill's first version, treat them as fixed.

If a future user asks "what if I want a more aggressive Growth strategy", point them to:
- Increase `growth_score` weight to 0.70
- Reduce `quality_value_score` to 0.10
- Increase momentum bonus to 0.20

But warn: deviating from the defaults invalidates the backtest results unless they're rerun with the new weights.

## 5. Output schema

`compute_scores.py` writes per-stock scores; `strategy_weights.py` adds three new fields per stock:

```json
{
  "ticker": "AAPL",
  "industry_score": 80,
  "growth_score": 63.5,
  "quality_value_score": 52.5,
  "momentum_score": 67,
  "strategy_scores": {
    "growth":          0.20*80 + 0.60*63.5 + 0.20*52.5 + 0.10*67  =  71.8,
    "conservative":    0.30*80 + 0.20*63.5 + 0.50*52.5            =  62.95,
    "risk_avoidance":  0.40*80 + 0.10*63.5 + 0.50*52.5            =  64.6
  }
}
```

(The arithmetic above is for illustration; the actual values will round.)