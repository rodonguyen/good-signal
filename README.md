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

## Format Code

```bash
black .
```

