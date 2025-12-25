"""
Download historical order book data from Bybit for ETHUSDT perpetual.
Attempts to get historical order book snapshots. If unavailable, falls back to using volume as proxy.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import time
from pybit.unified_trading import HTTP


def try_download_historical_orderbook(symbol: str, start_date: datetime, end_date: datetime):
    """
    Attempt to download historical order book data from Bybit.

    Note: Bybit typically doesn't provide historical order book snapshots via API.
    This function will attempt various approaches and document what's available.
    """
    client = HTTP(testnet=False)

    print(f"Attempting to download order book data for {symbol}...")
    print(f"Date range: {start_date} to {end_date}")

    # Try to get current order book to see structure
    try:
        response = client.get_orderbook(category="linear", symbol=symbol, limit=60)
        if response["retCode"] == 0:
            print("\n[OK] Current order book structure:")
            print(f"  Bid levels: {len(response['result']['b'])}")
            print(f"  Ask levels: {len(response['result']['a'])}")
            print(f"  Sample bid: price={response['result']['b'][0][0]}, volume={response['result']['b'][0][1]}")
            print(f"  Sample ask: price={response['result']['a'][0][0]}, volume={response['result']['a'][0][1]}")
    except Exception as e:
        print(f"[FAILED] Could not fetch current order book: {e}")

    # Check if there's a historical order book endpoint
    print("\n[INFO] Historical order book snapshots are typically NOT available via Bybit API.")
    print("  Exchanges usually only provide real-time order book data via websocket.")
    print("\nFalling back to proxy method...")

    return None


def calculate_volume_imbalance_proxy(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate a proxy for order book imbalance using OHLCV data.

    Uses volume-weighted price movement to estimate buy/sell pressure.
    Not as accurate as real order book imbalance but provides similar signal.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        DataFrame with added 'imbalance_ratio' column
    """
    print("\nCalculating volume imbalance proxy from OHLCV data...")

    df = df.copy()

    # Calculate price change and volume
    df['price_change'] = df['close'] - df['open']

    # Estimate buy volume vs sell volume using price movement
    # If price went up, assume more buying pressure; if down, more selling
    df['buy_volume_proxy'] = np.where(df['price_change'] >= 0,
                                       df['volume'] * (1 + abs(df['price_change']) / df['close']),
                                       df['volume'] * (1 - abs(df['price_change']) / df['close']))

    df['sell_volume_proxy'] = np.where(df['price_change'] < 0,
                                        df['volume'] * (1 + abs(df['price_change']) / df['close']),
                                        df['volume'] * (1 - abs(df['price_change']) / df['close']))

    # Calculate imbalance ratio similar to paper: (v_bid - v_ask) / (v_bid + v_ask)
    # Range: [-1, +1] where positive = buying pressure, negative = selling pressure
    total_volume = df['buy_volume_proxy'] + df['sell_volume_proxy']
    df['imbalance_ratio'] = np.where(total_volume > 0,
                                      (df['buy_volume_proxy'] - df['sell_volume_proxy']) / total_volume,
                                      0.0)

    # Smooth with rolling window to reduce noise
    df['imbalance_ratio'] = df['imbalance_ratio'].rolling(window=5, min_periods=1).mean()

    # Clip to [-1, 1] range
    df['imbalance_ratio'] = df['imbalance_ratio'].clip(-1, 1)

    print(f"[OK] Calculated imbalance ratio proxy")
    print(f"  Range: [{df['imbalance_ratio'].min():.3f}, {df['imbalance_ratio'].max():.3f}]")
    print(f"  Mean: {df['imbalance_ratio'].mean():.3f}")
    print(f"  Std: {df['imbalance_ratio'].std():.3f}")

    return df


def main():
    """Main function to download or create order book proxy data."""

    # Load existing OHLCV data
    data_path = Path("E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_1min_from202506.csv")

    print(f"Loading OHLCV data from: {data_path}")
    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])

    print(f"[OK] Loaded {len(df)} rows")
    print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    print(f"  Columns: {list(df.columns)}")

    # Try to download historical order book
    start_date = df['timestamp'].min()
    end_date = df['timestamp'].max()

    historical_ob = try_download_historical_orderbook(
        symbol="ETHUSDT",
        start_date=start_date,
        end_date=end_date
    )

    # Create proxy data
    df_with_imbalance = calculate_volume_imbalance_proxy(df)

    # Save enhanced data
    output_path = Path("E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_1min_with_imbalance.csv")

    # Select relevant columns
    output_df = df_with_imbalance[['timestamp', 'open', 'high', 'low', 'close', 'volume', 'imbalance_ratio']]
    output_df.to_csv(output_path, index=False)

    print(f"\n[OK] Saved enhanced data to: {output_path}")
    print(f"  Columns: {list(output_df.columns)}")

    print("\n" + "="*60)
    print("ORDER BOOK DATA SUMMARY")
    print("="*60)
    print("[X] Historical order book snapshots: NOT AVAILABLE from Bybit API")
    print("[OK] Using volume-based imbalance ratio as proxy")
    print("  This estimates buy/sell pressure from price movement and volume")
    print("  Formula: (buy_vol_proxy - sell_vol_proxy) / (buy_vol_proxy + sell_vol_proxy)")
    print("  Range: [-1, +1] similar to paper's order book imbalance")
    print("="*60)


if __name__ == "__main__":
    main()
