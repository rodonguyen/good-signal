# Breakout Mechanism - Detailed Explanation

## Overview

The breakout strategy uses **1-minute bars** to detect when price crosses predefined breakout levels. Trades are triggered immediately when a breakout is detected.

## Step-by-Step Process

### 1. Setting Breakout Levels (At 13:00 UTC)

At the start of each trading day (13:00 UTC), breakout levels are calculated using:

```
Upper Level = Previous Day Close + (k × Previous Day ATR)
Lower Level = Previous Day Close - (k × Previous Day ATR)
```

Where:
- **Previous Day Close**: Price at 13:00 UTC of the previous day
- **Previous Day ATR**: Average True Range calculated over last 14 periods (14 × 24-hour periods)
- **k (breakout_multiplier)**: Default = 0.33

**Example from actual trade:**
- Previous Close: 3136.11
- Previous ATR: 105.97
- Breakout Multiplier: 0.33
- **Upper Level**: 3136.11 + (0.33 × 105.97) = **3171.08**
- **Lower Level**: 3136.11 - (0.33 × 105.97) = **3101.14**

### 2. Monitoring Period (24-Hour Window)

The system monitors for breakouts during the **entire 24-hour period**:
- **Start**: 13:00 UTC (e.g., Dec 9, 2025 13:00:00)
- **End**: Next day 13:00 UTC (e.g., Dec 10, 2025 13:00:00)

### 3. Breakout Detection (1-Minute Bars)

The system checks **each 1-minute bar sequentially** during the trading day:

```python
for each 1-minute bar in the trading day:
    # Check for upper breakout (LONG)
    if bar['high'] >= upper_level:
        → Enter LONG at upper_level price
        → Entry time = this bar's timestamp
    
    # Check for lower breakout (SHORT)
    if bar['low'] <= lower_level:
        → Enter SHORT at lower_level price
        → Entry time = this bar's timestamp
```

