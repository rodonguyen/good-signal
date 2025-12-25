"""
Check if Binance provides historical order book data.
"""

import requests
import time
from datetime import datetime

print("Investigating Binance API for historical order book data...\n")

# Binance API base URLs
SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"

print("="*60)
print("1. CURRENT ORDER BOOK (Binance Futures)")
print("="*60)
try:
    response = requests.get(f"{FUTURES_BASE}/fapi/v1/depth", params={
        "symbol": "ETHUSDT",
        "limit": 100
    })
    if response.status_code == 200:
        data = response.json()
        print("[OK] Current order book available")
        print(f"  Bid levels: {len(data['bids'])}")
        print(f"  Ask levels: {len(data['asks'])}")
        print(f"  Last update ID: {data.get('lastUpdateId')}")
    else:
        print(f"[ERROR] {response.status_code}: {response.text}")
except Exception as e:
    print(f"[ERROR] {e}")

print("\n" + "="*60)
print("2. CHECKING FOR HISTORICAL ORDER BOOK DOWNLOADS")
print("="*60)
print("[INFO] Binance provides downloadable historical data at:")
print("  https://data.binance.vision/")
print("\nAvailable historical data types:")
print("  - Klines/Candlesticks: YES")
print("  - Trades: YES")
print("  - Aggregate Trades: YES")
print("  - Order Book Snapshots: CHECKING...")

# Check if order book snapshots are available
vision_base = "https://data.binance.vision"

print("\n" + "="*60)
print("3. BINANCE DATA VISION - ORDER BOOK DEPTH")
print("="*60)

# Try to access order book depth data
# Format: https://data.binance.vision/data/futures/um/daily/bookDepth/ETHUSDT/
test_urls = [
    f"{vision_base}/data/futures/um/daily/depth/ETHUSDT/",
    f"{vision_base}/data/futures/um/daily/bookDepth/ETHUSDT/",
    f"{vision_base}/data/spot/daily/depth/ETHUSDT/",
]

for url in test_urls:
    try:
        response = requests.head(url, timeout=5)
        print(f"  Testing: {url}")
        print(f"    Status: {response.status_code}")
        if response.status_code == 200:
            print(f"    [FOUND!] This endpoint exists")
    except Exception as e:
        print(f"    [ERROR] {e}")

# Check documentation page
print("\n" + "="*60)
print("4. BINANCE HISTORICAL DATA DOCUMENTATION")
print("="*60)
print("Checking available data types from Binance Vision...")

# List of known data types
data_types = [
    "aggTrades",  # Aggregate trades
    "klines",     # Candlesticks
    "trades",     # Individual trades
    "depth",      # Order book depth snapshots (if available)
    "bookTicker", # Best bid/ask ticker
]

print("\nKnown Binance historical data types:")
for dt in data_types:
    print(f"  - {dt}")

print("\n" + "="*60)
print("5. ALTERNATIVE: BINANCE PUBLIC DATA API")
print("="*60)
print("[INFO] Binance may offer order book snapshots via:")
print("  1. Downloadable files (data.binance.vision)")
print("  2. Institutional data feeds")
print("  3. Real-time websocket (diff depth stream)")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("\nBinance provides historical downloads at data.binance.vision:")
print("  [YES] Historical klines/candlesticks")
print("  [YES] Historical trades (tick-by-tick)")
print("  [???] Historical order book depth snapshots - NEEDS VERIFICATION")
print("\nTo verify order book depth availability:")
print("  1. Visit: https://data.binance.vision/")
print("  2. Navigate to futures/um/daily/ or spot/daily/")
print("  3. Look for 'depth' or 'bookDepth' folders")
print("\nNote: Even if not available as snapshots, we can:")
print("  - Use tick trades to reconstruct order flow")
print("  - Use bookTicker data if available")
print("  - Continue with volume-based proxy (already implemented)")
print("="*60)
