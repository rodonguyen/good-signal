# Crypto Trading Implementation - ETHUSDT Futures

## Overview

This document outlines the implementation plan for adapting the intraday volatility breakout strategy for cryptocurrency trading using **ETHUSDT perpetual futures** on **Bybit**. The strategy uses 24-hour virtual trading days starting at 13:00 UTC.

## Key Configuration Decisions

### 1. Data Source: Bybit API (ETHUSDT Futures)

**Data Provider**: Bybit
- **Symbol**: `ETHUSDT` (perpetual futures contract)
- **Category**: `linear` (USDT-margined perpetual futures)
- **API**: Bybit REST API v5 or Python SDK (`pybit`)
- **Large Dataset Support**: ✅ Yes, Bybit allows downloading extensive historical data
  - Public API endpoints for historical data
  - No authentication required for historical data (public endpoints)
  - Rate limits: 120 requests/minute (public), higher with API key
  - Can download years of historical data

**Technical Requirements:**
- Use Bybit API endpoint: `https://api.bybit.com/v5/market/kline`
- Symbol format: `ETHUSDT`
- Category: `linear` (for perpetual futures)
- Timeframe: 1-minute klines (`interval=1`)
- Data format: timestamp (ms), open, high, low, close, volume, turnover
- Timezone: Use whatever timezone Bybit provides (typically UTC)
- Date range: Can download years of historical data

**Key Functions:**
- `download_bybit_futures_data(symbol='ETHUSDT', category='linear', start_date, end_date, interval='1')` → saves CSV
- `convert_bybit_to_standard_format(dataframe)` → standardizes column names
- Handle Bybit rate limits (120 requests per minute for public endpoints)

**Bybit API Details:**
- **Public Endpoint**: `/v5/market/kline` (no API key needed for historical data)
- **Category Parameter**: `category=linear` for USDT-margined perpetual futures
- **Rate Limits**: 120 requests/minute (public), higher with API key
- **Data Retention**: Extensive historical data available
- **Python SDK**: `pybit` package (`pip install pybit`)

**Gap Handling:**
- Crypto has little gaps - **ignore gaps**
- Use whatever timezone Bybit provides
- Virtual day boundaries are independent of data gaps

---

### 2. Trading Day Definition: 24-Hour Periods Starting at 13:00 UTC

**Day Start Time: 13:00 UTC** ✅ **CONFIRMED**

**Day Structure:**
- **Virtual Trading Day**: 13:00 UTC to 13:00 UTC next day (24-hour period)
- **Previous Day Close**: Price at 13:00 UTC (start of current day)
- **Current Day Close**: Price at 13:00 UTC next day (end of current day)
- **Breakout Levels**: Set at 13:00 UTC using previous 24-hour period's ATR
- **Entry Window**: 13:00 UTC to 13:00 UTC next day (full 24 hours)
- **Exit Time**: **13:00 UTC next day** - **CLOSE ALL TRADES** at this time (end of day)

**Implementation:**
- All timestamps stored in UTC
- Day boundaries: `datetime.floor('D')` adjusted to 13:00 UTC
- Previous day = current timestamp - 24 hours (aligned to 13:00 UTC boundary)
- **Mandatory Exit**: All open positions must be closed at 13:00 UTC (end of day)

**Key Functions:**
- `define_crypto_day(timestamp, day_start_hour=13)` → returns day identifier
- `get_previous_day_close(dataframe, current_day)` → price at previous 13:00 UTC
- `get_day_boundaries(date, day_start_hour=13)` → (start_time, end_time)
- `close_all_trades_at_eod(open_positions, eod_time=13:00 UTC)` → closes all positions

---

### 3. ATR Calculation: Last 14 Periods (24-Hour Periods)

**ATR Configuration: Last 14 periods** ✅ **CONFIRMED**

**Calculation Method:**
- **Period**: Use 24-hour periods (not calendar days)
- **ATR Definition**: Average of True Range over **14 periods** (14 × 24-hour periods)
- **True Range**: `max(high - low, abs(high - prev_close), abs(low - prev_close))`
- **Daily Range**: For each 24-hour period (13:00 UTC to 13:00 UTC), calculate:
  - High of period
  - Low of period
  - Close at end of period (13:00 UTC)
  - Previous close (13:00 UTC of previous period)

**Example:**
- Day 1: 13:00 UTC Jan 1 to 13:00 UTC Jan 2 → Range = High - Low
- Day 2: 13:00 UTC Jan 2 to 13:00 UTC Jan 3 → Range = High - Low
- ...
- Day 14: 13:00 UTC Jan 14 to 13:00 UTC Jan 15 → Range = High - Low
- **ATR(14) = Average of last 14 such 24-hour periods**

