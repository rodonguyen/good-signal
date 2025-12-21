"""
Fee and PnL utilities for backtesting.

Model:
- `fee_rate` is a TOTAL round-trip fee rate applied to (entry_notional + exit_notional).
  Example: fee_rate=0.003 means fees = 0.3% * (entry_notional + exit_notional).
"""

from __future__ import annotations

from typing import Literal, Tuple

DirectionInt = Literal[1, -1]


def calculate_round_trip_fees(*, entry_price: float, exit_price: float, size: float, fee_rate: float) -> float:
    notional_entry = entry_price * size
    notional_exit = exit_price * size
    return (notional_entry + notional_exit) * fee_rate


def calculate_pnl_with_fees(
    *,
    entry_price: float,
    exit_price: float,
    size: float,
    direction: DirectionInt,
    fee_rate: float,
) -> Tuple[float, float, float]:
    """
    Returns: (raw_pnl, fees, net_pnl)
    """
    raw_pnl = (exit_price - entry_price) * direction * size
    fees = calculate_round_trip_fees(entry_price=entry_price, exit_price=exit_price, size=size, fee_rate=fee_rate)
    net_pnl = raw_pnl - fees
    return raw_pnl, fees, net_pnl


