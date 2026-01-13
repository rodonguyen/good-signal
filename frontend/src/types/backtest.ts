// Backtest API Types

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface StrategyConfig {
  type: string // 'supertrend' | 'ma_cross' | 'rsi' | etc.
  enabled: boolean
  signal_timeframe?: string
  params: Record<string, number | string | boolean>
}

export interface FilterConfig {
  type: string // 'ema_filter' | 'volume_filter' | etc.
  enabled: boolean
  params: Record<string, number | string | boolean>
}

export interface BacktestRequest {
  symbols: string[]
  strategies: StrategyConfig[]
  filters?: FilterConfig[]
  timeframe?: string
  start_date?: string
  end_date?: string
  fee_rate?: number
  initial_equity?: number
}

export type BacktestStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface BacktestMetrics {
  total_return: number
  total_return_pct: number
  sharpe_ratio: number
  sortino_ratio?: number
  max_drawdown: number
  max_drawdown_pct: number
  win_rate: number
  profit_factor: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  avg_win: number
  avg_loss: number
  largest_win?: number
  largest_loss?: number
  avg_trade_duration?: number
  expectancy?: number
}

export interface BacktestResult {
  id: string
  name?: string
  status: BacktestStatus
  progress: number
  config: Record<string, unknown>
  symbols: string[]
  strategies: StrategyConfig[]
  filters?: FilterConfig[]
  timeframe?: string
  fee_rate?: number
  initial_equity?: number
  final_equity?: number
  metrics?: BacktestMetrics
  error_message?: string
  created_at: string
  completed_at?: string
}

export type TradeDirection = 'long' | 'short'

export interface BacktestTrade {
  id: number
  symbol: string
  strategy_id: string
  direction: TradeDirection
  entry_time: string
  exit_time: string
  entry_price: number
  exit_price: number
  exit_reason?: string
  stop_level?: number
  tp_level?: number
  raw_pnl: number
  fees: number
  net_pnl: number
  portfolio_pnl?: number
  position_size?: number
}

// Form state types for UI
export interface BacktestFormState {
  symbols: string[]
  strategies: StrategyConfig[]
  filters: FilterConfig[]
  timeframe: string
  startDate: string
  endDate: string
  feeRate: number
  initialEquity: number
}
