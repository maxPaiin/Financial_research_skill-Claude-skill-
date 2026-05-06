# Backtest Methodology

Implementation reference for `scripts/backtest.py`. Translates Requirements §7-11 into precise, reproducible rules.

## Table of contents
1. [Universe & data assumptions](#1-universe--data-assumptions)
2. [Rebalancing rules](#2-rebalancing-rules)
3. [Risk control rules](#3-risk-control-rules)
4. [Output metrics](#4-output-metrics)
5. [Token-cost tradeoffs](#5-token-cost-tradeoffs)
6. [Known limitations](#6-known-limitations)

---

## 1. Universe & data assumptions

- **Universe**: every unique stock held by any of the 7–11 input funds. Computed in Stage 1.
- **Lookback**: 1y, 3y, 5y from `today`. If a stock has < 3y price history, it's included only in the 1y window.
- **Pricing data**: yfinance daily adjusted close, resampled to month-end.
- **Point-in-time fundamentals**: yfinance does NOT give clean point-in-time PE/ROE history. The backtest uses **current** fundamentals as a proxy for the entire window. This is a known bias (lookahead bias on fundamentals). Output flags this in the methodology section of the PDF.
- **Survivorship**: yfinance is survivorship-biased (delisted tickers may be missing). Output notes this.

For users who need rigorous backtesting, recommend a paid data source (FactSet, Compustat) — out of scope for this skill.

---

## 2. Rebalancing rules

```python
rebalance_frequency = "monthly"     # last business day of each month
selection_pct = 0.20                # top 20% by strategy score
weighting = "equal"
turnover_threshold = None           # rebalance every period regardless
```

Each month-end:

1. Score every stock in universe using the strategy's formula (with current fundamentals — see §1 caveat).
2. Rank, select top 20% (round up; minimum 5 stocks).
3. Equal-weight across selected stocks.
4. Apply industry cap (see §3).
5. Compute next month's return as the weighted average of constituent monthly returns.

### 2.1 Sell condition (separate from rebalance)

```python
# Mid-month stop loss check (daily)
if any_stock_mtd_return < -0.10:
    sell_that_stock_to_cash    # excess weight redistributed equally to others at next month-end
```

Per Requirements §9, this is daily-monitored. In practice the backtest checks at month-end resolution because monthly is what we have for fundamentals. We document this as an approximation.

### 2.2 Sell condition (rank-based)

```python
# At rebalance time
if held_stock not in current_top_30_pct:
    sell    # buffer between top-20% (buy) and top-30% (hold) reduces turnover
```

The 20% buy / 30% hold buffer is a standard turnover-reduction technique not literally in Requirements §8 but inferred — Requirements only said `if not in top_30%: sell` which works as written.

---

## 3. Risk control rules

### 3.1 Stop loss

Per stock, mid-period (see §2.1).

### 3.2 Industry cap

```python
max_industry_weight = 0.30
```

If after equal-weighting, any industry's total weight exceeds 30%, redistribute the excess proportionally to under-weighted industries' constituents. If no other industry can absorb it, the excess goes to cash for that period.

### 3.3 Cash treatment

Cash earns the period's risk-free rate (3-month T-bill from FRED, or 0 if FRED unavailable).

---

## 4. Output metrics

For each (strategy, period) cell:

| Metric | Definition |
|---|---|
| **CAGR** | `(final_nav / initial_nav) ** (1/years) - 1` |
| **Sharpe Ratio** | `mean(excess_monthly_return) / stdev(excess_monthly_return) * sqrt(12)`, where excess = return - rf |
| **Max Drawdown** | Largest peak-to-trough decline in NAV across the window |
| **Win Rate** | Fraction of months with positive return |
| **Volatility** | `stdev(monthly_return) * sqrt(12)` (annualized) |
| **Turnover** | Average monthly fraction of portfolio replaced |

Stored as:
```json
{
  "strategy": "growth",
  "period": "3y",
  "cagr": 0.142,
  "sharpe": 0.83,
  "max_drawdown": -0.247,
  "win_rate": 0.611,
  "volatility": 0.198,
  "avg_turnover": 0.34,
  "equity_curve": [{"date": "2022-05", "nav": 1.000}, ...],
  "n_stocks_universe": 187,
  "data_quality_flags": ["lookahead_fundamentals", "survivorship_bias"]
}
```

The PDF report renders the equity curves as a chart per strategy (3 lines, one for each).

---

## 5. Token-cost tradeoffs

This stage is the most expensive in the pipeline. Per the user's spec decision, full backtesting is retained. Mitigations:

- **Cache aggressively**: yfinance responses cached to `/home/claude/work/cache/` keyed by `ticker__YYYYMM`. Re-running within a day is free.
- **Batch tickers**: yfinance `download(["AAPL", "MSFT", ...])` accepts up to ~50 tickers per call. Script batches.
- **Skip optional momentum** if the universe exceeds 250 stocks, to keep wall-clock under 15 minutes.
- **Single-period mode**: if `--periods 1y` only, runtime drops ~5×.

If the user is rate-limited or the run hits the budget cap (see SKILL.md error recovery):
- Reduce universe to top 100 stocks by aggregate fund weight.
- Skip the 5y window.
- Drop to lookback only on representative ETFs as a sanity check.
Flag all such reductions in the PDF.

---

## 6. Known limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Current fundamentals used throughout window | Optimistic bias for value/growth-tilted strategies | Disclosed in report |
| Survivorship bias | Optimistic bias on returns | Disclosed in report |
| No transaction costs / slippage | Optimistic bias on net returns | Subtract 0.10% per rebalance from NAV (configurable in script) |
| No taxes / fees | Optimistic bias | Disclosed |
| Stop-loss at month-end resolution | Real-world stop-loss would trigger earlier | Disclosed |
| FX not modeled for cross-market holdings | Unhedged FX swings missing | If a portfolio has > 30% non-base-currency holdings, flag in report |

The PDF's "Methodology Notes" section reproduces this table verbatim. Users must read it before trusting any number.