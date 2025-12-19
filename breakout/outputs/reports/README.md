# Portfolio Chart Visualization

This directory contains a modular JavaScript implementation for visualizing portfolio analysis using TradingView Lightweight Charts.

## Files

- `portfolio-chart.js` - Main chart module (modular, reusable)
- `portfolio-chart-example.html` - Example HTML file showing usage
- `README.md` - This file

## Features

- **Price History**: Candlestick chart showing price movements
- **Trade Markers**: 
  - Triangles for buy/sell entries (green up for long, red down for short)
  - Circles for stop loss and exit points
- **Level Lines**: Horizontal lines showing:
  - Breakout levels (upper/lower) - dashed lines
  - Stop loss levels - dotted lines
  - Only shown for days with trades
- **Equity Curve**: Right y-axis displays portfolio equity value over time

## Usage

### 1. Include Required Libraries

```html
<!-- TradingView Lightweight Charts -->
<script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>

<!-- Portfolio Chart Module -->
<script src="portfolio-chart.js"></script>
```

### 2. Prepare Your Data

The chart expects data in the following format:

```javascript
const chartData = {
    containerId: 'chart-container',  // DOM element ID
    candlestickData: [
        { time: 1642427876, open: 10.0, high: 10.63, low: 9.49, close: 9.55 }
        // ... more candlestick data
    ],
    equityData: [
        { time: 1642427876, value: 10000 }
        // ... more equity data points
    ],
    trades: [
        {
            entryTime: 1642427876,      // Unix timestamp (seconds)
            exitTime: 1642514276,       // Unix timestamp (seconds)
            entryPrice: 10.0,
            exitPrice: 10.5,
            direction: 'long',          // 'long' or 'short'
            stopLevel: 9.5,             // Optional
            upperLevel: 10.3,           // Optional
            lowerLevel: 9.7,            // Optional
            exitReason: 'end_of_day',   // 'stop_loss' or 'end_of_day'
            portfolioPnl: 50.0
        }
        // ... more trades
    ],
    options: {
        height: 700  // Optional chart height
    }
};
```

### 3. Initialize the Chart

```javascript
// Wait for libraries to load
function initChart() {
    if (typeof LightweightCharts === 'undefined' || typeof PortfolioChart === 'undefined') {
        setTimeout(initChart, 100);
        return;
    }
    
    PortfolioChart.init(chartData);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initChart);
} else {
    setTimeout(initChart, 100);
}
```

## Exporting Data from Python

Use the `chart_data_exporter.py` module to export data from your Python analysis:

```python
from src.chart_data_exporter import export_chart_data_from_portfolio

# Export data to JSON file
chart_data = export_chart_data_from_portfolio(
    portfolio_file="data/portfolio/portfolio_trades.csv",
    price_data_file="data/raw/crypto/ETHUSDT/ETHUSDT_1min.csv",
    output_file="outputs/reports/chart_data.json"
)
```

Then load it in your HTML:

```javascript
fetch('chart_data.json')
    .then(response => response.json())
    .then(data => {
        const chartData = {
            containerId: 'chart-container',
            ...data,
            options: { height: 700 }
        };
        PortfolioChart.init(chartData);
    });
```

## Module Structure

The `portfolio-chart.js` module is organized into several sub-modules:

- **DataProcessor**: Handles data transformation and validation
- **MarkerBuilder**: Creates trade markers (triangles, circles)
- **HorizontalLineBuilder**: Creates price level lines
- **ChartInitializer**: Sets up chart and series
- **PortfolioChart**: Main controller

## API Reference

### PortfolioChart.init(config)

Initialize the chart with configuration.

**Parameters:**
- `config.containerId` (string, required): DOM element ID
- `config.candlestickData` (array): Candlestick price data
- `config.equityData` (array): Equity curve data
- `config.trades` (array): Trade objects
- `config.options` (object, optional): Chart options

**Returns:** Chart instance

### PortfolioChart.update(config)

Update chart with new data.

**Parameters:**
- `config`: Same as `init()`

### PortfolioChart.destroy()

Destroy the chart instance and clean up resources.

## Customization

### Colors

Modify colors in the `CHART_COLORS` constant at the top of `portfolio-chart.js`:

```javascript
const CHART_COLORS = {
    candlestick: { up: '#26a69a', down: '#ef5350', ... },
    equity: { line: '#2196F3', ... },
    markers: { buy: '#00ff00', sell: '#ff0000', ... },
    // ...
};
```

### Chart Options

Pass custom options when initializing:

```javascript
PortfolioChart.init({
    containerId: 'chart-container',
    // ... data ...
    options: {
        height: 800,
        // Add more options as needed
    }
});
```

## Browser Compatibility

Requires browsers supporting ES2020 features. For older browsers, use a transpiler like Babel.

## License

This module uses TradingView Lightweight Charts, which requires attribution. See the TradingView license for details.

