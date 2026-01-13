"""
Resample 1-min ETHUSDT data with imbalance ratio to 15-min bars.

Based on src/utils/resample_data.py but handles imbalance_ratio column.
"""

import pandas as pd
from pathlib import Path


def resample_to_15min(input_file: str, output_file: str):
    """
    Resample 1-min OHLCV+imbalance data to 15-min bars.

    Args:
        input_file: Path to input CSV file (1-min data)
        output_file: Path to output CSV file (15-min data)
    """
    print(f"Reading data from: {input_file}")

    # Read the data
    df = pd.read_csv(input_file)

    # Convert timestamp to datetime and set as index
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    df = df.sort_index()

    print(f"Loaded {len(df)} 1-min bars")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    print(f"Columns: {list(df.columns)}")

    # Resample to 15-min bars
    agg_dict = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }

    # Add imbalance_ratio if present (use mean for aggregation)
    if "imbalance_ratio" in df.columns:
        agg_dict["imbalance_ratio"] = "mean"
        print("Including imbalance_ratio (using mean for aggregation)")

    resampled = df.resample("15min", label="left", closed="left").agg(agg_dict)

    # Drop rows with NaN (incomplete bars)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])

    # Reset index to have timestamp as a column
    resampled = resampled.reset_index()

    print(f"\nResampled to {len(resampled)} 15-min bars")
    print(f"Reduction: {len(df)} -> {len(resampled)} ({len(df)/len(resampled):.1f}x)")
    print(f"Date range: {resampled['timestamp'].iloc[0]} to {resampled['timestamp'].iloc[-1]}")

    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to CSV
    print(f"\nSaving to: {output_file}")
    resampled.to_csv(output_file, index=False)

    print("\nDone!")
    print(f"\nFirst few rows:")
    print(resampled.head())
    print(f"\nLast few rows:")
    print(resampled.tail())

    return resampled


if __name__ == "__main__":
    input_file = "E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_1min_from202305_with_imbalance.csv"
    output_file = "E:/Personal/GitHub/good-signal/bayesian_method_poc/ETHUSDT_15min_with_imbalance.csv"

    resample_to_15min(input_file, output_file)
