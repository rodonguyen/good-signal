# Good Signal - Fullstack Trading Application Plan

## Executive Summary

Transform the existing CLI-based trading system into a production-grade fullstack application with FastAPI backend, React frontend, SQLite persistence, and automated live trading via Bybit API.

---

## Confirmed Requirements

| Category | Decision |
|----------|----------|
| Backend | FastAPI (in `/backend` directory) |
| Frontend | React + Vite + TailwindCSS + shadcn/ui (in `/frontend` directory) |
| Database | SQLite |
| Charts | TradingView lightweight-charts |
| Authentication | Local-only (no auth required) |
| Backtest Execution | Background task queue with configurable concurrent workers |
| Live Trading | Full automation via Bybit API |
| Position Monitoring | Polling + WebSocket hybrid |
| Risk Management | Full controls (kill switch, daily loss limit, max positions, max exposure) |
| Multi-symbol | Yes, managed independently |

---

## Project Structure

```
E:\Personal\GitHub\good-signal/
├── src/                             # [EXISTING] Core trading logic (unchanged)
│   ├── backtest/                    # Backtesting framework
│   ├── strategies/                  # Live signal strategies
│   ├── indicators/                  # Technical indicators
│   ├── notifiers/                   # Discord notifier
│   └── data/                        # Bybit fetcher
│
├── backend/                         # [NEW] FastAPI backend
│   ├── __init__.py
│   ├── main.py                      # FastAPI app entry + lifespan
│   ├── config.py                    # Settings (Pydantic BaseSettings)
│   ├── dependencies.py              # DI container
│   │
│   ├── routers/                     # API route handlers
│   │   ├── __init__.py
│   │   ├── backtest.py
│   │   ├── live_trading.py
│   │   ├── positions.py
│   │   ├── risk.py
│   │   ├── configs.py
│   │   └── websocket.py
│   │
│   ├── schemas/                     # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── backtest.py
│   │   ├── trade.py
│   │   ├── position.py
│   │   ├── config.py
│   │   └── websocket.py
│   │
│   ├── services/                    # Business logic layer
│   │   ├── __init__.py
│   │   ├── backtest_service.py
│   │   ├── live_trading_service.py
│   │   ├── position_service.py
│   │   ├── order_service.py
│   │   ├── risk_service.py
│   │   └── notification_service.py
│   │
│   ├── infrastructure/              # Data access & integrations
│   │   ├── __init__.py
│   │   ├── database/
│   │   │   ├── __init__.py
│   │   │   ├── connection.py        # SQLite async connection
│   │   │   ├── models.py            # SQLAlchemy ORM models
│   │   │   └── repositories/        # Data access layer
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── backtest_repo.py
│   │   │       ├── position_repo.py
│   │   │       ├── trade_repo.py
│   │   │       └── config_repo.py
│   │   ├── exchange/
│   │   │   ├── __init__.py
│   │   │   ├── base.py              # Abstract exchange interface
│   │   │   └── bybit_client.py      # REST + WS + Orders
│   │   └── queue/
│   │       ├── __init__.py
│   │       ├── task_manager.py      # SQLite-backed task queue
│   │       └── worker.py            # Background workers
│   │
│   ├── core/                        # Shared utilities
│   │   ├── __init__.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── constants.py
│   │
│   └── tests/                       # Backend tests
│       ├── __init__.py
│       ├── conftest.py              # Pytest fixtures
│       ├── unit/
│       │   ├── test_backtest_service.py
│       │   ├── test_risk_service.py
│       │   └── test_order_service.py
│       ├── integration/
│       │   ├── test_backtest_api.py
│       │   ├── test_positions_api.py
│       │   └── test_websocket.py
│       └── e2e/
│           └── test_trading_flow.py
│
├── frontend/                        # [NEW] React application (yarn)
│   ├── package.json
│   ├── yarn.lock
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── index.html
│   │
│   ├── src/
│   │   ├── main.tsx                 # Entry point
│   │   ├── App.tsx                  # Root component + router
│   │   │
│   │   ├── api/                     # API client layer
│   │   │   ├── client.ts            # Axios instance
│   │   │   ├── backtest.ts
│   │   │   ├── trading.ts
│   │   │   ├── positions.ts
│   │   │   └── websocket.ts
│   │   │
│   │   ├── components/              # UI components
│   │   │   ├── ui/                  # shadcn/ui components
│   │   │   ├── charts/              # TradingView wrappers
│   │   │   │   ├── CandlestickChart.tsx
│   │   │   │   ├── EquityChart.tsx
│   │   │   │   └── TradeMarkers.tsx
│   │   │   ├── backtest/
│   │   │   │   ├── BacktestForm.tsx
│   │   │   │   ├── BacktestResults.tsx
│   │   │   │   ├── BacktestProgress.tsx
│   │   │   │   └── SavedBacktests.tsx
│   │   │   ├── trading/
│   │   │   │   ├── TradingDashboard.tsx
│   │   │   │   ├── PositionCard.tsx
│   │   │   │   └── RiskControls.tsx
│   │   │   └── common/
│   │   │       ├── Header.tsx
│   │   │       ├── Sidebar.tsx
│   │   │       └── StatusIndicator.tsx
│   │   │
│   │   ├── hooks/                   # Custom hooks
│   │   │   ├── useBacktest.ts
│   │   │   ├── useWebSocket.ts
│   │   │   └── usePositions.ts
│   │   │
│   │   ├── stores/                  # Zustand state stores
│   │   │   ├── backtestStore.ts
│   │   │   ├── tradingStore.ts
│   │   │   └── configStore.ts
│   │   │
│   │   ├── pages/                   # Route pages
│   │   │   ├── BacktestPage.tsx
│   │   │   ├── LiveTradingPage.tsx
│   │   │   ├── PositionsPage.tsx
│   │   │   └── SettingsPage.tsx
│   │   │
│   │   ├── types/                   # TypeScript types
│   │   │   ├── backtest.ts
│   │   │   ├── trading.ts
│   │   │   └── api.ts
│   │   │
│   │   └── lib/                     # Utilities
│   │       ├── formatters.ts
│   │       └── validators.ts
│   │
│   └── tests/                       # Frontend tests
│       ├── setup.ts
│       ├── components/
│       │   └── BacktestForm.test.tsx
│       └── hooks/
│           └── useWebSocket.test.ts
│
├── data/                            # Data storage
│   ├── raw/crypto/                  # [EXISTING] 1-minute CSVs
│   ├── cache/backtest/              # [EXISTING] Parquet cache
│   ├── trades/                      # [EXISTING] Trade CSVs
│   ├── portfolio/                   # [EXISTING] Portfolio trades
│   └── db/                          # [NEW] SQLite database
│       └── good_signal.db
│
├── config/                          # [EXISTING] Configuration files
├── outputs/reports/                 # [EXISTING] HTML reports
├── logs/                            # Log files
│
├── backtest.py                      # [EXISTING] CLI entry
├── wfo.py                           # [EXISTING] WFO CLI
├── main.py                          # [EXISTING] Live trading CLI
├── run_backend.py                   # [NEW] Backend server entry
├── requirements.txt                 # [UPDATED] Add backend deps
└── fullstack-app-plan-complete.md   # [NEW] This plan document
```

