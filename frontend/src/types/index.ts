// API Types
export interface BacktestConfig {
  symbol: string
  timeframe: string
  startDate: string
  endDate: string
  strategy: string
  parameters: Record<string, unknown>
}

export interface BacktestResult {
  id: string
  config: BacktestConfig
  metrics: {
    totalReturn: number
    sharpeRatio: number
    maxDrawdown: number
    winRate: number
    totalTrades: number
  }
  trades: Trade[]
  equity: number[]
}

export interface Trade {
  id: string
  timestamp: string
  symbol: string
  side: 'buy' | 'sell'
  price: number
  quantity: number
  pnl?: number
}

export interface Position {
  symbol: string
  side: 'long' | 'short'
  quantity: number
  entryPrice: number
  currentPrice: number
  unrealizedPnl: number
  realizedPnl: number
}

export interface Strategy {
  id: string
  name: string
  description: string
  parameters: Record<string, unknown>
  isActive: boolean
}
