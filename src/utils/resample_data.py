"""
Script to resample OHLCV data to different timeframes.

This script reads OHLCV CSV data and creates resampled versions
for backtesting strategies that require different timeframes.
"""

import pandas as pd
from pathlib import Path
from typing import Literal

SupportedTimeframe = Literal["1m", "5m", "15m", "1h", "4h", "1d"]


def _get_resample_rule(timeframe: str) -> str:
    """
    Convert timeframe string to pandas resample rule.

    Args:
        timeframe: Timeframe string (e.g., "1m", "5m", "1h", "4h", "1d")

    Returns:
        Pandas resample rule string
    """
    rule_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }
    if timeframe not in rule_map:
        raise ValueError(f"Unsupported timeframe: {timeframe}. " f"Supported: {', '.join(rule_map.keys())}")
    return rule_map[timeframe]


def resample_data(
    input_file: str,
    output_file: str,
    timeframe: str = "4h",
    timestamp_col: str = "timestamp",
):
    """
    Resample OHLCV data to a different timeframe.

    Args:
        input_file: Path to input CSV file
        output_file: Path to output CSV file
        timeframe: Target timeframe (e.g., "1m", "5m", "15m", "1h", "4h", "1d")
        timestamp_col: Name of the timestamp column (default: "timestamp")
    """
    print(f"Reading data from: {input_file}")

    # Read the data
    df = pd.read_csv(input_file)

    # Validate required columns
    required_cols = {"open", "high", "low", "close", "volume", timestamp_col}
    missing = sorted(required_cols - set(df.columns))
    if missing:
        raise ValueError(f"CSV file missing required columns: {missing}")

    # Convert timestamp to datetime and set as index
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], utc=True)
    df = df.set_index(timestamp_col)
    df = df.sort_index()

    print(f"Loaded {len(df)} bars")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")

    # Get resample rule
    rule = _get_resample_rule(timeframe)

    # Resample using OHLCV aggregation
    resampled = df.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    # Add turnover if it exists in the original data
    if "turnover" in df.columns:
        resampled["turnover"] = df["turnover"].resample(rule, label="left", closed="left").sum()

    # Drop rows with NaN (incomplete bars)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])

    # Reset index to have timestamp as a column
    resampled = resampled.reset_index()

    print(f"Resampled to {len(resampled)} {timeframe} bars")
    print(f"Date range: {resampled[timestamp_col].iloc[0]} to {resampled[timestamp_col].iloc[-1]}")

    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to CSV
    print(f"Saving to: {output_file}")
    resampled.to_csv(output_file, index=False)

    print("Done!")
    print(f"\nFirst few rows:")
    print(resampled.head())
    print(f"\nLast few rows:")
    print(resampled.tail())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Resample OHLCV data to different timeframes")
    parser.add_argument(
        "--input",
        type=str,
        default="data/raw/crypto/ETHUSDT/ETHUSDT_1min.csv",
        help="Path to input CSV file",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to output CSV file (default: auto-generated from input and timeframe)",
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        default="4h",
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        help="Target timeframe (default: 4h)",
    )

    args = parser.parse_args()

    # Auto-generate output path if not provided
    if args.output is None:
        input_path = Path(args.input)
        output_path = input_path.parent / f"{input_path.stem.replace('_1min', '')}_{args.timeframe}.csv"
        args.output = str(output_path)

    # Resample the data
    resample_data(args.input, args.output, timeframe=args.timeframe)
