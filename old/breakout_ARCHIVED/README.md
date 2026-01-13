# Intraday Volatility Breakout System

A modular backtesting system for intraday volatility breakout strategies on cryptocurrency futures (Bybit).

## Setup

```bash
pip install -r requirements.txt
```

## Configuration

Configure the system by editing YAML files in `src/config/`:

- **`crypto_symbols.yaml`**: Symbol definitions, API settings, and data download date range (`start_date`, `end_date`)
- **`breakout_config.yaml`**: Strategy parameters (ATR period, multipliers, day start hour, fees)
- **`filter_config.yaml`**: Market condition filters (narrow day, volatility, trend)
- **`portfolio_config.yaml`**: Capital, position sizing method, symbol list

## Usage

### Run Complete Workflow

Run all 5 blocks with default configuration:
```bash
python src/main.py
```

### Custom Symbol

```bash
python src/main.py --symbol ETHUSDT
```

### Override Date Range (Optional)

Date ranges are configured in `crypto_symbols.yaml`. To override via command line:
```bash
python src/main.py --symbol ETHUSDT --start-date 2024-01-01 --end-date 2024-12-31
```

### Override Strategy Parameters

```bash
python src/main.py --atr-period 20 --breakout-multiplier 0.5 --stop-multiplier 0.25
```

### Run Specific Blocks

```bash
python src/main.py --blocks 2 4 5
```

## Output

The system generates:

- **Portfolio Report**: `src/reports/portfolio_report.html` - Performance statistics and charts
- **Chart Files**: `src/reports/{SYMBOL}_chart.html` - Interactive TradingView-style charts per symbol

## Workflow

The system follows a 5-block workflow:

1. **Download Data** → 2. **Generate Trades** → 3. **Filter Trades** → 4. **Build Portfolio** → 5. **Analyze**

All blocks are executed automatically when running `main.py`, or you can run specific blocks using `--blocks`.