---

## Database Schema

### Core Tables

```sql
-- Backtest jobs and results
backtests (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT,              -- pending, running, completed, failed, cancelled
    progress REAL,
    config_json TEXT,
    symbols TEXT,             -- JSON array
    strategies TEXT,          -- JSON array
    filters TEXT,             -- JSON array
    fee_rate, initial_equity, risk_per_trade, start_date, end_date,
    -- Results (populated on completion)
    total_return, sharpe_ratio, max_drawdown, win_rate, profit_factor, total_trades,
    results_json TEXT,
    report_path TEXT,
    created_at, started_at, completed_at, error_message
)

-- Backtest individual trades
backtest_trades (
    id INTEGER PRIMARY KEY,
    backtest_id TEXT FK,
    symbol, strategy_id, direction,
    entry_time, exit_time, entry_price, exit_price, stop_level, tp_level,
    raw_pnl, fees, net_pnl, portfolio_pnl, position_size,
    exit_reason, metadata_json
)

-- Live trading configurations
live_configs (
    id TEXT PRIMARY KEY,
    name TEXT,
    is_active INTEGER,
    symbol, strategy_type, strategy_params, filter_configs,
    initial_equity, risk_per_trade, max_position_size, max_daily_loss, max_open_positions,
    timeframe, fee_rate,
    created_at, updated_at
)

-- Live positions
positions (
    id TEXT PRIMARY KEY,
    config_id TEXT FK,
    symbol, strategy_id, direction, status,
    entry_time, entry_price, entry_order_id,
    quantity, notional_value,
    stop_loss, take_profit,
    exit_time, exit_price, exit_order_id, exit_reason,
    realized_pnl, unrealized_pnl, fees_paid,
    created_at, updated_at
)

-- Live trade history
live_trades (
    id TEXT PRIMARY KEY,
    position_id, config_id, symbol, strategy_id, direction, trade_type,
    order_id, order_type, order_status,
    requested_price, executed_price, quantity, filled_quantity,
    fees, realized_pnl,
    requested_at, executed_at, error_message
)

-- Risk management state (singleton)
risk_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    kill_switch_active, kill_switch_reason, kill_switch_activated_at,
    daily_pnl, daily_trades, daily_reset_date,
    total_open_positions, total_exposure,
    updated_at
)

-- Background task queue
task_queue (
    id TEXT PRIMARY KEY,
    task_type, status, priority,
    payload_json, result_json, error_message,
    worker_id, attempts, max_attempts,
    created_at, started_at, completed_at, scheduled_at
)

-- Saved config templates
saved_configs (id, name, config_type, config_json, created_at, updated_at)
```

