# Bayesian Trading Strategy - Enhancement Report

**Date:** December 30, 2025
**Implementation:** Steps 1-2 from improvements.md
**Timeframe:** 15-minute bars

---

## Executive Summary

This report analyzes the impact of implementing feature engineering (Step 1) and regime detection (Step 2) on the Bayesian regression trading strategy. The enhancements aimed to improve signal quality by filtering trades during low-volatility periods.

**Key Finding:** Regime detection reduces trade count but does not significantly improve signal quality. The fundamental issue remains: **the edge per trade (~$0.60) is too small to overcome transaction costs (~$4-5 per trade)**.

---

## Methodology

### Step 1: Feature Engineering

Added the following features to the trading logic:

| Feature | Formula | Purpose |
|---------|---------|---------|
| `volatility_20` | 20-bar rolling std of returns | Current volatility |
| `volatility_60` | 60-bar rolling std of returns | Baseline volatility |
| `vol_regime` | volatility_20 / volatility_60 | Volatility regime ratio |
| `trend` | (SMA20 - SMA60) / close | Normalized trend strength |
| `volume_ratio` | volume / 20-bar volume SMA | Volume confirmation |

### Step 2: Regime Detection

Applied a volatility regime filter:
- **Rule:** Only allow new trades when `vol_regime >= 0.8`
- **Rationale:** Low-volatility periods have poor signal-to-noise ratio

---

## Results Comparison

### Test Period Statistics
- **Duration:** 310 days (Feb 9 - Dec 16, 2025)
- **Data:** ETHUSDT 15-minute bars
- **Train/Test Split:** 66.7% / 33.3%

### Performance Comparison

| Metric | Baseline | Enhanced | Change |
|--------|----------|----------|--------|
| **Completed Trades** | 4,302 | 3,458 | -19.6% |
| **Gross P&L** | $2,454.99 | $2,134.15 | -13.1% |
| **Win Rate** | 36.0% | 36.3% | +0.3% |
| **Avg Profit/Trade** | $0.57 | $0.62 | +8.8% |
| **Max Drawdown** | $2,054.99 | $1,926.84 | -6.2% |
| **Sharpe Ratio** | 0.02 | 0.02 | 0% |
| **Signals Filtered** | 0 | 8,690 | - |
| **Filter Rate** | 0% | 71.5% | - |

### Feature Statistics (Full Dataset)
| Feature | Mean | Std |
|---------|------|-----|
| vol_regime | 0.965 | 0.283 |
| trend | -0.000019 | 0.010 |
| volume_ratio | 1.044 | 0.983 |

**Trading Regime Coverage:** 69.9% of bars qualify (vol_regime >= 0.8)

---

## Analysis

### What Worked

1. **Trade Reduction:** Regime detection successfully reduced trades by ~20%
2. **Improved Per-Trade Edge:** Average profit per trade increased from $0.57 to $0.62 (+8.8%)
3. **Lower Drawdown:** Max drawdown reduced by 6.2%

### What Didn't Work

1. **Total Profit Decrease:** Despite filtering 71.5% of signals, gross profit decreased by 13.1%
2. **Win Rate Unchanged:** Win rate remained essentially flat at ~36%
3. **Sharpe Ratio Unchanged:** Risk-adjusted returns did not improve

### Root Cause Analysis

The regime detection filters signals but **doesn't improve signal quality**. The issue is that:

1. **Low-volatility periods aren't the problem.** The vol_regime filter assumes low-vol = bad signals, but the data shows only 30% of bars are in low-vol regime.

2. **The model's predictions are uniformly weak.** Whether in high or low volatility, the Bayesian model produces similar signal quality.

3. **Filtering reduces opportunity without improving hit rate.** We're trading less but not trading better.

---

## Profit Factor Analysis

| Metric | Baseline | Enhanced |
|--------|----------|----------|
| Avg Winning Trade | $26.99 | $29.54 |
| Avg Losing Trade | -$14.27 | -$15.86 |
| Profit Factor | 1.89x | 1.86x |

The profit factor (avg win / avg loss) remains ~1.9x in both cases. This is positive but insufficient:

- **Break-even requirement with fees:** Profit factor > 2.5x (given 36% win rate)
- **Current profit factor:** ~1.9x
- **Gap:** Need ~30% improvement in signal quality

---

## Conclusions

### Steps 1-2 Verdict: **Marginal Improvement**

Feature engineering and regime detection provide modest benefits but do not solve the fundamental signal quality issue.

### Recommendations for Step 3 (Gradient Boosting)

The Bayesian k-means approach has inherent limitations:
1. **Unsupervised clustering** finds patterns but doesn't optimize for profitability
2. **Linear regression combination** cannot capture non-linear relationships
3. **No feature importance** makes debugging difficult

LightGBM should address these issues by:
- Learning which features actually predict returns
- Capturing non-linear relationships
- Providing feature importance for analysis
- Potentially achieving higher win rates or profit factors

---

## Files Generated

| File | Description |
|------|-------------|
| `run_bayesian_poc_enhanced.py` | Enhanced implementation with regime detection |
| `results/enhanced_performance_*.png` | Performance visualization |

---

## Next Steps

1. **Implement Step 3:** Replace k-means with LightGBM
2. **Add direction classification:** Predict up/down/neutral instead of price change magnitude
3. **Cost-aware training:** Incorporate transaction costs into the loss function

---

**Report End**
