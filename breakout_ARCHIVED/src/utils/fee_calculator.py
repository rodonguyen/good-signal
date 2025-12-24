"""Fee calculation utilities for crypto trading."""

from typing import Literal


def calculate_crypto_fees(
    entry_price: float,
    exit_price: float,
    size: float,
    fee_rate: float = 0.0015
) -> float:
    """Calculate total fees for a crypto trade.
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        size: Position size (contracts/units)
        fee_rate: Total fee rate (default: 0.0015 = 0.15%)
        
    Returns:
        Total fee amount
    """
    # Fee is 0.15% of notional value (entry + exit)
    notional_entry = entry_price * size
    notional_exit = exit_price * size
    total_notional = notional_entry + notional_exit
    
    return total_notional * fee_rate


def apply_fees_to_pnl(
    raw_pnl: float,
    entry_price: float,
    exit_price: float,
    size: float,
    direction: Literal[1, -1],
    fee_rate: float = 0.0015
) -> float:
    """Calculate net PnL after fees.
    
    Args:
        raw_pnl: Raw PnL before fees
        entry_price: Entry price
        exit_price: Exit price
        size: Position size
        direction: 1 for long, -1 for short
        fee_rate: Total fee rate (default: 0.0015)
        
    Returns:
        Net PnL after fees
    """
    fees = calculate_crypto_fees(entry_price, exit_price, size, fee_rate)
    return raw_pnl - fees


def calculate_pnl_with_fees(
    entry_price: float,
    exit_price: float,
    size: float,
    direction: Literal[1, -1],
    fee_rate: float = 0.0015
) -> float:
    """Calculate PnL including fees in one step.
    
    Args:
        entry_price: Entry price
        exit_price: Exit price
        size: Position size
        direction: 1 for long, -1 for short
        fee_rate: Total fee rate (default: 0.0015)
        
    Returns:
        Net PnL after fees
    """
    # Raw PnL
    price_diff = exit_price - entry_price
    raw_pnl = price_diff * direction * size
    
    # Apply fees
    return apply_fees_to_pnl(raw_pnl, entry_price, exit_price, size, direction, fee_rate)



