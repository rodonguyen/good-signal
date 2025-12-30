"""
Preprocess the new ETHUSDT_1min.csv data file by adding imbalance ratio.
"""

import pandas as pd
import numpy as np
from pathlib import Path

print("=" * 60)
print("PREPROCESSING NEW DATA FILE")
print("=" * 60)

# Load data
input_file = Path("E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_1min_from202305.csv")
output_file = Path("E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_1min_from202305_with_imbalance.csv")

print(f"\n[LOG] Loading data from: {input_file}")
df = pd.read_csv(input_file)
df["timestamp"] = pd.to_datetime(df["timestamp"])

print(f"[OK] Loaded {len(df)} rows")
print(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
print(f"  Duration: {(df['timestamp'].max() - df['timestamp'].min()).days} days")
print(f"  Columns: {list(df.columns)}")

# Calculate volume imbalance proxy
print(f"\n[LOG] Calculating volume imbalance proxy...")

# Calculate price change
df["price_change"] = df["close"] - df["open"]

# Estimate buy volume vs sell volume using price movement
df["buy_volume_proxy"] = np.where(
    df["price_change"] >= 0, df["volume"] * (1 + abs(df["price_change"]) / df["close"]), df["volume"] * (1 - abs(df["price_change"]) / df["close"])
)

df["sell_volume_proxy"] = np.where(
    df["price_change"] < 0, df["volume"] * (1 + abs(df["price_change"]) / df["close"]), df["volume"] * (1 - abs(df["price_change"]) / df["close"])
)

# Calculate imbalance ratio: (v_bid - v_ask) / (v_bid + v_ask)
total_volume = df["buy_volume_proxy"] + df["sell_volume_proxy"]
df["imbalance_ratio"] = np.where(total_volume > 0, (df["buy_volume_proxy"] - df["sell_volume_proxy"]) / total_volume, 0.0)

# Smooth with rolling window
df["imbalance_ratio"] = df["imbalance_ratio"].rolling(window=5, min_periods=1).mean()

# Clip to [-1, 1] range
df["imbalance_ratio"] = df["imbalance_ratio"].clip(-1, 1)

print(f"[OK] Calculated imbalance ratio")
print(f"  Range: [{df['imbalance_ratio'].min():.3f}, {df['imbalance_ratio'].max():.3f}]")
print(f"  Mean: {df['imbalance_ratio'].mean():.3f}")
print(f"  Std: {df['imbalance_ratio'].std():.3f}")

# Save enhanced data
output_df = df[["timestamp", "open", "high", "low", "close", "volume", "imbalance_ratio"]]
output_df.to_csv(output_file, index=False)

print(f"\n[OK] Saved enhanced data to: {output_file}")
print(f"  Columns: {list(output_df.columns)}")
print(f"  Rows: {len(output_df)}")

print("\n" + "=" * 60)
print("PREPROCESSING COMPLETE")
print("=" * 60)
print(f"New data file ready: {output_file}")
print(f"Total: {len(output_df)} rows ({(df['timestamp'].max() - df['timestamp'].min()).days} days)")
print("=" * 60)