**Implementation:**
- Aggregate 1-minute bars into 24-hour periods (13:00 UTC boundaries)
- Calculate True Range for each 24-hour period
- Calculate ATR as rolling average of True Range (**period=14**)
- Use ATR from previous 24-hour period to set current day's breakout levels

**Key Functions:**
- `aggregate_24h_periods(dataframe, day_start_hour=13)` → daily bars
- `calculate_crypto_atr(daily_bars, period=14)` → ATR series
- `get_previous_day_atr(atr_series, current_day)` → ATR value for breakout calculation

---

### 4. Breakout Logic Adaptations (Block 2 Changes)

**Modified Entry Logic:**
- Breakout levels set at **13:00 UTC** (start of trading day)
- Levels based on **previous 24-hour period's close** and **ATR**
- Monitor for breakout during **entire 24-hour period** (13:00 UTC to 13:00 UTC)
- No market hours restriction (trade 24/7)

**Exit Logic:**
- **Mandatory Exit**: All open positions closed at **13:00 UTC** (end of day)
- Stop loss: If hit before 13:00 UTC, exit immediately
- End of day: If still in position at 13:00 UTC, exit at market price

**Edge Cases:**
- **Gap at 13:00 UTC**: Crypto has little gaps - ignore, use whatever price is available
- **Weekend/No Gaps**: Crypto trades continuously, no weekend gaps
- **High Volatility**: Crypto can have extreme moves; ensure stops are reasonable

**Key Functions:**
- `calculate_breakout_levels(prev_close_13utc, prev_atr, multiplier)` → (upper, lower)
- `detect_breakout_24h(minute_bars, upper_level, lower_level, day_start)` → trade or None
- `execute_crypto_trade(entry, stop_level, eod_13utc, minute_bars)` → trade record
- `close_all_trades_at_13utc(open_positions, eod_time)` → closes all positions

---

### 5. Fees: 0.15% Total Per Trade

**Fee Configuration: 0.15% total per trade** ✅ **CONFIRMED**

**Fee Structure:**
- **Total Fee**: 0.15% per trade (round trip: entry + exit)
- **Per Side**: ~0.075% per entry/exit (or as configured)
- **Implementation**: Deduct fees in Block 2 (trade execution)
- **Formula**: 
  ```
  pnl = (exit_price - entry_price) × direction × size - (entry_price + exit_price) × size × 0.0015
  ```
  Or simpler:
  ```
  pnl = (exit_price - entry_price) × direction × size × (1 - 0.0015)
  ```

**Fee Calculation:**
- Applied on both entry and exit
- Total: 0.15% of notional value per trade
- For futures: Fee based on contract value

**Key Functions:**
- `calculate_crypto_fees(entry_price, exit_price, size, fee_rate=0.0015)` → fee amount
- `apply_fees_to_pnl(raw_pnl, entry_price, exit_price, size, fee_rate=0.0015)` → net PnL

---

### 6. Additional Crypto-Specific Considerations

**A. Higher Volatility**
- Crypto markets are more volatile than stocks
- **Adjustment**: May need different breakout multipliers (k values)
  - Test: 0.33 (default), 0.5, 0.66 for crypto
  - Wider stops may be needed
- **Risk**: Higher chance of stop-outs, but also larger moves

**B. Liquidity & Slippage**
- ETHUSDT futures on Bybit has high liquidity
- Still consider:
  - Slippage during high volatility periods
  - Order book depth for larger positions
  - Spread costs (tighter on major pairs like ETHUSDT)
- **Implementation**: Add slippage model in backtest (e.g., 0.05% for market orders)

**C. Funding Rates (Perpetual Futures)**
- **ETHUSDT perpetual futures** have funding rates every 8 hours
- Funding rates can affect long-term positions
- **For intraday strategy**: Funding rates may have minimal impact since we exit at 13:00 UTC (within 24 hours)
- **Implementation**: Consider adding funding rate costs if holding positions longer than 8 hours
- **Note**: Since we close all trades at 13:00 UTC, funding rates may apply if position is held >8 hours

**D. No Market Holidays**
- Crypto trades 24/7, no holidays
- **Simplification**: No need to handle early closes or market holidays
- **Consistency**: Every day is a trading day

**E. Timezone Consistency**
- All data in UTC (from Bybit)
- All calculations in UTC
- Virtual day boundaries at 13:00 UTC
- **No DST issues**: UTC doesn't change
- **Gap handling**: Ignore gaps, use whatever timezone Bybit provides

---

### 7. Modified Project Structure for Crypto

