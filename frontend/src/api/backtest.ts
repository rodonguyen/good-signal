import { apiClient } from './client'
import type {
  BacktestRequest,
  BacktestResult,
  BacktestTrade,
  BacktestStatus,
  PaginatedResponse,
} from '@/types/backtest'

/**
 * Create a new backtest
 * @param request Backtest configuration
 * @returns Created backtest result
 */
export async function createBacktest(request: BacktestRequest): Promise<BacktestResult> {
  const response = await apiClient.post<BacktestResult>('/api/backtests', request)
  return response.data
}

/**
 * List all backtests with pagination
 * @param page Page number (1-indexed)
 * @param pageSize Number of items per page
 * @param status Optional status filter
 * @returns Paginated list of backtests
 */
export async function listBacktests(
  page: number = 1,
  pageSize: number = 20,
  status?: BacktestStatus
): Promise<PaginatedResponse<BacktestResult>> {
  const params: Record<string, string | number> = {
    page,
    page_size: pageSize,
  }

  if (status) {
    params.status = status
  }

  const response = await apiClient.get<PaginatedResponse<BacktestResult>>('/api/backtests', {
    params,
  })
  return response.data
}

/**
 * Get a specific backtest by ID
 * @param id Backtest ID
 * @returns Backtest result
 */
export async function getBacktest(id: string): Promise<BacktestResult> {
  const response = await apiClient.get<BacktestResult>(`/api/backtests/${id}`)
  return response.data
}

/**
 * Get trades for a specific backtest
 * @param id Backtest ID
 * @param page Page number (1-indexed)
 * @param pageSize Number of items per page
 * @returns Paginated list of trades
 */
export async function getBacktestTrades(
  id: string,
  page: number = 1,
  pageSize: number = 50
): Promise<PaginatedResponse<BacktestTrade>> {
  const response = await apiClient.get<PaginatedResponse<BacktestTrade>>(
    `/api/backtests/${id}/trades`,
    {
      params: {
        page,
        page_size: pageSize,
      },
    }
  )
  return response.data
}

/**
 * Cancel a running backtest
 * @param id Backtest ID
 * @returns Updated backtest result
 */
export async function cancelBacktest(id: string): Promise<BacktestResult> {
  const response = await apiClient.post<BacktestResult>(`/api/backtests/${id}/cancel`)
  return response.data
}

/**
 * Delete a backtest
 * @param id Backtest ID
 */
export async function deleteBacktest(id: string): Promise<void> {
  await apiClient.delete(`/api/backtests/${id}`)
}
