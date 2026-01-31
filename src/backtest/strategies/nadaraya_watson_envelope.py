"""
Backtest strategy: Nadaraya-Watson Envelope mean-reversion strategy.

Rules (matching the LuxAlgo Pine Script logic):
- Compute NW kernel regression + MAE envelope on signal_timeframe bars.
- SELL signal: price crosses from below to above the upper envelope.
- BUY signal:  price crosses from below to above... no — price crosses
  from above to below the lower envelope.

More precisely (Pine Script logic):
  - SELL (▼): src[i] > upper[i]  AND  src[i+1] < upper[i+1]
      i.e. price just pierced above the upper band (look-back cross).
  - BUY  (▲): src[i] < lower[i]  AND  src[i+1] > lower[i+1]
      i.e. price just pierced below the lower band.

Entry: at the close of the signal bar (or next bar open).
Exit:  price crosses the NW smooth (middle) line, acting as a mean-reversion target,
       OR a fixed stop loss at `stop_mult × MAE` beyond the envelope.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.backtest.contracts import BaseBacktestStrategy, BacktestContext, validate_trades_df
from src.backtest.utils.fee_utils import calculate_pnl_with_fees
from src.backtest.utils.resample_utils import ensure_utc_timestamp
from src.indicators.nadaraya_watson import NadarayaWatsonEnvelope


class NadarayaWatsonEnvelopeStrategy(BaseBacktestStrategy):
    """Nadaraya-Watson Envelope mean-reversion backtest strategy."""

    @property
    def strategy_id(self) -> str:
        return "nw_envelope"

    def generate_trades(
        self,
        minute_df: pd.DataFrame,
        *,
        context: BacktestContext,
        params: Mapping[str, Any],
    ) -> pd.DataFrame:
        minute_df = ensure_utc_timestamp(minute_df, "timestamp").sort_values("timestamp").reset_index(drop=True)

        empty_cols = [
            "symbol", "strategy_id", "entry_time", "exit_time",
            "direction", "entry_price", "exit_price",
            "stop_level", "tp_level", "raw_pnl", "fees", "net_pnl", "exit_reason",
        ]

        if minute_df.empty:
            return pd.DataFrame(columns=empty_cols)

        # Parameters
        window = int(params.get("window", 500))
        bandwidth = float(params.get("bandwidth", 8.0))
        mult = float(params.get("mult", 3.0))
        stop_mult = float(params.get("stop_mult", 1.5))  # stop at stop_mult × envelope width beyond entry
        signal_timeframe = params.get("signal_timeframe", "1h")
        filter_pipeline = params.get("filter_pipeline")
        debug = bool(params.get("debug", False))

        # Resample to signal timeframe
        if "_signal_bars" in params and params["_signal_bars"] is not None:
            sig_df = params["_signal_bars"].copy()
        else:
            sig_df = self._resample_to_timeframe(minute_df, signal_timeframe)

        if len(sig_df) < window:
            if debug:
                print(f"NW Envelope: not enough bars ({len(sig_df)}) for window={window}")
            return pd.DataFrame(columns=empty_cols)

        # Calculate indicator
        indicator = NadarayaWatsonEnvelope(window=window, bandwidth=bandwidth, mult=mult)
        sig_df = indicator.calculate(sig_df)
        sig_df = sig_df.dropna(subset=["nw_upper", "nw_lower", "nw_smooth"]).reset_index(drop=True)

        if len(sig_df) < 2:
            return pd.DataFrame(columns=empty_cols)

        # Pre-extract arrays for signal detection
        close = sig_df["close"].values
        upper = sig_df["nw_upper"].values
        lower = sig_df["nw_lower"].values
        smooth = sig_df["nw_smooth"].values
        timestamps = sig_df["timestamp"].values

        # For 1m execution: pre-extract numpy arrays
        ts_1m = minute_df["timestamp"].values.astype("int64")
        open_1m = minute_df["open"].values
        high_1m = minute_df["high"].values
        low_1m = minute_df["low"].values
        close_1m = minute_df["close"].values

        trades_out: list[dict[str, Any]] = []

        i = 1
        while i < len(sig_df) - 1:
            # Pine Script crossover: both bars compared against the SAME envelope level.
            # Pine uses y[i-1] for both; non-repainting equivalent uses current bar's level.
            # SELL: close crosses above upper  (close[i] > upper[i] and close[i-1] < upper[i])
            # BUY:  close crosses below lower  (close[i] < lower[i] and close[i-1] > lower[i])
            sell_signal = close[i] > upper[i] and close[i - 1] < upper[i]
            buy_signal = close[i] < lower[i] and close[i - 1] > lower[i]

            if not sell_signal and not buy_signal:
                i += 1
                continue

            trade_direction = "short" if sell_signal else "long"

            # Check filter
            if filter_pipeline is not None:
                if not filter_pipeline.is_allowed(sig_df, i, trade_direction):
                    i += 1
                    continue

            # Entry: next 1m bar after signal bar timestamp
            signal_ts = pd.Timestamp(timestamps[i]).value
            entry_1m_idx = int(np.searchsorted(ts_1m, signal_ts, side="right"))
            if entry_1m_idx >= len(open_1m):
                i += 1
                continue

            entry_price = float(open_1m[entry_1m_idx])
            entry_time = pd.Timestamp(ts_1m[entry_1m_idx], unit="ns")

            # Calculate stop and TP
            # MAE band width = upper - smooth (same as smooth - lower)
            band_width = float(upper[i] - smooth[i])
            direction_int = 1 if trade_direction == "long" else -1

            if trade_direction == "long":
                # Mean-reversion: target is the smooth line
                tp_level = float(smooth[i])
                stop_level = entry_price - stop_mult * band_width
            else:
                tp_level = float(smooth[i])
                stop_level = entry_price + stop_mult * band_width

            # Scan 1m bars for exit
            # Find the timestamp of the last signal bar in our window to limit scan
            last_sig_ts = pd.Timestamp(timestamps[-1]).value
            end_1m_idx = int(np.searchsorted(ts_1m, last_sig_ts, side="right"))
            end_1m_idx = min(end_1m_idx, len(open_1m))

            exit_price = None
            exit_time = None
            exit_reason = None

            for k in range(entry_1m_idx + 1, end_1m_idx):
                h = float(high_1m[k])
                l = float(low_1m[k])

                if trade_direction == "long":
                    # Check stop first
                    if l <= stop_level:
                        exit_price = stop_level
                        exit_time = pd.Timestamp(ts_1m[k], unit="ns")
                        exit_reason = "stop_loss"
                        break
                    # Check TP (mean reversion to smooth)
                    if h >= tp_level:
                        exit_price = tp_level
                        exit_time = pd.Timestamp(ts_1m[k], unit="ns")
                        exit_reason = "take_profit"
                        break
                else:  # short
                    if h >= stop_level:
                        exit_price = stop_level
                        exit_time = pd.Timestamp(ts_1m[k], unit="ns")
                        exit_reason = "stop_loss"
                        break
                    if l <= tp_level:
                        exit_price = tp_level
                        exit_time = pd.Timestamp(ts_1m[k], unit="ns")
                        exit_reason = "take_profit"
                        break

            # If no exit found, close at last available bar
            if exit_price is None:
                last_idx = end_1m_idx - 1 if end_1m_idx > entry_1m_idx else entry_1m_idx
                exit_price = float(close_1m[last_idx])
                exit_time = pd.Timestamp(ts_1m[last_idx], unit="ns")
                exit_reason = "end_of_data"

            # PnL
            size = 1.0
            raw_pnl, fees, net_pnl = calculate_pnl_with_fees(
                entry_price=entry_price,
                exit_price=exit_price,
                size=size,
                direction=direction_int,
                fee_rate=context.fee_rate,
            )

            trades_out.append({
                "symbol": context.symbol,
                "strategy_id": self.strategy_id,
                "entry_time": entry_time,
                "exit_time": exit_time,
                "direction": trade_direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "stop_level": stop_level,
                "tp_level": tp_level,
                "raw_pnl": raw_pnl,
                "fees": fees,
                "net_pnl": net_pnl,
                "exit_reason": exit_reason,
            })

            if debug:
                print(
                    f"NW Trade: {trade_direction} @ {entry_price:.2f} ({entry_time}) -> "
                    f"{exit_price:.2f} ({exit_time}), PnL: {net_pnl:.2f}, Reason: {exit_reason}"
                )

            # Skip past exit on signal bars
            if exit_time is not None:
                exit_ns = exit_time.value if hasattr(exit_time, 'value') else pd.Timestamp(exit_time).value
                sig_ts_arr = np.array([pd.Timestamp(t).value for t in timestamps])
                next_i = int(np.searchsorted(sig_ts_arr, exit_ns, side="right"))
                i = max(i + 1, next_i)
            else:
                i += 1

        if not trades_out:
            if debug:
                print("NW Envelope: No trades generated")
            return pd.DataFrame(columns=empty_cols)

        trades_df = pd.DataFrame(trades_out)
        validate_trades_df(trades_df)

        if debug:
            print(f"NW Envelope: Generated {len(trades_df)} trades")

        return trades_df

    def _resample_to_timeframe(self, minute_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        df = minute_df.copy()
        df = df.set_index("timestamp")
        resampled = df.resample(timeframe).agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        resampled = resampled.dropna()
        resampled = resampled.reset_index()
        return resampled
