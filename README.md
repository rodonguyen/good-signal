# Trading Signal Bot

A Python bot that monitors cryptocurrency prices using Bollinger Bands and sends trading signals via Discord.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
# Copy example config files
cp config/assets.yaml.example config/assets.yaml
cp config/discord.yaml.example config/discord.yaml

# Edit with your settings
# - Add Discord webhook URL to config/discord.yaml
# - Configure assets in config/assets.yaml
```

### 3. Run

```bash
python main.py
```

## Configuration

- **`config/discord.yaml`**: Discord webhook URL for notifications
- **`config/assets.yaml`**: Trading pairs and strategy settings

## Requirements

- Python 3.9+
- See `requirements.txt` for dependencies

## Backtesting

### Quick Start


2. **Configure**: Edit `config/backtest/backtest.yaml`:
   - Set `universe.symbols` to your trading pairs
   - Enable desired strategies
   - Configure `enabled_blocks` (1=data download, 2=run strategy, 3=filters, 4=portfolio, 5=analysis)

3. **Run**:
   ```bash
   python backtest.py
   ```

4. **View results**: Reports are generated in `outputs/reports/{strategy_id}/`

### Data Download (Optional)

To download historical data automatically:
- Set `data.download.enabled: true`
- Set `data.download.start_date` and `end_date` (YYYY-MM-DD format)
- Run with `enabled_blocks: [1]` to download only, or include `1` in the list

### Output Files

- **Trades**: `data/trades/{strategy_id}/{SYMBOL}_trades.csv`
- **Portfolio**: `data/portfolio/{strategy_id}/portfolio_trades.csv`
- **Reports**: `outputs/reports/{strategy_id}/portfolio_report.html`

## Walk-Forward Optimization

Walk-forward optimization (WFO) tests parameter combinations across rolling time windows to find optimal strategy parameters while avoiding overfitting.

### Quick Start

1. **Ensure you have historical data**:
   - Data should be in `data/raw/crypto/{SYMBOL}/{SYMBOL}_1min.csv` or `{SYMBOL}_1min_from202305.csv`
   - The system will automatically segment data from a single CSV file by date ranges

2. **Configure WFO** (optional):
   - Edit `config/backtest/wfo_config.yaml` to customize parameters
   - If not specified, uses defaults (6-month train, 3-month test, 3-month step)

3. **Run WFO**:
   ```bash
   python wfo.py
   ```
   
   Or specify custom config:
   ```bash
   python wfo.py --wfo-config config/backtest/wfo_config.yaml
   ```

4. **View results**: 
   - HTML report: `outputs/reports/wfo_{strategy}/wfo_report.html`
   - Open in browser to see interactive charts and metrics

### Configuration File

Edit `config/backtest/wfo_config.yaml` to customize:

```yaml
strategy: atr_breakout
symbol: ETHUSDT  # Optional: uses first from backtest.yaml if null

windows:
  train_months: 6
  test_months: 3
  step_months: 3

parameters:
  breakout_multiplier:
    start: 0.24
    end: 0.60
    step: 0.02
  stop_multiplier:
    start: 0.16
    end: 0.50
    step: 0.02

optimization_target: sharpe  # Options: 'sharpe', 'pnl', 'return'
```

### Example: Quick Test with Small Grid

For faster testing, edit `wfo_config.yaml` to use smaller ranges:

```yaml
parameters:
  breakout_multiplier:
    start: 0.24
    end: 0.32
    step: 0.02
  stop_multiplier:
    start: 0.16
    end: 0.24
    step: 0.02
```

This tests 5×5 = 25 combinations instead of 19×18 = 342.

### How It Works

1. **Data Loading**: Loads the full CSV file once (e.g., `ETHUSDT_1min_from202305.csv`)
2. **Window Calculation**: Creates rolling windows (e.g., 6-month train, 3-month test, 3-month step)
3. **Grid Search**: For each training window, tests all parameter combinations
4. **Best Selection**: Selects best config by Sharpe ratio
5. **Out-of-Sample Testing**: Tests selected config on the next 3-month period
6. **Reporting**: Generates HTML report with:
   - Scatter plots showing parameter performance (color=Sharpe, size=PnL)
   - Parameter stability heatmap
   - Combined out-of-sample equity curve
   - Per-cycle metrics and results

### Report Features

- **Interactive Scatter Plots**: Hover to see metrics, star marker for best config, blue border for top 10% robustness zone
- **Parameter Stability**: Heatmap showing which parameter combinations were selected most often
- **Combined OOS Curve**: Stitched equity curve from all test periods
- **Full Grid Results**: Sortable table with all parameter combinations tested

## Format Code

```bash
black .
```

