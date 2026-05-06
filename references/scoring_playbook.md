# Scoring Playbook

Implementation reference for `scripts/compute_scores.py`. All formulas trace back to `Requirements_and_Analysis_Logic.md` §3-6, with the multi-stock adaptations decided in the spec-merge phase.

## Table of contents

1. [Inputs](#1-inputs)
2. [Industry score](#2-industry-score-0100)
3. [Growth score](#3-growth-score-0100)
4. [Quality & Value score](#4-quality--value-score-0100)
5. [Momentum (optional)](#5-momentum-optional)
6. [Total score (pre-strategy)](#6-total-score-pre-strategy)
7. [Worked example](#7-worked-example)

---

## 1. Inputs

Each stock record (from `market.json`) provides:

```python
{
  "ticker": "AAPL",
  "industry": "technology",
  "price": 195.20,
  "market_cap": 3.05e12,
  "pe": 28.4,
  "pbr": 45.1,
  "ev_ebitda": 21.3,
  "roe": 0.171,
  "eps_estimate_t": 7.21,
  "eps_estimate_t_minus_1": 6.84,
  "industry_etf_return_12m": 0.184,   # decimal
  "index_return_12m": 0.122,
  "past_6m_return": 0.087
}
```

Macro context (from `macro.json`):
```python
{
  "interest_rate_yoy_change": +0.005,    # +50 bps
  "inflation_yoy": 0.031,                # 3.1%
  "fx_regime": "weak_jpy" | "normal" | "strong_usd"
}
```

If any field is `null` / missing, the corresponding factor returns `None` and the composite uses available factors only (re-normalize the weights).

---

## 2. Industry score (0–100)

### 2.1 Macro tilt

```python
def macro_score(industry: str, inflation: float, rate_change: float, fx_regime: str) -> int:
    score = 0
    if industry in {"commodity", "trading", "materials", "energy"}:
        if inflation > 0.025:
            score += 1
    if industry in {"financial", "banks", "insurance"}:
        if rate_change > 0:
            score += 1
    if industry in {"export", "auto", "semiconductors_jp"}:
        if fx_regime == "weak_jpy":
            score += 1
    return score   # 0..3
```

### 2.2 Price verification

```python
relative_strength = industry_etf_return_12m - index_return_12m
trend = industry_etf_return_12m   # positive => up-trending
```

### 2.3 Composite

```python
def industry_score(macro: int, trend: float, relative_strength: float) -> int:
    score = 0
    score += macro * 20                     # 0, 20, 40, or 60
    if trend > 0:
        score += 30
    if relative_strength > 0:
        score += 50
    else:
        score += 10                         # weak but not zero
    return min(score, 100)
```

Output range: 10–100 (never 0; floor protects against dead-zero stocks dragging composites).

---

## 3. Growth score (0–100)

### 3.1 Value-percentile sub-score (lower PE/PBR within industry = higher score)

```python
def value_score(pe: float, industry_pe_distribution: list[float]) -> int:
    p = percentile(pe, industry_pe_distribution)   # 0..100
    return 100 - p                                 # cheaper => higher
```

`industry_pe_distribution` is the list of PE values across all stocks in the same industry within our universe (the unique stocks across the 7–11 funds). Computed once by `compute_scores.py` before the per-stock loop.

### 3.2 EPS revision sub-score (the alpha signal)

```python
def revision(eps_t: float, eps_t_minus_1: float) -> float:
    if eps_t_minus_1 == 0:
        return 0.0
    return (eps_t - eps_t_minus_1) / abs(eps_t_minus_1)

def revision_score(rev: float) -> int:
    if rev > 0.10:
        return 100
    elif rev > 0.05:
        return 85
    elif rev > 0:
        return 70
    elif rev > -0.05:
        return 40
    else:
        return 20
```

### 3.3 Composite

```python
growth_score = 0.5 * value_score + 0.5 * revision_score
```

---

## 4. Quality & Value score (0–100)

### 4.1 EV/EBITDA percentile (lower = better)

```python
def ev_score(ev_ebitda: float, industry_dist: list[float]) -> int:
    p = percentile(ev_ebitda, industry_dist)
    return 100 - p
```

### 4.2 ROE percentile (higher = better)

```python
def roe_score(roe: float, industry_dist: list[float]) -> int:
    return percentile(roe, industry_dist)
```

### 4.3 Composite

```python
quality_value_score = 0.5 * ev_score + 0.5 * roe_score
```

---

## 5. Momentum (optional)

```python
def momentum_score(past_6m_return: float, universe_dist: list[float]) -> int:
    return percentile(past_6m_return, universe_dist)
```

Universe-wide percentile (not industry-relative) because momentum is a cross-sectional factor.

Used only by the **Growth strategy** in `strategy_weights.py`. See `references/strategy_weights.md` §2.

---

## 6. Total score (pre-strategy)

The "neutral" total score (used in rankings before strategy weighting):

```python
total_score = (
    0.30 * industry_score
  + 0.30 * growth_score
  + 0.40 * quality_value_score
)
```

This is what `references/strategy_weights.md` calls the **Conservative**-leaning baseline. The three strategy-specific weights replace this in Stage 4.

---

## 7. Worked example

Stock: AAPL (technology), in a hypothetical universe.

| Input | Value |
|---|---|
| industry | technology |
| pe | 28.4 |
| ev_ebitda | 21.3 |
| roe | 0.171 |
| eps_estimate_t | 7.21 |
| eps_estimate_t_minus_1 | 6.84 |
| industry_etf_return_12m | 0.184 |
| index_return_12m | 0.122 |
| past_6m_return | 0.087 |
| inflation | 0.031 |
| rate_change | +0.005 |
| fx_regime | normal |

Industry PE distribution (tech sector in universe): pretend 20th percentile = 18, 50th = 26, 80th = 35.
AAPL's PE 28.4 is at ~58th percentile → `value_score = 100 - 58 = 42`.

EV/EBITDA distribution: AAPL's 21.3 at ~70th → `ev_score = 30`.
ROE distribution: AAPL's 0.171 at ~75th → `roe_score = 75`.

```
macro             = 0  (tech doesn't match commodity/financial/export buckets)
trend             = +30  (industry ETF return positive)
rel_strength      = 0.184 - 0.122 = +0.062 → +50
industry_score    = 0 + 30 + 50 = 80

revision          = (7.21 - 6.84) / 6.84 = 0.054 → revision_score = 85
growth_score      = 0.5 * 42 + 0.5 * 85 = 63.5

quality_value     = 0.5 * 30 + 0.5 * 75 = 52.5

total (neutral)   = 0.3 * 80 + 0.3 * 63.5 + 0.4 * 52.5 = 24 + 19.05 + 21 = 64.05
```

The strategy-specific scores will redistribute these weights — see `strategy_weights.md`.