# Intraday Volatility Breakout System - Implementation Plan

## Overview

This document outlines the implementation plan for building a modular intraday volatility breakout backtesting system using Python and Alpaca API. The system follows a 6-block workflow designed for simplicity, modularity, and ease of extension.

## Core Strategy Logic

### Basic Breakout Rules
- **ATR Calculation**: Average True Range (daily range)
- **Breakout Levels**: 
  - Upper: `Close + k × ATR` (default k = 0.33)
  - Lower: `Close - k × ATR` (default k = 0.33)
- **Entry Logic**:
  - Long: Price breaks above upper level
  - Short: Price breaks below lower level
- **Risk Management**:
  - Fixed stop loss: `k × ATR` (default k = 0.33)
  - Exit: End of day (EOD)
- **Constraints**:
  - One breakout attempt per day per symbol
  - Simple exit (fixed stop + EOD)

### Enhanced Logic (Market Context Filters)
- Trade breakouts only when market conditions are favorable:
  - Narrow day filter
  - Low volatility contraction
  - Trend filter
  - Volatility expansion pattern
- Logic: `if market_context_ok -> set_next_day_breakout_levels`

## 6-Block Workflow Architecture

### Block 1: Data Downloader
**Purpose**: Download and store 1-minute bar data from Alpaca API

**Inputs**:
- Symbol list (SPY, QQQ, IWM, GLD, TLT, sector ETFs, futures proxies)
- Date range (start_date, end_date)
- Alpaca API credentials (API key, secret key)

**Outputs**:
- CSV files (one per symbol)
- Directory structure: `data/{symbol}/{symbol}_YYYY-MM-DD.csv` or `data/{symbol}_1min.csv`

**Technical Requirements**:
- Use Alpaca Python SDK (`alpaca-py`) or direct API calls
- Download SIP (Securities Information Processor) quality data
- Handle rate limiting and API errors
- Data format: timestamp, open, high, low, close, volume
- Save as clean CSV files
- Support incremental updates (check existing files)

**Key Functions**:
- `download_symbol_data(symbol, start_date, end_date)` → saves CSV
- `validate_data_quality(dataframe)` → checks for gaps, errors
- `organize_data_structure()` → creates directory hierarchy

**Unclear Requirements**:
- Should we download all data at once or symbol-by-symbol?
- How to handle missing bars or data gaps?
- Should we store raw data or pre-processed (normalized timestamps)?
- Timezone handling (market hours vs UTC)?

---

### Block 2: Basic Breakout Engine
**Purpose**: Execute breakout logic on 1-minute data and generate raw trades

**Inputs**:
- CSV files from Block 1 (1-minute bars)
- Strategy parameters:
  - ATR period (default: 14 days?)
  - Breakout multiplier (k, default: 0.33)
  - Stop loss multiplier (default: 0.33)
  - Entry time window (e.g., market open to close)

**Outputs**:
- CSV file per symbol with all trades
- Columns: date, symbol, entry_time, exit_time, direction (long/short), entry_price, exit_price, stop_price, pnl, ATR_value, breakout_level_upper, breakout_level_lower
- Metadata: ATR values, breakout levels per day

**Technical Requirements**:
- Read 1-minute CSV files
- Calculate daily ATR (average of daily high-low ranges over period)
- For each trading day:
  - Calculate breakout levels at previous day's close
  - Monitor for breakout during trading hours
  - Execute trade on first breakout
  - Apply stop loss if hit
  - Exit at end of day if still in position
- Handle edge cases:
  - No breakout during day
  - Multiple breakouts (only first counts)
  - Stop hit before EOD
  - Gap opens beyond breakout levels

**Key Functions**:
- `calculate_daily_atr(dataframe, period=14)` → returns ATR series
- `calculate_breakout_levels(close_price, atr, multiplier)` → returns (upper, lower)
- `detect_breakout(minute_bars, upper_level, lower_level)` → returns (direction, entry_time, entry_price) or None
- `execute_trade(entry, stop_level, eod_time, minute_bars)` → returns trade record
- `process_symbol(symbol, params)` → generates trade CSV

**Unclear Requirements**:
- ATR calculation period (14 days? 20 days? Based on what timeframe?)
- Should breakout levels be set at previous day's close or current day's open?
- What if price gaps beyond breakout levels at open?
- Should we use actual ATR (True Range) or simple daily range?
- Market hours definition (9:30 AM - 4:00 PM ET? Include pre-market?)
- How to handle early market close (holidays)?

---

### Block 3: Trade Filter
**Purpose**: Apply market condition filters to raw trades

**Inputs**:
- Trade CSV from Block 2
- Market condition data (daily bars for context)
- Filter parameters:
  - Narrow day threshold
  - Volatility contraction criteria
  - Trend filter rules
  - Volatility expansion patterns