---

## API Endpoints

### Backtest
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/backtests` | Create & queue backtest |
| GET | `/api/backtests` | List backtests (paginated) |
| GET | `/api/backtests/{id}` | Get backtest details |
| GET | `/api/backtests/{id}/trades` | Get trades (paginated) |
| DELETE | `/api/backtests/{id}` | Delete backtest |
| POST | `/api/backtests/{id}/cancel` | Cancel running backtest |

### Live Trading
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/live/configs` | Create trading config |
| GET | `/api/live/configs` | List configs |
| PUT | `/api/live/configs/{id}` | Update config |
| DELETE | `/api/live/configs/{id}` | Delete config |
| POST | `/api/live/configs/{id}/start` | Start trading |
| POST | `/api/live/configs/{id}/stop` | Stop trading |

### Positions
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/positions` | List positions |
| GET | `/api/positions/{id}` | Get position details |
| POST | `/api/positions/{id}/close` | Close position |
| PUT | `/api/positions/{id}/stop-loss` | Update SL |
| PUT | `/api/positions/{id}/take-profit` | Update TP |

### Risk Management
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/risk` | Get risk state |
| POST | `/api/risk/kill-switch` | Activate kill switch |
| DELETE | `/api/risk/kill-switch` | Deactivate |
| PUT | `/api/risk/limits` | Update limits |

### Configuration
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/datasets` | List available symbols |
| GET | `/api/strategies` | List strategies |
| GET | `/api/filters` | List filters |

---

## WebSocket Events

```typescript
// Connection: ws://localhost:8000/ws

// Subscribe
{ type: "subscribe", channels: ["backtest", "positions", "trades", "risk"] }

// Server -> Client Events
backtest:progress  { backtest_id, progress, current_symbol, status }
backtest:complete  { backtest_id, status, results?, error? }
position:update    { position_id, symbol, status, unrealized_pnl, current_price }
trade:executed     { trade_id, position_id, symbol, direction, trade_type, price, pnl? }
risk:alert         { alert_type, message, severity, action_taken? }
price:update       { symbol, price, timestamp, change_24h }
```

---

## Risk Management Flow

```
Signal → Kill Switch Check → Daily Loss Check → Position Limit Check
         → Position Size Check → Exposure Check → EXECUTE / REJECT
