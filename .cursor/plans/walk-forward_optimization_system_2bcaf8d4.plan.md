---
name: Walk-Forward Optimization System
overview: Implement a walk-forward optimization framework that tests parameter combinations across rolling 6-month training windows, selects best configs by Sharpe ratio, validates on 3-month test periods, and generates comprehensive HTML reports with scatter plots and performance metrics.
todos:
  - id: create-optimization-module
    content: Create src/backtest/optimization/ directory structure with __init__.py
    status: pending
  - id: implement-metrics
    content: Implement metrics.py with Sharpe, drawdown, win rate, and return calculations
    status: pending
    dependencies:
      - create-optimization-module
  - id: implement-grid-search
    content: Implement grid_search.py to generate 342 parameter combinations (breakout_mult 0.24-0.60, stop_mult 0.16-0.50)
    status: pending
    dependencies:
      - create-optimization-module
  - id: implement-wfo-config
    content: Implement wfo_config.py with date window calculation (6-month train, 3-month test, 3-month step)
    status: pending
    dependencies:
      - create-optimization-module
  - id: implement-walk-forward
    content: Implement walk_forward.py with WalkForwardOptimizer class that runs grid search per cycle and selects best config by Sharpe
    status: pending
    dependencies:
      - implement-metrics
      - implement-grid-search
      - implement-wfo-config
  - id: implement-wfo-report
    content: Implement wfo_report.py with HTML report generator including scatter plots (color=Sharpe, size=PnL), summary section, and per-cycle layouts
    status: pending
    dependencies:
      - implement-walk-forward
  - id: create-entry-point
    content: Create wfo.py entry point script for running walk-forward optimization
    status: pending
    dependencies:
      - implement-wfo-report
  - id: add-parameter-stability
    content: Add parameter stability heatmap and best config frequency analysis to report
    status: pending
    dependencies:
      - implement-wfo-report
  - id: add-robustness-analysis
    content: Add top 10% robustness zone visualization to scatter plots
    status: pending
    dependencies:
      - implement-wfo-report
  - id: add-combined-oos-curve
    content: Add combined out-of-sample equity curve stitching all test periods together
    status: pending
    dependencies:
      - implement-wfo-report
---

# Walk-Forward Optimization Implementation Plan

## Overview

Build a walk-forward optimization (WFO) system that:

- Tests 342 parameter combinations (breakout_mult: 0.24-0.60, stop_mult: 0.16-0.50) per training window
- Uses rolling 6-month training / 3-month testing windows with 3-month step forward
- Optimizes by Sharpe Ratio (color), with PnL as size in scatter plots
- Generates comprehensive HTML reports with per-cycle analysis and aggregate metrics

## Architecture

```
src/backtest/optimization/
├── __init__.py
├── walk_forward.py          # Main WFO orchestrator
├── grid_search.py            # Parameter grid generation & iteration
├── metrics.py                # Performance metrics (Sharpe, drawdown, etc.)
├── wfo_report.py             # HTML report generator
└── wfo_config.py             # WFO-specific configuration
```

## Implementation Details

### 1. Grid Search Module (`grid_search.py`)

**Purpose**: Generate and iterate through parameter combinations

**Key Components**:

- `ParameterGrid` class to generate all combinations
- Iterator pattern for efficient memory usage
- Range: breakout_mult [0.24, 0.60] step 0.02, stop_mult [0.16, 0.50] step 0.02

**Functions**:

```python
def generate_parameter_grid(
    breakout_range: tuple[float, float, float],  # (start, end, step)
    stop_range: tuple[float, float, float]
) -> list[dict[str, float]]
```

### 2. Metrics Module (`metrics.py`)

**Purpose**: Calculate performance metrics from trades/equity curves

**Key Functions**:

- `calculate_sharpe_ratio(equity_curve: pd.Series, risk_free_rate: float = 0.0) -> float`
- `calculate_max_drawdown(equity_curve: pd.Series) -> float`
- `calculate_win_rate(trades_df: pd.DataFrame) -> float`
- `calculate_avg_win_loss(trades_df: pd.DataFrame) -> tuple[float, float]`
- `calculate_annualized_return(equity_curve: pd.Series, initial_capital: float) -> float`
- `calculate_total_return(equity_curve: pd.Series, initial_capital: float) -> float`

**Note**: Reuse existing logic from `src/backtest/steps/portfolio.py` where possible

### 3. Walk-Forward Orchestrator (`walk_forward.py`)

**Purpose**: Main WFO execution engine

**Key Class**: `WalkForwardOptimizer`

**Methods**:

- `**init**(config: BacktestConfig, strategy_type: str, date_ranges: list[tuple])`
- `run_cycle(train_start: datetime, train_end: datetime, test_start: datetime, test_end: datetime) -> CycleResult`
- `run_all_cycles() -> list[CycleResult]`
- `_run_single_backtest(params: dict, start: datetime, end: datetime) -> BacktestResult`

**Data Structures**:

```python
@dataclass
class BacktestResult:
    params: dict[str, float]
    trades_df: pd.DataFrame
    equity_curve: pd.Series
    sharpe: float
    total_pnl: float
    max_drawdown: float
    # ... other metrics

@dataclass
class CycleResult:
    cycle_num: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    grid_results: list[BacktestResult]  # All 342 configs
    best_config: BacktestResult
    test_result: BacktestResult  # OOS result with best config
```

**Integration Points**:

- Reuse `BacktestRunner` logic but extract strategy execution into callable function
- Filter data by date range before passing to strategy
- Use existing `PortfolioBuilder` for position sizing and equity curve calculation