**Key Points:**
- **Timeframe**: 1-minute bars (not tick data, not 5-minute, not hourly)
- **Trigger Condition**: Price **touches or crosses** the breakout level
- **Entry Price**: Always at the breakout level itself (not the bar's open/close)
- **First Breakout Wins**: Only the **first** breakout of the day triggers a trade

### 4. Entry Execution

When a breakout is detected:

**For LONG (Upper Breakout):**
- Entry triggered when: `1-minute bar high >= upper_level`
- Entry price: `upper_level` (exact breakout level)
- Entry time: Timestamp of the 1-minute bar that triggered it

**For SHORT (Lower Breakout):**
- Entry triggered when: `1-minute bar low <= lower_level`
- Entry price: `lower_level` (exact breakout level)
- Entry time: Timestamp of the 1-minute bar that triggered it

**Example from Trade #1:**
```
Day: 2025-12-09
Upper Level: 3171.08
Lower Level: 3101.14

At 14:25:00 UTC, a 1-minute bar had:
- Low: <= 3101.14 (lower level)
→ SHORT entry triggered
→ Entry Price: 3101.14 (exact lower level)
→ Entry Time: 2025-12-09 14:25:00 UTC
```

### 5. Stop Loss Calculation

After entry, stop loss is set:

**For LONG:**
```
Stop Level = Entry Price - (stop_multiplier × ATR)
```

**For SHORT:**
```
Stop Level = Entry Price + (stop_multiplier × ATR)
```

Where `stop_multiplier` = 0.33 (default)

**Example from Trade #1:**
- Entry: 3101.14 (SHORT)
- ATR: 105.97
- Stop Multiplier: 0.33
- **Stop Level**: 3101.14 + (0.33 × 105.97) = **3136.11**

### 6. Exit Conditions

The trade exits when one of these occurs (checked in order):

1. **Stop Loss Hit** (checked first):
   - For LONG: If any 1-minute bar's `low <= stop_level`
   - For SHORT: If any 1-minute bar's `high >= stop_level`
   - Exit price: Stop level
   - Exit reason: `stop_loss`

2. **End of Day** (if stop not hit):
   - At exactly **13:00 UTC next day**
   - Exit price: Close price of the 1-minute bar at 13:00 UTC
   - Exit reason: `end_of_day`
   - **Mandatory**: All trades must exit at 13:00 UTC if still open

**Example from Trade #3:**
```
Entry: 2025-12-12 15:26:00 UTC (SHORT at 3178.46)
Stop Level: 3246.14
End of Day: 2025-12-13 13:00:00 UTC

Result: Stop was NOT hit, so exited at end_of_day
Exit Price: 3114.69 (close at 13:00 UTC)
Exit Reason: end_of_day
```

## Timeline Example

Let's trace through a complete example:

### Day Setup (Dec 9, 2025 at 13:00 UTC)
```
Previous Day (Dec 8) Close: 3136.11
Previous Day ATR: 105.97
Breakout Multiplier: 0.33

Upper Level: 3136.11 + (0.33 × 105.97) = 3171.08
Lower Level: 3136.11 - (0.33 × 105.97) = 3101.14
```

### Monitoring (Dec 9, 13:00 UTC → Dec 10, 13:00 UTC)

**13:00 UTC** - Day starts, levels set, monitoring begins

**14:00 UTC** - Check 1-minute bars:
- Bar high: 3120.50 (below upper 3171.08) ✓
- Bar low: 3115.20 (above lower 3101.14) ✓
- No breakout

**14:25 UTC** - Check 1-minute bar:
- Bar high: 3105.00
- **Bar low: 3098.00 (≤ 3101.14)** ← **BREAKOUT DETECTED!**
- **SHORT entry triggered**
- Entry Price: 3101.14 (exact lower level)
- Entry Time: 2025-12-09 14:25:00 UTC

**14:26 UTC** - Stop loss set:
- Stop Level: 3101.14 + (0.33 × 105.97) = 3136.11

**15:02 UTC** - Check 1-minute bars:
- **Bar high: 3138.50 (≥ 3136.11)** ← **STOP HIT!**
- Exit Price: 3136.11 (stop level)
- Exit Time: 2025-12-09 15:02:00 UTC
- Exit Reason: stop_loss

## Key Characteristics

### Timeframe Used
- **Detection**: 1-minute bars
- **Entry Trigger**: When 1-minute bar touches/crosses level
- **Exit Monitoring**: 1-minute bars (for stop loss)
- **Exit Time**: 1-minute bar at 13:00 UTC (for end of day)

### Breakout Logic
- **Sequential Scanning**: Checks each 1-minute bar in chronological order
- **First Breakout Wins**: Only first breakout of the day triggers trade
- **One Trade Per Day**: Maximum one breakout attempt per trading day
- **No Re-entry**: If trade exits early (stop loss), no new entry that day

### Entry Price Logic
- **Always at Level**: Entry is at the exact breakout level, not the bar's open/close
- **Rationale**: Assumes you can enter at the level when price touches it
- **No Slippage Model**: Currently uses exact level price (can be enhanced)

### Exit Priority
1. **Stop Loss** (checked first on each bar)
2. **End of Day** (mandatory at 13:00 UTC if still open)

## Visual Example

```
Price Chart (1-minute bars):

Upper Level: 3171.08 ────────────────────────────────
                    │
                    │  [Bar touches upper] → LONG entry
                    │
Previous Close: 3136.11 ─────────────────────────────
                    │
                    │  [Bar touches lower] → SHORT entry
                    │
Lower Level: 3101.14 ────────────────────────────────

Day Start: 13:00 UTC          Day End: Next 13:00 UTC
│                              │
├──────────────────────────────┤
    24-hour monitoring window
```

## Code Reference

The breakout detection happens in `src/breakout_engine.py`:

```python
def detect_breakout(self, minute_bars, upper_level, lower_level, day_start, day_end):
    # Filter 1-minute bars for this trading day
    day_bars = minute_bars[(minute_bars['timestamp'] >= day_start) & 
                           (minute_bars['timestamp'] < day_end)]
    
    # Check each 1-minute bar sequentially
    for idx, row in day_bars.iterrows():
        # Upper breakout (LONG)
        if row['high'] >= upper_level:
            return {
                'direction': 1,  # Long
                'entry_time': row['timestamp'],
                'entry_price': upper_level  # Exact level
            }
        
        # Lower breakout (SHORT)
        if row['low'] <= lower_level:
            return {
                'direction': -1,  # Short
                'entry_time': row['timestamp'],
                'entry_price': lower_level  # Exact level
            }
    
    return None  # No breakout
```

## Summary

- **Timeframe**: 1-minute bars for both detection and monitoring
- **Trigger**: When 1-minute bar's high/low touches/crosses breakout level
- **Entry**: At exact breakout level price, timestamp of triggering bar
- **Exit**: Stop loss (checked on each bar) or end of day (13:00 UTC mandatory)
- **Frequency**: Maximum one trade per 24-hour period