**Outputs**:
- Filtered trade CSV (same format as Block 2, but subset)

**Technical Requirements**:
- Read daily bars for market context
- Calculate filter conditions:
  - **Narrow day**: Previous day's range < threshold (e.g., < 0.5 × average range)
  - **Volatility contraction**: Recent ATR < longer-term ATR
  - **Trend filter**: Price above/below moving average
  - **Volatility expansion**: ATR increasing pattern
- Apply filters: `if condition_met -> keep_trade`
- Preserve trade metadata for analysis

**Key Functions**:
- `calculate_narrow_day(daily_bars, threshold)` → boolean series
- `calculate_volatility_contraction(daily_bars, short_period, long_period)` → boolean series
- `calculate_trend_filter(daily_bars, ma_period)` → boolean series
- `apply_filters(trades_df, daily_bars, filter_config)` → filtered trades

**Unclear Requirements**:
- Exact filter definitions (thresholds, periods)
- Should filters be AND (all must pass) or OR (any passes)?
- Do we need to calculate filters on the day before the trade or same day?
- Should we filter trades or filter days (prevent breakout levels from being set)?

---

### Block 4: Portfolio Builder
**Purpose**: Combine trades from multiple symbols into unified portfolio

**Inputs**:
- Filtered trade CSVs from Block 3 (one per symbol)
- Position sizing rules
- Portfolio configuration

**Outputs**:
- Unified trade list CSV
- Portfolio equity curve
- Per-symbol allocation

**Technical Requirements**:
- Read all symbol trade CSVs
- Combine into single dataframe
- Apply position sizing:
  - Fixed dollar amount per trade
  - Risk-based sizing (e.g., 1% risk per trade)
  - Equal weight per symbol
- Calculate portfolio-level metrics:
  - Combined equity curve
  - Daily P&L
  - Drawdown
- Handle overlapping trades (multiple symbols same day)

**Key Functions**:
- `load_all_trades(symbol_list, data_dir)` → combined dataframe
- `apply_position_sizing(trades_df, sizing_method, capital)` → adds position_size column
- `calculate_portfolio_equity(trades_df)` → equity curve series
- `build_portfolio(symbol_list, config)` → portfolio CSV

**Unclear Requirements**:
- Position sizing method (fixed dollar, risk-based, equal weight)?
- Starting capital amount?
- Should we allow multiple positions simultaneously?
- How to handle commissions and slippage (already in Block 2 or here)?

---

### Block 5: Portfolio Analysis
**Purpose**: Generate performance statistics and visualizations

**Inputs**:
- Portfolio trade CSV from Block 4
- Equity curve data

**Outputs**:
- Performance statistics (CSV or text report)
- Charts (equity curve, drawdown, monthly returns, etc.)

**Technical Requirements**:
- Calculate statistics:
  - Total return, annualized return
  - Sharpe ratio, Sortino ratio
  - Max drawdown, average drawdown
  - Win rate, average win/loss
  - Profit factor
  - Number of trades, trades per year
  - Average trade duration
- Generate visualizations:
  - Equity curve (line chart)
  - Drawdown chart
  - Monthly returns (bar chart)
  - Trade distribution (histogram)
  - Per-symbol performance (table/heatmap)
- Export reports (PDF, HTML, or markdown)

**Key Functions**:
- `calculate_statistics(equity_curve, trades_df)` → stats dictionary
- `plot_equity_curve(equity_curve)` → matplotlib figure
- `plot_drawdown(equity_curve)` → matplotlib figure
- `generate_report(stats, charts, output_path)` → saves report

**Unclear Requirements**:
- Report format preference (PDF, HTML, markdown, Jupyter notebook)?
- Which statistics are most important?
- Should we compare filtered vs unfiltered performance?
- Benchmark comparison (SPY, risk-free rate)?

---

### Block 6: RealTest Integration (Alternative to Blocks 3+4+5)
**Purpose**: Use RealTest software for filtering, portfolio building, and analysis

**Inputs**:
- Raw trades from Block 2 (CSV format)
- RealTest script/template

**Outputs**:
- RealTest analysis results
- Equity curves and statistics

**Technical Requirements**:
- Export trades in RealTest-compatible format
- RealTest script handles:
  - Market condition filters
  - Portfolio combination
  - Position sizing
  - Performance analytics
- Document RealTest import process

**Unclear Requirements**:
- RealTest file format specification?
- Is RealTest license required or free?
- Should we provide both Python and RealTest paths?

---

## Technical Stack

### Required Libraries
- **Data & API**: `alpaca-py` (Alpaca SDK), `pandas`, `numpy`
- **Data Processing**: `pandas`, `numpy`
- **Visualization**: `matplotlib`, `seaborn` (optional)
- **Utilities**: `python-dotenv` (for API keys), `pathlib`

