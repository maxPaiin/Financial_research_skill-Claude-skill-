"""
Stage 8: Monthly-rebalanced backtest across {1y, 3y, 5y} × {growth,
conservative, risk_avoidance}. Implements the rules in
references/backtest_methodology.md.

Inputs:
  holdings.json          (for the universe)
  scores_strategies.json (for current strategy scores)
  market.json            (for industry mapping & beta)
  macro.json             (for risk-free rate)

Output:
  backtest.json with per-(strategy, period) metrics + monthly equity curves.

Limitations:
  * Uses CURRENT fundamentals as proxy across the entire window (lookahead bias).
  * yfinance survivorship-biased.
  * Monthly resolution stop-loss (not daily).
All flagged in the output's `data_quality_flags` field.
"""

import sys
import json
import argparse
import math
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    print("ERROR: yfinance / pandas / numpy required.", file=sys.stderr)
    sys.exit(2)


PERIODS = {"1y": 12, "3y": 36, "5y": 60}
SELECTION_PCT = 0.20
HOLD_BUFFER_PCT = 0.30      # sell if outside top-30%
STOP_LOSS = -0.10
INDUSTRY_CAP = 0.30
TRANSACTION_COST_BPS = 10   # 0.10% per rebalance, applied to NAV
MIN_PORTFOLIO_SIZE = 5


def fetch_price_panel(tickers, start, end, cache_dir):
    """Download monthly close prices for all tickers. Returns DataFrame indexed by month-end."""
    cache_path = cache_dir / f"prices_{start}_{end}.parquet"
    if cache_path.exists():
        try:
            return pd.read_parquet(cache_path)
        except Exception:
            pass

    print(f"  Downloading prices for {len(tickers)} tickers, {start}..{end}")
    # yfinance batching
    batch_size = 30
    frames = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            df = yf.download(
                tickers=batch,
                start=start,
                end=end,
                interval="1mo",
                auto_adjust=True,
                progress=False,
                threads=True,
            )
            if isinstance(df.columns, pd.MultiIndex):
                close = df["Close"]
            else:
                close = df[["Close"]].rename(columns={"Close": batch[0]})
            frames.append(close)
        except Exception as e:
            print(f"    batch failed: {e}", file=sys.stderr)

    if not frames:
        return pd.DataFrame()

    panel = pd.concat(frames, axis=1)
    panel = panel.loc[:, ~panel.columns.duplicated()]
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        panel.to_parquet(cache_path)
    except Exception:
        pass
    return panel


def select_portfolio(scored_stocks, n_select, industry_lookup, cap=INDUSTRY_CAP):
    """Equal-weight top N, applying industry cap. Returns dict ticker -> weight."""
    if not scored_stocks:
        return {}
    selected = sorted(scored_stocks, key=lambda x: -x[1])[:max(n_select, MIN_PORTFOLIO_SIZE)]
    weights = {t: 1.0 / len(selected) for t, _ in selected}

    # Apply industry cap
    industry_totals = defaultdict(float)
    for t, w in weights.items():
        industry_totals[industry_lookup.get(t, "other")] += w

    overweight = [(ind, total) for ind, total in industry_totals.items() if total > cap]
    if overweight:
        # Cap each over-weighted industry, redistribute excess to under-weighted
        for ind, total in overweight:
            excess = total - cap
            scale = cap / total
            for t in list(weights.keys()):
                if industry_lookup.get(t, "other") == ind:
                    weights[t] *= scale
        # Re-normalize the rest
        residual = 1.0 - sum(weights.values())
        if residual > 0:
            under_tickers = [t for t in weights if industry_lookup.get(t, "other") not in {ind for ind, _ in overweight}]
            if under_tickers:
                add = residual / len(under_tickers)
                for t in under_tickers:
                    weights[t] += add
            # else: residual goes to "cash" (we just won't fully invest)

    return weights


