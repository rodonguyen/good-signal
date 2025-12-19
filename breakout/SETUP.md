# Setup Instructions

## Virtual Environment Setup

### 1. Create Virtual Environment (if not already created)
```bash
python -m venv venv
```

### 2. Activate Virtual Environment

**Windows (PowerShell):**
```powershell
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 3. Install Dependencies
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Verify Installation
```bash
python -m pip list
```

## Usage

After activation, you can run any of the scripts:

```bash
# Download data
python src/bybit_downloader.py

# Generate trades
python src/breakout_engine.py --symbol ETHUSDT

# Filter trades
python src/trade_filter.py --symbol ETHUSDT

# Build portfolio
python src/portfolio_builder.py

# Analyze portfolio
python src/portfolio_analysis.py
```

## Deactivate Virtual Environment

When done, deactivate the virtual environment:
```bash
deactivate
```

## Notes

- The `lightweight-charts` package is commented out in `requirements.txt` because it has Windows build issues with `pythonnet` dependency
- For HTML reports, we use TradingView's JavaScript library directly (no Python dependency needed)
- Desktop GUI examples require `lightweight-charts` but may not work on Windows