```

**Controls:**
- Kill switch: Emergency halt all trading, close all positions
- Daily loss limit: Auto-activate kill switch when exceeded
- Max open positions: Reject new entries when limit reached
- Max position size: Reject oversized trades
- Max exposure: Reject if total notional exceeds limit

---

## Frontend Pages

### 1. Backtest Page (`/backtest`)
- **BacktestForm**: Multi-select symbols, strategies, filters, fee/equity/risk settings
- **BacktestProgress**: Progress bar, current symbol/strategy, cancel button
- **BacktestResults**: Stats summary, TradingView candlestick chart with trade markers, equity curve, trades table
- **SavedBacktests**: Sidebar list of previous backtests

### 2. Live Trading Page (`/live`)
- **TradingDashboard**: Active configs, live positions with real-time PnL, recent trades feed
- **CreateConfigForm**: Symbol, strategy, filters, risk settings
- **RiskControlsPanel**: Kill switch, daily PnL, open positions count, exposure

### 3. Positions Page (`/positions`)
- Filter by status/symbol/date
- Position table with detail modal
- Close position, edit SL/TP actions

### 4. Settings Page (`/settings`)
- Risk limits configuration
- Discord webhook settings
- Concurrent backtest workers setting
- Cache management

---

## Integration Strategy

**Principle: Wrap existing modules, don't modify them**

1. **BacktestService** wraps `BacktestRunner` from `src/backtest/runner.py`
   - Add progress callback mechanism
   - Convert JSON API request → YAML config structure

2. **Reuse strategies directly**
   - Factory pattern exists: `_strategy_factory()` in runner.py
   - Expose strategy list via API for frontend selection

3. **Reuse filters directly**
   - `FilterPipeline` and `BaseFilterRule` work as-is
   - Serialize/deserialize filter configs via API

4. **Extend BybitFetcher** (`src/data/bybit_fetcher.py`)
   - Add order execution methods
   - Add WebSocket streaming for positions/prices

5. **Extend DiscordNotifier**
   - Add async support
   - Add trade execution notifications with PnL

---

## Critical Files to Modify/Extend

| File | Modification |
|------|--------------|
| `src/data/bybit_fetcher.py` | Add order execution, WebSocket streams |
| `src/notifiers/discord_notifier.py` | Add async, trade notifications |
| `requirements.txt` | Add FastAPI, SQLAlchemy, uvicorn, websockets |

---

## Key Dependencies to Add

```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
sqlalchemy[asyncio]>=2.0.0
aiosqlite>=0.19.0
websockets>=12.0
pydantic>=2.5.0
python-multipart>=0.0.6
```

Frontend (install via `yarn add`):
```
react react-dom react-router-dom
typescript @types/react @types/react-dom
tailwindcss @tailwindcss/forms postcss autoprefixer
zustand (state management)
lightweight-charts (TradingView)
axios (HTTP client)
```

Frontend dev dependencies (install via `yarn add -D`):
```
vite @vitejs/plugin-react
vitest @testing-library/react @testing-library/jest-dom
msw (mock service worker)
```

shadcn/ui setup:
```bash
cd frontend
yarn dlx shadcn@latest init
yarn dlx shadcn@latest add button card input select table tabs dialog
```

---

## Implementation Phases

### Phase 1: Backend Foundation
- [ ] Set up FastAPI project structure
- [ ] Implement SQLite database with SQLAlchemy async
- [ ] Create repositories and ORM models
- [ ] Implement task queue with configurable workers

### Phase 2: Backtest Feature
- [ ] Implement BacktestService wrapping existing runner
- [ ] Create backtest API endpoints
- [ ] Implement WebSocket for progress updates
- [ ] Store backtest results in SQLite

### Phase 3: Frontend Foundation
- [ ] Set up React + Vite + TailwindCSS + shadcn/ui
- [ ] Create API client layer
- [ ] Implement Zustand stores
- [ ] Build backtest form and results UI
- [ ] Integrate TradingView charts

### Phase 4: Live Trading Core
- [ ] Extend BybitClient with order execution
- [ ] Implement OrderService, PositionService
- [ ] Implement RiskService with kill switch
- [ ] Create live trading API endpoints
- [ ] Build trading dashboard UI

### Phase 5: Integration & Polish
- [ ] Discord notifications for live trades
- [ ] Saved configurations feature
- [ ] Comprehensive error handling
- [ ] WebSocket reconnection logic
- [ ] Performance optimization

---

## Open Questions Resolved

| Question | Answer |
|----------|--------|
| How many concurrent backtests? | Configurable via settings (default: 2) |
| How to track backtest progress? | Progress callback in runner, broadcast via WebSocket |
| How to handle partial fills? | Track filled_quantity vs requested, update position accordingly |
| What happens on kill switch? | Close all positions immediately, halt all new entries |
| How to persist positions during restart? | SQLite positions table, reconcile with exchange on startup |

---

## Testing Plan

### Backend Testing Strategy

**Test Framework**: pytest + pytest-asyncio + httpx (async test client)

#### Unit Tests (`backend/tests/unit/`)
| File | Coverage Target | Key Test Cases |
|------|-----------------|----------------|
| `test_backtest_service.py` | BacktestService | Create backtest, queue task, progress updates, cancel |
| `test_risk_service.py` | RiskService | Kill switch activation, daily loss check, position limits |
| `test_order_service.py` | OrderService | Order execution, partial fills, error handling |
| `test_position_service.py` | PositionService | Open/close position, PnL calculation, SL/TP updates |
| `test_task_manager.py` | TaskManager | Enqueue, claim task, concurrent workers, retry logic |

#### Integration Tests (`backend/tests/integration/`)
| File | Coverage Target | Key Test Cases |
|------|-----------------|----------------|
| `test_backtest_api.py` | `/api/backtests/*` | Create, list, get, delete, cancel via HTTP |
| `test_positions_api.py` | `/api/positions/*` | CRUD operations, close position |
| `test_risk_api.py` | `/api/risk/*` | Kill switch toggle, update limits |
| `test_websocket.py` | WebSocket | Connect, subscribe, receive events |

#### E2E Tests (`backend/tests/e2e/`)
| File | Coverage Target | Key Test Cases |
|------|-----------------|----------------|
| `test_backtest_flow.py` | Full backtest cycle | Create → Progress → Complete → View results |
| `test_trading_flow.py` | Full trading cycle | Config → Start → Signal → Order → Position → Close |

### Frontend Testing Strategy

**Test Framework**: Vitest + React Testing Library + MSW (mock service worker)

#### Component Tests (`frontend/tests/components/`)
| File | Coverage Target | Key Test Cases |
|------|-----------------|----------------|
| `BacktestForm.test.tsx` | BacktestForm | Validation, multi-select, submit |
| `BacktestResults.test.tsx` | BacktestResults | Stats display, chart rendering |
| `PositionCard.test.tsx` | PositionCard | PnL display, actions |
| `RiskControls.test.tsx` | RiskControls | Kill switch toggle, limit inputs |

#### Hook Tests (`frontend/tests/hooks/`)
| File | Coverage Target | Key Test Cases |
|------|-----------------|----------------|
| `useWebSocket.test.ts` | useWebSocket | Connect, reconnect, message handling |
| `useBacktest.test.ts` | useBacktest | API calls, state updates |

#### E2E Tests (Playwright - optional)
| File | Coverage Target | Key Test Cases |
|------|-----------------|----------------|
| `backtest.spec.ts` | Backtest page | Full user flow |
| `trading.spec.ts` | Trading page | Config creation, start/stop |

### Test Coverage Targets
- Backend: **80%** minimum line coverage
- Frontend: **70%** minimum line coverage
- Critical paths (risk, orders): **95%** coverage

---

## Completion Criteria & Auto-Iteration Gates

### Phase 1: Backend Foundation
**Minimum Completion Criteria:**
- [ ] FastAPI app starts without errors (`python run_backend.py`)
- [ ] SQLite database initializes with all 7 tables
- [ ] `/api/health` endpoint returns 200
- [ ] Unit tests pass: `pytest backend/tests/unit/ -v`
- [ ] Test coverage ≥ 60% for created files

**Verification Command:**
```bash
python run_backend.py &  # Start server
curl http://localhost:8000/api/health  # Should return {"status": "ok"}
pytest backend/tests/unit/ --cov=backend --cov-report=term-missing
```

### Phase 2: Backtest Feature
**Minimum Completion Criteria:**
- [ ] POST `/api/backtests` creates job and returns ID
- [ ] Backtest executes in background worker
- [ ] Progress updates broadcast via WebSocket
- [ ] GET `/api/backtests/{id}` returns results after completion
- [ ] Backtest with existing strategy (supertrend) produces valid trades
- [ ] Integration tests pass: `pytest backend/tests/integration/test_backtest_api.py -v`

**Verification Command:**
```bash
# Create backtest
curl -X POST http://localhost:8000/api/backtests \
  -H "Content-Type: application/json" \
  -d '{"symbols":["ETHUSDT"],"strategies":[{"type":"supertrend","params":{}}],"fee_rate":0.0015,"initial_equity":10000}'

# Check status (should show progress/completion)
curl http://localhost:8000/api/backtests/{id}
```

### Phase 3: Frontend Foundation
**Minimum Completion Criteria:**
- [ ] `yarn dev` starts frontend without errors
- [ ] All 4 pages render (`/backtest`, `/live`, `/positions`, `/settings`)
- [ ] BacktestForm submits request to backend
- [ ] WebSocket connects and receives backtest progress
- [ ] BacktestResults displays stats and chart
- [ ] Component tests pass: `yarn test`

**Verification Command:**
```bash
cd frontend
yarn dev     # Should start on http://localhost:5173
yarn test    # All tests pass
yarn build   # Production build succeeds
```

### Phase 4: Live Trading Core
**Minimum Completion Criteria:**
- [ ] BybitClient connects to testnet (not mainnet initially)
- [ ] OrderService can place test orders
- [ ] RiskService blocks orders when limits exceeded
- [ ] Kill switch closes all positions
- [ ] Position updates via WebSocket
- [ ] E2E test pass: `pytest backend/tests/e2e/test_trading_flow.py -v`

**Verification Command:**
```bash
# Use Bybit testnet
export BYBIT_TESTNET=true
pytest backend/tests/e2e/test_trading_flow.py -v
```

### Phase 5: Integration & Polish
**Minimum Completion Criteria:**
- [ ] Discord notifications sent on trade events
- [ ] Saved configs persist and reload correctly
- [ ] WebSocket reconnects after disconnect
- [ ] All tests pass: `pytest && cd frontend && yarn test`
- [ ] Backend coverage ≥ 80%, Frontend coverage ≥ 70%
- [ ] No critical/high security issues (basic audit)

**Verification Command:**
```bash
# Full test suite
pytest backend/ --cov=backend --cov-fail-under=80
cd frontend && yarn test --coverage --coverageThreshold='{"global":{"lines":70}}'
```

---

## Auto-Iteration Protocol

When implementing each phase, follow this protocol:

1. **Implement** → Write code for the phase
2. **Test** → Run verification commands
3. **Check** → All criteria met?
   - **YES** → Proceed to next phase
   - **NO** → Fix issues and re-test
4. **Report** → Summarize what was completed, what tests pass

### Iteration Loop Example
```
[Phase 1] → Implement → Test → FAIL (health endpoint missing)
         → Fix → Test → FAIL (coverage 55%)
         → Add tests → Test → PASS (coverage 62%)
         → ✓ Phase 1 Complete
[Phase 2] → Implement → Test → ...
```

### Stop Conditions
- **Success**: All 5 phases complete with all criteria met
- **Blocked**: External dependency unavailable (e.g., Bybit API down)
- **User Request**: User asks to pause or change direction

---

## Success Criteria (Final)

The application is considered production-ready when:

1. **Backtest Feature**
   - [ ] User can run backtests via UI with multi-select symbols/strategies/filters
   - [ ] Backtest results display with TradingView charts and stats
   - [ ] Backtest configs can be saved and reloaded
   - [ ] Multiple concurrent backtests execute without issues

2. **Live Trading Feature**
   - [ ] Live trading executes orders automatically on signals
   - [ ] Real-time position updates via WebSocket
   - [ ] Positions tracked in SQLite with correct PnL

3. **Risk Management**
   - [ ] Risk controls prevent excessive losses
   - [ ] Kill switch immediately halts all trading and closes positions
   - [ ] Daily loss limit triggers automatic kill switch

4. **Notifications**
   - [ ] Discord notifications on trade entry/exit with PnL

5. **Quality**
   - [ ] All tests pass
   - [ ] Backend coverage ≥ 80%
   - [ ] Frontend coverage ≥ 70%
   - [ ] No critical bugs in core trading flow