### 4. Report Generator (`wfo_report.py`)

**Purpose**: Generate comprehensive HTML report with interactive visualizations

**Key Class**: `WFOReportGenerator`

**Methods**:

- `generate_report(cycle_results: list[CycleResult], output_path: Path) -> Path`
- `_generate_summary_section(cycle_results: list[CycleResult]) -> str`
- `_generate_cycle_section(cycle_result: CycleResult) -> str`
- `_generate_scatter_plot_data(cycle_result: CycleResult) -> dict`
- `_generate_parameter_stability_heatmap(cycle_results: list[CycleResult]) -> dict`
- `_generate_combined_oos_equity_curve(cycle_results: list[CycleResult]) -> dict`

**Report Structure**:

- Summary section: Combined OOS equity curve, aggregate metrics, parameter stability heatmap, best config frequency table
- Per-cycle sections: Scatter plot (left) + metrics table (right)
- Appendix: Full grid search results table (sortable)

**Visualization Libraries**:

- Plotly.js for interactive scatter plots and charts
- DataTables.js for sortable tables
- Custom CSS for responsive layout

**Scatter Plot Specs**:

- X: breakout_multiplier
- Y: stop_multiplier  
- Color: Sharpe Ratio (yellow → red gradient)
- Size: Absolute PnL (1-2 range, scaled)
- Marker: ★ for best config, ○ border for top 10%

### 5. Configuration (`wfo_config.py`)

**Purpose**: WFO-specific configuration schema

**Key Components**:

- Date range calculation (rolling windows with 3-month step)
- Parameter grid definition
- Optimization target (Sharpe)
- Report output paths

**Date Window Calculation**:

```python
def calculate_wfo_windows(
    data_start: datetime,
    data_end: datetime,
    train_months: int = 6,
    test_months: int = 3,
    step_months: int = 3
) -> list[tuple[datetime, datetime, datetime, datetime]]
```

### 6. Entry Point Integration

**Option A**: New standalone script `wfo.py`

**Option B**: Extend `backtest.py` with `--mode wfo` flag

**Recommended**: Option A for cleaner separation

**Usage**:

```bash
python wfo.py --config config/backtest/backtest.yaml --strategy atr_breakout
```

## Data Flow

```
1. Load config → BacktestConfig
2. Calculate date windows → list[(train_start, train_end, test_start, test_end)]
3. For each cycle:
   a. Generate parameter grid → 342 combinations
   b. For each combination:
                                                                                                                                                                                                                                                   - Filter data to train period
                                                                                                                                                                                                                                                   - Run backtest with params
                                                                                                                                                                                                                                                   - Calculate metrics (Sharpe, PnL, etc.)
   c. Select best config (max Sharpe)
   d. Run test period with best config
   e. Store CycleResult
4. Generate HTML report from all CycleResult objects
```

## Files to Create

1. `src/backtest/optimization/__init__.py`
2. `src/backtest/optimization/grid_search.py`
3. `src/backtest/optimization/metrics.py`
4. `src/backtest/optimization/walk_forward.py`
5. `src/backtest/optimization/wfo_report.py`
6. `src/backtest/optimization/wfo_config.py`
7. `wfo.py` (entry point)

## Files to Modify

1. `src/backtest/runner.py` - Extract reusable backtest execution logic (optional, for cleaner separation)

## Key Dependencies

- Existing: `BacktestRunner`, `AtrBreakoutStrategy`, `PortfolioBuilder`, `OhlcvStore`
- New: Plotly.js (via CDN in HTML), DataTables.js (via CDN)

## Testing Considerations

- Unit tests for metrics calculations
- Unit tests for date window calculation
- Integration test with small parameter grid (2-3 combinations)
- Validate scatter plot data structure

## Performance Optimizations

- Cache resampled data (already exists in `OhlcvStore`)
- Parallelize grid search (optional, use `multiprocessing` for 342 runs)
- Progress bars for long-running operations
- Save intermediate results (JSON) to allow resume from interruption

## Output Structure

```
outputs/reports/wfo_atr_breakout/
├── wfo_report.html
├── data/
│   ├── cycle_1_grid.json
│   ├── cycle_2_grid.json
│   ├── ...
│   ├── oos_equity_curve.json
│   └── summary_stats.json
└── charts/  # Optional: static fallback images
    ├── cycle_1_scatter.png
    └── ...
```

## Implementation Order

1. **Phase 1**: Core infrastructure

                                                                                                                                                                                                                                                                                                                                                                                                - `metrics.py` - Metrics calculation
                                                                                                                                                                                                                                                                                                                                                                                                - `grid_search.py` - Parameter grid generation
                                                                                                                                                                                                                                                                                                                                                                                                - `wfo_config.py` - Date window calculation

2. **Phase 2**: WFO engine

                                                                                                                                                                                                                                                                                                                                                                                                - `walk_forward.py` - Main orchestrator
                                                                                                                                                                                                                                                                                                                                                                                                - Integration with existing backtest components

3. **Phase 3**: Reporting

                                                                                                                                                                                                                                                                                                                                                                                                - `wfo_report.py` - HTML report generation
                                                                                                                                                                                                                                                                                                                                                                                                - Scatter plot generation
                                                                                                                                                                                                                                                                                                                                                                                                - Summary statistics

4. **Phase 4**: Entry point & polish

                                                                                                                                                                                                                                                                                                                                                                                                - `wfo.py` - CLI interface
                                                                                                                                                                                                                                                                                                                                                                                                - Error handling
                                                                                                                                                                                                                                                                                                                                                                                                - Progress indicators