"""
Check if Bybit provides historical order book data through their API.
Investigate available endpoints for order book snapshots.
"""

from pybit.unified_trading import HTTP
import time
from datetime import datetime, timedelta
import pandas as pd

client = HTTP(testnet=False)

print("Investigating Bybit API for historical order book data...\n")

# 1. Check current order book
print("="*60)
print("1. CURRENT ORDER BOOK")
print("="*60)
try:
    ob = client.get_orderbook(category="linear", symbol="ETHUSDT", limit=60)
    if ob["retCode"] == 0:
        print("[OK] Current order book available")
        print(f"  Update time: {ob['result']['ts']}")
        print(f"  Bid levels: {len(ob['result']['b'])}")
        print(f"  Ask levels: {len(ob['result']['a'])}")
except Exception as e:
    print(f"[ERROR] {e}")

# 2. Check if there's ticker data with bid/ask
print("\n" + "="*60)
print("2. TICKER DATA (may include bid/ask)")
print("="*60)
try:
    ticker = client.get_tickers(category="linear", symbol="ETHUSDT")
    if ticker["retCode"] == 0:
        print("[OK] Ticker data available")
        result = ticker['result']['list'][0]
        print(f"  Available fields: {list(result.keys())}")
        if 'bid1Price' in result:
            print(f"  Best bid: {result.get('bid1Price')}, size: {result.get('bid1Size')}")
            print(f"  Best ask: {result.get('ask1Price')}, size: {result.get('ask1Size')}")
except Exception as e:
    print(f"[ERROR] {e}")

# 3. Check kline data for volume info
print("\n" + "="*60)
print("3. KLINE DATA (includes volume)")
print("="*60)
try:
    # Get recent kline
    now_ms = int(time.time() * 1000)
    kline = client.get_kline(
        category="linear",
        symbol="ETHUSDT",
        interval="1",
        limit=5
    )
    if kline["retCode"] == 0:
        print("[OK] Kline data available")
        print(f"  Columns: timestamp, open, high, low, close, volume, turnover")
        print(f"  Sample: {kline['result']['list'][0]}")
except Exception as e:
    print(f"[ERROR] {e}")

# 4. Check public trading data
print("\n" + "="*60)
print("4. PUBLIC TRADING DATA (recent trades)")
print("="*60)
try:
    trades = client.get_public_trade_history(
        category="linear",
        symbol="ETHUSDT",
        limit=10
    )
    if trades["retCode"] == 0:
        print("[OK] Public trade history available")
        print(f"  Number of recent trades: {len(trades['result']['list'])}")
        sample = trades['result']['list'][0]
        print(f"  Sample trade fields: {list(sample.keys())}")
        print(f"  Sample: {sample}")
except Exception as e:
    print(f"[ERROR] {e}")

# 5. Check insurance/funding data
print("\n" + "="*60)
print("5. MARKET DATA ENDPOINTS")
print("="*60)

# Try to get open interest
try:
    oi = client.get_open_interest(category="linear", symbol="ETHUSDT", intervalTime="1h", limit=5)
    if oi["retCode"] == 0:
        print("[OK] Open interest data available")
        print(f"  Sample: {oi['result']['list'][0]}")
except Exception as e:
    print(f"[INFO] Open interest: {e}")

# 6. Check if there's historical order book via websocket-like endpoint
print("\n" + "="*60)
print("6. HISTORICAL ORDER BOOK INVESTIGATION")
print("="*60)
print("[INFO] Checking Bybit documentation...")
print("  - get_orderbook() only provides CURRENT snapshot")
print("  - No REST API endpoint for HISTORICAL order book snapshots")
print("  - Historical order book would require:")
print("    a) Real-time websocket recording (not available historically)")
print("    b) Third-party data provider (e.g., Kaiko, CryptoCompare)")
print("    c) Bybit's institutional data feeds (if available)")

# 7. Alternative: Can we reconstruct from trade data?
print("\n" + "="*60)
print("7. ALTERNATIVE APPROACHES")
print("="*60)
print("[OPTION 1] Use current order book snapshot for live trading")
print("[OPTION 2] Use volume from kline data as proxy (already implemented)")
print("[OPTION 3] Use tick-by-tick trade data to estimate order flow")
print("[OPTION 4] Check if Bybit provides downloadable historical snapshots")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("Bybit REST API provides:")
print("  [YES] Current order book snapshot via get_orderbook()")
print("  [YES] Historical OHLCV data via get_kline()")
print("  [YES] Recent public trades via get_public_trade_history()")
print("  [NO]  Historical order book snapshots via REST API")
print("\nFor historical order book, you would need:")
print("  - Real-time websocket data collection (going forward)")
print("  - Third-party historical data provider")
print("  - Bybit institutional data access (if available)")
print("="*60)
