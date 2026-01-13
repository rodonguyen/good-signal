import { apiClient } from './client'
import type {
  RiskState,
  RiskLimits,
  Position,
  ActivateKillSwitchRequest,
  ClosePositionRequest,
  UpdateStopLossRequest,
  UpdateTakeProfitRequest,
  PositionStatus,
} from '@/types/trading'

// Risk Management APIs
export const getRiskState = async (): Promise<RiskState> => {
  const response = await apiClient.get<RiskState>('/api/risk')
  return response.data
}

export const activateKillSwitch = async (reason: string): Promise<RiskState> => {
  const response = await apiClient.post<RiskState>('/api/risk/kill-switch', {
    reason,
  } as ActivateKillSwitchRequest)
  return response.data
}

export const deactivateKillSwitch = async (): Promise<RiskState> => {
  const response = await apiClient.delete<RiskState>('/api/risk/kill-switch')
  return response.data
}

export const updateRiskLimits = async (limits: RiskLimits): Promise<RiskState> => {
  const response = await apiClient.put<RiskState>('/api/risk/limits', limits)
  return response.data
}

// Position Management APIs
export interface ListPositionsParams {
  status?: PositionStatus
  symbol?: string
  skip?: number
  limit?: number
}

interface PositionsResponse {
  positions: Position[]
  total: number
  skip: number
  limit: number
}

export const listPositions = async (params?: ListPositionsParams): Promise<Position[]> => {
  const response = await apiClient.get<PositionsResponse>('/api/positions', { params })
  return response.data.positions
}

export const getPosition = async (id: string): Promise<Position> => {
  const response = await apiClient.get<Position>(`/api/positions/${id}`)
  return response.data
}

export const closePosition = async (id: string, reason?: string): Promise<Position> => {
  const response = await apiClient.post<Position>(`/api/positions/${id}/close`, {
    reason,
  } as ClosePositionRequest)
  return response.data
}

export const updateStopLoss = async (id: string, stopLoss: number): Promise<Position> => {
  const response = await apiClient.put<Position>(`/api/positions/${id}/stop-loss`, {
    stop_loss: stopLoss,
  } as UpdateStopLossRequest)
  return response.data
}

export const updateTakeProfit = async (id: string, takeProfit: number): Promise<Position> => {
  const response = await apiClient.put<Position>(`/api/positions/${id}/take-profit`, {
    take_profit: takeProfit,
  } as UpdateTakeProfitRequest)
  return response.data
}