### Project Structure
```
breakout/
├── data/
│   ├── raw/              # Block 1 output: 1-minute CSVs
│   │   ├── SPY/
│   │   ├── QQQ/
│   │   └── ...
│   ├── trades/           # Block 2 output: raw trades
│   │   ├── SPY_trades.csv
│   │   ├── QQQ_trades.csv
│   │   └── ...
│   ├── filtered/         # Block 3 output: filtered trades
│   └── portfolio/        # Block 4 output: combined portfolio
├── src/
│   ├── block1_downloader.py
│   ├── block2_breakout_engine.py
│   ├── block3_trade_filter.py
│   ├── block4_portfolio_builder.py
│   ├── block5_analysis.py
│   └── utils/
│       ├── data_utils.py
│       ├── calculation_utils.py
│       └── config.py
│   └── config/
│       ├── symbols.yaml      # Symbol list and settings
│       └── strategy_params.yaml  # Strategy parameters
├── outputs/
│   ├── reports/
│   └── charts/
├── requirements.txt
├── .env.example          # API key template
├── README.md
└── IMPLEMENTATION_PLAN.md
```

---

## Implementation Phases

### Phase 1: Setup & Data Download (Block 1)
1. Set up Python environment and dependencies
2. Create Alpaca API account and get credentials
3. Implement data downloader with error handling
4. Test download for 1-2 symbols over short date range
5. Validate data quality and structure

### Phase 2: Core Breakout Engine (Block 2)
1. Implement ATR calculation
2. Implement breakout level calculation
3. Implement trade detection and execution logic
4. Add stop loss and EOD exit handling
5. Test on single symbol, validate trade logic manually
6. Generate raw trades CSV

### Phase 3: Market Filters (Block 3)
1. Implement daily bar aggregation from 1-minute data
2. Implement narrow day filter
3. Implement volatility contraction filter
4. Implement trend filter
5. Implement filter combination logic
6. Test filtering on raw trades

### Phase 4: Portfolio Construction (Block 4)
1. Implement multi-symbol trade loading
2. Implement position sizing methods
3. Calculate portfolio equity curve
4. Handle overlapping positions
5. Generate unified portfolio CSV

### Phase 5: Analysis & Reporting (Block 5)
1. Implement performance statistics calculations
2. Create equity curve visualization
3. Create drawdown chart
4. Create monthly returns chart
5. Generate comprehensive report
6. Compare filtered vs unfiltered results

### Phase 6: Integration & Testing
1. End-to-end workflow test
2. Validate against article's example results (SPY + QQQ)
3. Document usage and parameters
4. Create example configurations
5. Error handling and edge cases

---

## Key Design Principles

1. **Modularity**: Each block is independent and can be modified without affecting others
2. **Simplicity**: Avoid over-engineering; keep code transparent and easy to understand
3. **Transparency**: All calculations and logic should be clear and verifiable
4. **Extensibility**: Easy to add new filters, symbols, or parameters
5. **LLM-Friendly**: Code structure that works well with ChatGPT/Claude modifications

---

## Unclear Requirements Summary

### Data & Timing
- [ ] ATR calculation period (14, 20, or other?)
- [ ] Breakout levels set at previous close or current open?
- [ ] Market hours definition (include pre-market? early closes?)
- [ ] Timezone handling (ET vs UTC)
- [ ] How to handle gaps beyond breakout levels at open?

### Strategy Logic
- [ ] Use True Range or simple daily range for ATR?
- [ ] Filter logic: AND (all must pass) or OR (any passes)?
- [ ] Filter timing: day before trade or same day?
- [ ] Exact filter thresholds and periods

### Portfolio Management
- [ ] Position sizing method (fixed, risk-based, equal weight)
- [ ] Starting capital amount
- [ ] Allow simultaneous positions across symbols?
- [ ] Commission/slippage handling location (Block 2 or Block 4?)

### Analysis & Reporting
- [ ] Report format (PDF, HTML, markdown, Jupyter?)
- [ ] Key statistics priority
- [ ] Benchmark comparison needed?
- [ ] RealTest integration path (required or optional?)

---

## Next Steps

1. **Clarify Requirements**: Address unclear requirements with stakeholder or make reasonable assumptions
2. **Start with Block 1**: Implement data downloader as foundation
3. **Iterate Block by Block**: Test each block independently before moving to next
4. **Validate Against Examples**: Compare results with article's SPY+QQQ example
5. **Document Assumptions**: Record all parameter choices and reasoning

---

## References

- Alpaca API Documentation: https://alpaca.markets/docs/
- Alpaca Python SDK: https://github.com/alpacahq/alpaca-py
- Article: "Intraday Volatility Breakout Blueprint" by Peter
- Related: "Day Trading Volatility Breakouts Systematically [All Rules Included]"


