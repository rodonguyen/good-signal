export interface RiskState {
  kill_switch_active: boolean
  kill_switch_reason?: string
  kill_switch_activated_at?: string
  daily_pnl: number
  daily_trades?: number
  daily_reset_date?: string
  total_open_positions: number
  total_exposure: number
  total_unrealized_pnl?: number
  updated_at?: string
  risk_limits: RiskLimits
}

export interface RiskLimits {
  max_daily_loss: number
  max_positions: number
  max_exposure: number
  max_position_size?: number
}

export type PositionDirection = 'LONG' | 'SHORT'
export type PositionStatus = 'OPEN' | 'CLOSED' | 'PENDING'

export interface Position {
  id: string
  symbol: string
  direction: PositionDirection
  entry_price: number
  current_price: number
  quantity: number
  unrealized_pnl: number
  realized_pnl: number
  stop_loss?: number
  take_profit?: number
  status: PositionStatus
  opened_at: string
  closed_at?: string
  strategy?: string
}

export interface UpdateStopLossRequest {
  stop_loss: number
}

export interface UpdateTakeProfitRequest {
  take_profit: number
}

export interface ClosePositionRequest {
  reason?: string
}

export interface ActivateKillSwitchRequest {
  reason: string
}
