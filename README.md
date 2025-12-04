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

## Format Code

```bash
black .
```