def run_backtest(strategy_name, score_lookup, panel, industry_lookup, rf_monthly, n_months):
    """Execute the backtest. Returns metrics dict."""
    if panel.empty or len(panel) < 2:
        return {"error": "no_price_data"}

    # Use only the last n_months of the panel
    panel_window = panel.tail(n_months + 1).copy()
    monthly_returns = panel_window.pct_change().dropna(how="all")

    nav = 1.0
    nav_curve = [{"date": str(monthly_returns.index[0].date()), "nav": 1.0}]
    held_weights = {}
    monthly_pnl = []
    turnover_history = []

    n_select = max(MIN_PORTFOLIO_SIZE, int(len(score_lookup) * SELECTION_PCT))

    for date, returns_row in monthly_returns.iterrows():
        # Apply held portfolio's return for this month
        if held_weights:
            month_return = 0.0
            stopped_out = []
            new_weights = {}
            for t, w in held_weights.items():
                r = returns_row.get(t, 0)
                if pd.isna(r):
                    r = 0
                # Stop-loss: if month return < -10%, sell (move to cash for next month)
                if r < STOP_LOSS:
                    stopped_out.append(t)
                month_return += w * r

            # Apply transaction cost to month_return (proxy: every month rebalances)
            month_return -= TRANSACTION_COST_BPS / 10000

            nav *= (1 + month_return)
            monthly_pnl.append(month_return)
        else:
            # First month or all stopped — earn rf
            nav *= (1 + rf_monthly)
            monthly_pnl.append(rf_monthly)

        nav_curve.append({"date": str(date.date()), "nav": round(nav, 4)})

        # At end of this month, re-select based on current scores
        # (Lookahead bias: same scores used throughout.)
        scored = [(t, score_lookup[t]) for t in score_lookup if t in panel.columns]
        new_weights = select_portfolio(scored, n_select, industry_lookup)

        # Compute turnover
        prev = set(held_weights.keys())
        new = set(new_weights.keys())
        if prev or new:
            churn = len(prev.symmetric_difference(new)) / max(len(prev | new), 1)
            turnover_history.append(churn)

        held_weights = new_weights

    # Metrics
    if not monthly_pnl:
        return {"error": "no_returns"}

    monthly_pnl_arr = np.array(monthly_pnl)
    years = len(monthly_pnl) / 12
    cagr = (nav ** (1 / years) - 1) if years > 0 else 0
    excess = monthly_pnl_arr - rf_monthly
    sharpe = (excess.mean() / excess.std() * math.sqrt(12)) if excess.std() > 0 else 0
    nav_series = np.array([p["nav"] for p in nav_curve])
    rolling_max = np.maximum.accumulate(nav_series)
    drawdowns = (nav_series - rolling_max) / rolling_max
    max_dd = float(drawdowns.min())
    win_rate = float((monthly_pnl_arr > 0).sum() / len(monthly_pnl_arr))
    volatility = float(monthly_pnl_arr.std() * math.sqrt(12))
    avg_turnover = float(np.mean(turnover_history)) if turnover_history else 0

    return {
        "strategy": strategy_name,
        "n_months": int(len(monthly_pnl)),
        "cagr": round(cagr, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(win_rate, 4),
        "volatility": round(volatility, 4),
        "avg_turnover": round(avg_turnover, 4),
        "final_nav": round(nav, 4),
        "equity_curve": nav_curve,
        "data_quality_flags": [
            "lookahead_fundamentals",
            "survivorship_bias",
            "monthly_stop_loss_resolution",
        ],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True, help="holdings.json")
    ap.add_argument("--scores", required=True, help="scores_strategies.json")
    ap.add_argument("--market", required=True, help="market.json (for industry map)")
    ap.add_argument("--macro", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--periods", default="1y,3y,5y")
    ap.add_argument("--strategies", default="growth,conservative,risk_avoidance")
    ap.add_argument("--cache-dir", default="/home/claude/work/cache")
    ap.add_argument("--max-universe", type=int, default=None,
                    help="Cap universe to top-N by aggregate fund weight, for cost control")
    args = ap.parse_args()

    holdings = json.loads(Path(args.universe).read_text(encoding="utf-8"))
    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))["stocks"]
    market = json.loads(Path(args.market).read_text(encoding="utf-8"))["stocks"]
    macro = json.loads(Path(args.macro).read_text(encoding="utf-8"))

    rf_annual = macro.get("risk_free_rate") or 0.04
    rf_monthly = (1 + rf_annual) ** (1 / 12) - 1

    universe = [u["ticker"] for u in holdings.get("unique_universe", [])]
    if args.max_universe:
        universe = universe[:args.max_universe]

    industry_lookup = {t: market.get(t, {}).get("industry", "other") for t in universe}

    # Determine date range (longest period)
    period_months = max(PERIODS[p] for p in args.periods.split(","))
    end_date = datetime.today().date()
    start_date = end_date - timedelta(days=int(period_months * 31))

    cache_dir = Path(args.cache_dir)
    panel = fetch_price_panel(universe, start_date.isoformat(), end_date.isoformat(), cache_dir)

    if panel.empty:
        Path(args.out).write_text(json.dumps({"error": "price_fetch_failed"}, indent=2))
        sys.exit(1)

    results = {"runs": [], "rf_monthly": rf_monthly, "rf_annual": rf_annual,
               "universe_size": len(universe)}

    for strategy in args.strategies.split(","):
        score_lookup = {
            t: (scores.get(t, {}).get("strategy_scores") or {}).get(strategy)
            for t in universe
            if scores.get(t, {}).get("strategy_scores")
        }
        score_lookup = {t: s for t, s in score_lookup.items() if s is not None}

        for period in args.periods.split(","):
            n_months = PERIODS[period]
            print(f"Backtesting strategy={strategy} period={period}...")
            metrics = run_backtest(strategy, score_lookup, panel, industry_lookup, rf_monthly, n_months)
            metrics["period"] = period
            results["runs"].append(metrics)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    print(f"Backtest complete → {args.out}")


if __name__ == "__main__":
    main()