```
breakout/
├── data/
│   ├── raw/
│   │   ├── crypto/           # Crypto-specific data
│   │   │   └── ETHUSDT/
│   │   │       └── ETHUSDT_1min.csv
│   ├── trades/
│   │   ├── ETHUSDT_trades.csv
│   │   └── ...
├── src/
│   ├── block1_bybit_downloader.py  # Crypto-specific Bybit downloader
│   ├── block2_breakout_engine.py    # Needs crypto day logic
│   ├── block3_trade_filter.py
│   ├── block4_portfolio_builder.py
│   ├── block5_analysis.py
│   └── utils/
│       ├── crypto_utils.py        # Crypto-specific helpers
│       │   ├── define_crypto_day()
│       │   ├── aggregate_24h_periods()
│       │   ├── calculate_crypto_atr()
│       │   └── close_all_trades_at_13utc()
│       ├── fee_calculator.py      # Fee calculation (0.15%)
│       └── config.py
├── src/
│   └── config/
│       ├── crypto_symbols.yaml        # ETHUSDT config
│       └── crypto_strategy_params.yaml
│       ├── atr_period: 14
│       ├── day_start_utc: 13:00
│       ├── fee_rate: 0.0015
│       └── symbol: ETHUSDT
```

---

### 8. Implementation Checklist for Crypto

**Block 1 (Data Downloader):**
- [ ] Implement Bybit API integration for ETHUSDT futures
- [ ] Use category `linear` for perpetual futures
- [ ] Implement Bybit kline data download (1-minute)
- [ ] Handle Bybit rate limits (120 req/min)
- [ ] Convert Bybit data format to standard CSV
- [ ] Use Bybit's native timezone (typically UTC)
- [ ] Ignore gaps (crypto has little gaps)
- [ ] Test downloading ETHUSDT futures data (1+ years)

**Block 2 (Breakout Engine):**
- [ ] Implement 24-hour day definition (13:00 UTC start)
- [ ] Implement ATR calculation for 24-hour periods (period=14)
- [ ] Update breakout level calculation (use previous 24h close)
- [ ] Modify entry detection for 24-hour window
- [ ] **Implement mandatory exit at 13:00 UTC** (close all trades)
- [ ] Add crypto fee calculation (0.15% per trade)
- [ ] Handle stop loss before EOD
- [ ] Test on ETHUSDT futures data

**Block 3-5 (Filters, Portfolio, Analysis):**
- [ ] Adapt filters for 24-hour periods
- [ ] Update portfolio builder for crypto symbols
- [ ] Adjust analysis for crypto-specific metrics
- [ ] Compare crypto vs stock performance characteristics

**Testing:**
- [ ] Validate day boundaries (13:00 UTC)
- [ ] Validate ATR calculation (14 periods of 24-hour periods)
- [ ] Validate mandatory exit at 13:00 UTC
- [ ] Validate fee calculation (0.15% per trade)
- [ ] Test edge cases (extreme volatility)
- [ ] Compare results with manual calculations

---

### 9. Configuration Summary

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Symbol** | ETHUSDT | Perpetual futures contract |
| **Category** | linear | USDT-margined perpetual futures |
| **Data Source** | Bybit API | Public endpoints, no auth needed |
| **Day Start** | 13:00 UTC | Virtual trading day boundary |
| **Day End** | 13:00 UTC | Close all trades at this time |
| **ATR Period** | 14 | Last 14 periods of 24-hour periods |
| **ATR Calculation** | True Range | Over 24-hour periods |
| **Fees** | 0.15% | Total per trade (entry + exit) |
| **Gap Handling** | Ignore | Crypto has little gaps |
| **Timezone** | UTC | Use Bybit's native timezone |

---

### 10. Key Differences from Stock Implementation

1. **Data Source**: Bybit API instead of Alpaca
2. **Symbol Type**: Futures contract (ETHUSDT) instead of spot ETF
3. **Day Definition**: 24-hour periods starting at 13:00 UTC (not market hours)
4. **ATR Period**: 14 periods of 24-hour periods (not calendar days)
5. **Mandatory Exit**: All trades closed at 13:00 UTC (end of day)
6. **Fees**: 0.15% per trade (different from stock commissions)
7. **Gap Handling**: Ignore gaps (crypto has little gaps)
8. **Funding Rates**: May apply if holding >8 hours (perpetual futures)
9. **No Holidays**: Trades 24/7, every day is a trading day

---

## References

- **Bybit API Documentation**: https://bybit-exchange.github.io/docs/v5/
- **Bybit Python SDK**: https://github.com/bybit-exchange/pybit (`pip install pybit`)
- **Bybit History Fetcher**: https://github.com/shadmau/bybit-history-fetcher
- **Bybit Historical Data Downloader**: https://github.com/ryu878/bybit_history_downloader
- **Main Implementation Plan**: [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)
- Article: "Intraday Volatility Breakout Blueprint" by Peter

