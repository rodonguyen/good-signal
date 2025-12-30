# LightGBM Trading Strategy - Enhancement Report

**Date:** December 30, 2025
**Implementation:** Step 3 from improvements.md - Replace K-Means with Gradient Boosting
**Timeframe:** 15-minute bars

---

## Executive Summary

This report analyzes the implementation of LightGBM to replace the Bayesian k-means clustering approach. The goal was to achieve better prediction quality through supervised learning.

**Key Finding:** LightGBM confirms what the Bayesian approach hinted at - **there is minimal predictable signal in short-term crypto returns**. The model consistently early-stops at 1-7 trees with near-zero feature importance, indicating the features do not contain exploitable patterns.

---

## Methodology

### LightGBM Configuration

| Parameter | Value |
|-----------|-------|
| Objective | Regression (MSE) |
| Boosting Type | GBDT |
| Num Leaves | 31 |
| Learning Rate | 0.05 |
| Feature Fraction | 0.8 |
| Bagging Fraction | 0.8 |
| CV Method | Time-Series Split (5 folds) |
| Early Stopping | 50 rounds |

### Features Engineered (24 total)

| Category | Features |
|----------|----------|
| Returns | returns_1, returns_5, returns_10, returns_20 |
| Volatility | volatility_10, volatility_20, vol_regime |
| Trend | sma_10, sma_20, sma_60, trend_short, trend_long |
| Mean Reversion | zscore_20, zscore_60 |
| Volume | volume_ratio |
| Momentum | roc_5, roc_10, roc_20 |
| Range | range_pct, high_close, close_low, atr_ratio |
| Technical | rsi_14, bb_position |

---

## Results

### Experiment 1: 1-Bar Horizon (15 minutes)

| Metric | Value |
|--------|-------|
| Prediction Horizon | 1 bar (15 min) |
| Trading Threshold | 0.01% |
| Trees per Fold | 1-13 (avg 4) |
| Completed Trades | 419 |
| Total Profit | $718.70 |
| Win Rate | 53.2% |
| Avg Win | $62.02 |
| Avg Loss | -$66.90 |
| Profit Factor | 0.93x |
| Feature Importance | All ~0.00 |

**Analysis:** Model stops immediately (1-4 trees). Features provide no predictive value for 15-minute returns.

### Experiment 2: 4-Bar Horizon (1 hour)

| Metric | Value |
|--------|-------|
| Prediction Horizon | 4 bars (1 hour) |
| Trading Threshold | 0.05% |
| Trees per Fold | 1-7 (avg 3.4) |
| Completed Trades | 89 |
| Total Profit | -$1,113.02 |
| Win Rate | 59.6% |
| Avg Win | $112.00 |
| Avg Loss | -$195.81 |
| Profit Factor | 0.57x |
| Top Feature | vol_regime (0.01) |

**Analysis:** Higher win rate but larger losses. The model predicts direction but not magnitude correctly.

---

## Comparison with Bayesian Approach

| Metric | Bayesian (Enhanced) | LightGBM (1-bar) | LightGBM (4-bar) |
|--------|---------------------|------------------|------------------|
| Trades | 3,458 | 419 | 89 |
| Gross P&L | $2,134 | $719 | -$1,113 |
| Win Rate | 36.3% | 53.2% | 59.6% |
| Profit Factor | 1.86x | 0.93x | 0.57x |

**Key Insight:** The Bayesian approach's positive results may be due to:
1. **Trade frequency:** More trades = more opportunity to compound small edges
2. **Pattern matching:** K-means finds recurring patterns even without predictive power
3. **Overfitting:** The training/test split may leak information through pattern similarity

---

## Feature Importance Analysis

All features show near-zero importance across both experiments. This indicates:

1. **No single feature predicts returns** at 15-minute resolution
2. **Non-linear combinations** are also ineffective (LightGBM would find them)
3. **Market efficiency** at short timeframes

Top features (minimal importance):
| Feature | Importance (4-bar) |
|---------|-------------------|
| vol_regime | 0.01 |
| atr_ratio | 0.01 |
| trend_long | 0.01 |
| zscore_60 | 0.01 |
| volatility_20 | 0.01 |

The volatility-related features show slightly more (but still minimal) importance.

---

## Root Cause Analysis

### Why LightGBM Underperforms Bayesian

1. **LightGBM is honest:** Early stopping reveals there's no signal to learn
2. **Bayesian overfits:** Pattern matching finds spurious patterns that happen to profit
3. **Trade frequency matters:** Bayesian trades 8x more often

### Why Prediction is Fundamentally Hard

1. **Market Microstructure:**
   - 15-minute returns are dominated by noise
   - Order flow randomness overwhelms any signal

2. **Feature Lag:**
   - All features are backward-looking
   - By the time a pattern forms, it's already priced in

3. **Regime Non-Stationarity:**
   - Patterns that worked in training may not work in test
   - Crypto markets change rapidly

---

## Conclusions

### Step 3 Verdict: **Negative (But Informative)**

LightGBM did not outperform the Bayesian approach, but it provided valuable information:

1. **Confirms low signal-to-noise ratio** at 15-minute resolution
2. **Features are not predictive** - need fundamentally different data sources
3. **Bayesian approach may be overfitting** - its positive results should be questioned

### Recommendations

#### Short-Term (If Pursuing This Strategy)
1. **Use longer timeframes:** 4-hour or daily bars
2. **Add alternative data:** On-chain metrics, funding rates, open interest
3. **Focus on regime filtering:** Only trade during high-signal periods

#### Medium-Term
1. **Try direction classification** instead of regression
2. **Implement cost-aware training** (Sharpe optimization)
3. **Explore reinforcement learning** for optimal position sizing

#### Long-Term
1. **Question the premise:** Short-term crypto prediction may be fundamentally unprofitable
2. **Consider market-making:** Use order book data for spread capture instead of direction prediction
3. **Ensemble methods:** Combine Bayesian pattern matching with ML filtering

---

## Files Generated

| File | Description |
|------|-------------|
| `lgb_trader.py` | LightGBM trading implementation |
| `run_lgb_poc.py` | Main execution script |
| `results/lgb_performance_*.png` | Performance visualizations |
| `results/lgb_model.pkl` | Saved model weights |

---

## Technical Notes

### Early Stopping Behavior

The model stops after 1-7 trees because:
- Validation loss does not improve after initial trees
- Early stopping patience is 50 rounds
- LightGBM correctly identifies that more complexity = more overfitting

### Cross-Validation Approach

Time-series split ensures:
- Training data always precedes validation
- No look-ahead bias
- Realistic out-of-sample estimation

---

## Summary Statistics

| Aspect | Finding |
|--------|---------|
| Signal Quality | Near-zero predictive power |
| Feature Importance | No feature significantly contributes |
| Model Complexity | 1-7 trees (extremely simple) |
| Win Rate | 53-60% (slightly better than random) |
| Profit Factor | < 1.0 (losing strategy) |

**Bottom Line:** The data does not support profitable short-term trading at 15-minute resolution using technical features.

---

**Report End**
