# Intraday Volatility Breakout System

A modular backtesting system for intraday volatility breakout strategies, supporting both traditional stocks (Alpaca) and cryptocurrency futures (Bybit).

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure symbols in `src/config/crypto_symbols.yaml`

## Usage

### Complete Workflow

The system follows a 5-block workflow:

1. **Download Data** → 2. **Generate Trades** → 3. **Filter Trades** → 4. **Build Portfolio** → 5. **Analyze**

### Block 1: Download Crypto Data

Download ETHUSDT data (default, last 7 days):
```bash
python src/bybit_downloader.py
```

Download specific symbol:
```bash
python src/bybit_downloader.py --symbol BTCUSDT
```

Download with date range:
```bash
python src/bybit_downloader.py --symbol ETHUSDT --start-date 2025-12-01 --end-date 2025-12-16
```

### Block 2: Generate Breakout Trades

Process ETHUSDT data (default):
```bash
python src/breakout_engine.py --symbol ETHUSDT
```

With custom parameters:
```bash
python src/breakout_engine.py --symbol ETHUSDT --atr-period 14 --breakout-multiplier 0.33 --stop-multiplier 0.33
```

### Block 3: Filter Trades

Filter trades based on market conditions:
```bash
python src/trade_filter.py --symbol ETHUSDT
```

Configure filters in `src/config/filter_config.yaml`:
- Narrow day filter
- Volatility contraction filter
- Trend filter
- Volatility expansion filter
- AND/OR logic mode

### Block 4: Build Portfolio

Build portfolio with position sizing:
```bash
python src/portfolio_builder.py
```

Configure in `src/config/portfolio_config.yaml`:
- Starting capital
- Position sizing method (risk-based, fixed dollar, equal weight)
- Symbol list

### Block 5: Analyze Portfolio

Generate performance report:
```bash
python src/portfolio_analysis.py
```

Outputs:
- **Portfolio Report** (`outputs/reports/portfolio_report.html`): Main HTML report with performance statistics
- **Chart Files** (per symbol): Interactive TradingView charts
  - `outputs/reports/{SYMBOL}_chart.html` - Interactive chart for each symbol
  - `outputs/reports/chart_data/{SYMBOL}_chart_data.json` - Chart data files

Each symbol chart displays:
- Price history (candlestick chart)
- Trade markers (triangles for entry, circles for exit/SL)
- Breakout levels and stop loss levels (horizontal lines)

### Python API

**Download Data:**
```python
from src.bybit_downloader import BybitDownloader
from datetime import datetime, timedelta

downloader = BybitDownloader()
filepath = downloader.download_and_save(symbol='ETHUSDT')
```

**Generate Trades:**
```python
from src.breakout_engine import CryptoBreakoutEngine

engine = CryptoBreakoutEngine(atr_period=14, breakout_multiplier=0.33)
trades_df = engine.process_symbol('ETHUSDT')
```

**Filter Trades:**
```python
from src.trade_filter import TradeFilter

trade_filter = TradeFilter()
filtered_trades = trade_filter.filter_symbol('ETHUSDT')
```

**Build Portfolio:**
```python
from src.portfolio_builder import PortfolioBuilder

builder = PortfolioBuilder()
portfolio_df = builder.build_portfolio()
```

**Analyze:**
```python
from src.portfolio_analysis import PortfolioAnalysis

analyzer = PortfolioAnalysis()
report_file = analyzer.analyze()
```

## Adding New Symbols

Edit `src/config/crypto_symbols.yaml`:

```yaml
symbols:
  NEWUSDT:
    symbol: NEWUSDT
    category: linear
    description: New Coin Perpetual Futures
```

Then download:
```bash
python src/bybit_downloader.py --symbol NEWUSDT
```

## Configuration

See `src/config/crypto_symbols.yaml` for:
- Symbol definitions
- API rate limits
- Data directory paths

## Documentation

- [Main Implementation Plan](IMPLEMENTATION_PLAN.md) - Stock trading implementation
- [Crypto Implementation](CRYPTO_IMPLEMENTATION.md) - Crypto-specific details

