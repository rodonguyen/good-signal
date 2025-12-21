"""
Backtest strategy: BBTrendline signals on 1h, executed on 1m with RR=4:1.

Rules (as agreed):
- Compute Bollinger Bands on 1h bars.
- Generate BUY/SELL signals using existing `src/strategies/bb_trendline.py`.
- Entry fill: next 1m candle open at/after signal time.
- Stop: fixed at bb_middle of the *signal hour* (the hour whose close broke).
- TP: RR=4.0 * risk, where risk = abs(entry - stop).
- Exit: first hit on 1m bars (ideal fill at level). If both hit in same 1m candle -> stop_first.
- Ignore signals while in a trade.
- Fees: round-trip fee_rate on (entry_notional + exit_notional).
"""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import numpy as np

from src.backtest.contracts import BaseBacktestStrategy, BacktestContext, validate_trades_df
from src.backtest.utils.fee_utils import calculate_pnl_with_fees
from src.backtest.utils.resample_utils import ensure_utc_timestamp, resample_ohlcv
from src.backtest.utils.crypto_day_utils import define_crypto_day
from src.indicators.bollinger_bands import BollingerBands
from src.strategies.bb_trendline import BBTrendlineStrategy


class BBTrendlineRR4BacktestStrategy(BaseBacktestStrategy):
    @property
    def strategy_id(self) -> str:
        return "bb_trendline_rr4"

    def generate_trades(self, minute_df: pd.DataFrame, *, context: BacktestContext, params: Mapping[str, Any]) -> pd.DataFrame:
        minute_df = ensure_utc_timestamp(minute_df, "timestamp").sort_values("timestamp").reset_index(drop=True)
        empty_cols = [
            "symbol",
            "strategy_id",
            "entry_time",
            "exit_time",
            "direction",
            "entry_price",
            "exit_price",
            "stop_level",
            "tp_level",
            "raw_pnl",
            "fees",
            "net_pnl",
            "exit_reason",
            # helpful extras
            "signal_time",
        ]
        if minute_df.empty:
            return pd.DataFrame(columns=empty_cols)

        # Prepare fast arrays for execution scanning
        timestamp_ns = minute_df["timestamp"].astype("int64").to_numpy()
        open_ = minute_df["open"].to_numpy(dtype=float, copy=False)
        high = minute_df["high"].to_numpy(dtype=float, copy=False)
        low = minute_df["low"].to_numpy(dtype=float, copy=False)
        close = minute_df["close"].to_numpy(dtype=float, copy=False)

        # --- Build 1h signal frame ---
        signal_tf = str(params.get("signal_timeframe", "1h"))
        exec_tf = str(params.get("execution_timeframe", "1m"))
        if exec_tf != "1m":
            raise ValueError("BBTrendlineRR4BacktestStrategy currently supports execution_timeframe='1m' only")
        if signal_tf != "1h":
            raise ValueError("BBTrendlineRR4BacktestStrategy currently supports signal_timeframe='1h' only")

        indicator_params = params.get("indicator_params", {"period": 20, "std_dev": 2.0})
        period = int(indicator_params.get("period", 20))
        std_dev = float(indicator_params.get("std_dev", 2.0))

        # Allow runner to inject cached signal bars (recommended).
        injected_hourly = params.get("_signal_bars")
        if injected_hourly is not None:
            hourly = ensure_utc_timestamp(pd.DataFrame(injected_hourly), "timestamp").sort_values("timestamp").reset_index(drop=True)
        else:
            hourly = resample_ohlcv(minute_df, timeframe="1h")

        if len(hourly) < max(4, period + 1):
            return pd.DataFrame(columns=empty_cols)

        bb = BollingerBands(period=period, std_dev=std_dev)
        hourly = bb.calculate(hourly)

        signal_strategy = BBTrendlineStrategy()

        rr = float(params.get("rr_take_profit", 4.0))
        conflict_resolution = str(params.get("conflict_resolution", "stop_first")).lower()
        if conflict_resolution not in {"stop_first", "tp_first"}:
            raise ValueError("conflict_resolution must be 'stop_first' or 'tp_first'")

        debug = bool(params.get("debug", False))
        hourly_ts = pd.to_datetime(hourly["timestamp"], utc=True)

        trades_out: list[dict[str, Any]] = []
        i = 0
        while i < len(hourly):
            if debug and (i % 100 == 0):
                print(f"Processing hour {i}/{len(hourly)}")
            if i < 3:
                i += 1
                continue

            window = hourly.iloc[i - 3 : i + 1].copy()
            # Avoid calling the live signal strategy during BB warm-up; it logs warnings on NaNs.
            # Signal strategy references:
            # - t-3 and t-2 BB values for trendline
            # - t-1 close for breakout check
            t_minus_3 = window.iloc[-4]
            t_minus_2 = window.iloc[-3]
            t_minus_1 = window.iloc[-2]
            if pd.isna(
                [
                    t_minus_3.get("bb_upper"),
                    t_minus_2.get("bb_upper"),
                    t_minus_3.get("bb_lower"),
                    t_minus_2.get("bb_lower"),
                    t_minus_1.get("close"),
                ]
            ).any():
                i += 1
                continue
            signal = signal_strategy.generate_signal(window)
            if not signal:
                i += 1
                continue

            # Signal time = current hour open (this is when previous hour is completed)
            signal_time = pd.to_datetime(hourly.iloc[i]["timestamp"], utc=True)

            # Check filter: map signal hour to day and check if allowed
            filter_allow_map: dict[str, bool] = params.get("filter_allow_map", {})
            if filter_allow_map:
                signal_day = define_crypto_day(signal_time, day_start_hour=13)
                if not filter_allow_map.get(signal_day, True):  # Default to allowed if not in map
                    i += 1
                    continue  # Filtered out, skip this signal

            # Stop uses bb_middle of the signal hour candle (t-1 in strategy window)
            bb_middle_signal_hour = float(window.iloc[-2]["bb_middle"])
            if pd.isna(bb_middle_signal_hour):
                i += 1
                continue

            # Entry: next 1m candle open at/after signal_time
            entry_idx = int(np.searchsorted(timestamp_ns, signal_time.value, side="left"))
            if entry_idx >= len(timestamp_ns):
                break
            entry_time = pd.to_datetime(timestamp_ns[entry_idx], utc=True)
            entry_price = float(open_[entry_idx])

            direction = "long" if signal["signal"] == "BUY" else "short"
            direction_int = 1 if direction == "long" else -1

            stop_level = bb_middle_signal_hour
            risk = abs(entry_price - stop_level)
            if risk <= 0:
                i += 1
                continue

            # Validate stop is on correct side; otherwise skip.
            if direction == "long" and stop_level >= entry_price:
                i += 1
                continue
            if direction == "short" and stop_level <= entry_price:
                i += 1
                continue

            tp_level = entry_price + direction_int * rr * risk

            # --- Simulate exit on 1m bars ---
            start = entry_idx
            if start >= len(timestamp_ns):
                break

            if direction == "long":
                stop_hits = np.flatnonzero(low[start:] <= stop_level)
                tp_hits = np.flatnonzero(high[start:] >= tp_level)
            else:
                stop_hits = np.flatnonzero(high[start:] >= stop_level)
                tp_hits = np.flatnonzero(low[start:] <= tp_level)

            stop_idx = (start + int(stop_hits[0])) if stop_hits.size else None
            tp_idx = (start + int(tp_hits[0])) if tp_hits.size else None

            exit_reason = "end_of_data"
            if stop_idx is None and tp_idx is None:
                exit_idx = len(timestamp_ns) - 1
                exit_price = float(close[exit_idx])
            elif stop_idx is not None and tp_idx is None:
                exit_idx = stop_idx
                exit_price = float(stop_level)
                exit_reason = "bb_middle_stop"
            elif stop_idx is None and tp_idx is not None:
                exit_idx = tp_idx
                exit_price = float(tp_level)
                exit_reason = "take_profit_rr"
            else:
                # Both exist; choose earliest, break ties by conflict resolution.
                assert stop_idx is not None and tp_idx is not None
                if stop_idx < tp_idx:
                    exit_idx = stop_idx
                    exit_price = float(stop_level)
                    exit_reason = "bb_middle_stop"
                elif tp_idx < stop_idx:
                    exit_idx = tp_idx
                    exit_price = float(tp_level)
                    exit_reason = "take_profit_rr"
                else:
                    exit_idx = stop_idx
                    if conflict_resolution == "stop_first":
                        exit_price = float(stop_level)
                        exit_reason = "bb_middle_stop"
                    else:
                        exit_price = float(tp_level)
                        exit_reason = "take_profit_rr"

            exit_time = pd.to_datetime(timestamp_ns[int(exit_idx)], utc=True)

            raw_pnl, fees, net_pnl = calculate_pnl_with_fees(
                entry_price=entry_price,
                exit_price=float(exit_price),
                size=1.0,
                direction=direction_int,
                fee_rate=context.fee_rate,
            )

            trades_out.append(
                {
                    "symbol": context.symbol,
                    "strategy_id": self.strategy_id,
                    "signal_time": signal_time,
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "direction": direction,
                    "entry_price": entry_price,
                    "exit_price": float(exit_price),
                    "stop_level": float(stop_level),
                    "tp_level": float(tp_level),
                    "raw_pnl": float(raw_pnl),
                    "fees": float(fees),
                    "net_pnl": float(net_pnl),
                    "exit_reason": exit_reason,
                }
            )

            # Ignore signals while in trade: jump hourly cursor to the first bar strictly AFTER exit_time.
            # Use side='right' to guarantee progress if exit_time equals an hourly bar open.
            next_i = int(hourly_ts.searchsorted(pd.to_datetime(exit_time, utc=True), side="right"))
            i = max(i + 1, next_i)

        trades_df = pd.DataFrame(trades_out)
        if trades_df.empty:
            trades_df = pd.DataFrame(columns=empty_cols)

        # Ensure required columns exist (tp_level etc.)
        for col in ("stop_level", "tp_level"):
            if col not in trades_df.columns:
                trades_df[col] = pd.NA

        # Validate schema for downstream portfolio/reporting
        validate_trades_df(trades_df)
        return trades_df
