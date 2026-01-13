import { create } from 'zustand'
import type { BacktestResult, BacktestTrade, BacktestRequest, BacktestStatus } from '@/types/backtest'
import * as backtestApi from '@/api/backtest'

interface BacktestStore {
  // State
  backtests: BacktestResult[]
  currentBacktest: BacktestResult | null
  trades: BacktestTrade[]
  isLoading: boolean
  error: string | null

  // Pagination
  currentPage: number
  totalPages: number

  // Actions
  fetchBacktests: (page?: number, pageSize?: number, status?: BacktestStatus) => Promise<void>
  createBacktest: (request: BacktestRequest) => Promise<BacktestResult>
  fetchBacktest: (id: string) => Promise<void>
  fetchTrades: (id: string, page?: number, pageSize?: number) => Promise<void>
  cancelBacktest: (id: string) => Promise<void>
  deleteBacktest: (id: string) => Promise<void>
  setCurrentBacktest: (backtest: BacktestResult | null) => void
  updateBacktest: (id: string, updates: Partial<BacktestResult>) => void
  reset: () => void
}

export const useBacktestStore = create<BacktestStore>((set) => ({
  // Initial state
  backtests: [],
  currentBacktest: null,
  trades: [],
  isLoading: false,
  error: null,
  currentPage: 1,
  totalPages: 1,

  // Fetch list of backtests
  fetchBacktests: async (page = 1, pageSize = 20, status) => {
    set({ isLoading: true, error: null })
    try {
      const response = await backtestApi.listBacktests(page, pageSize, status)
      set({
        backtests: response.items,
        currentPage: response.page,
        totalPages: response.total_pages,
        isLoading: false,
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch backtests',
        isLoading: false,
      })
    }
  },

  // Create new backtest
  createBacktest: async (request) => {
    set({ isLoading: true, error: null })
    try {
      const result = await backtestApi.createBacktest(request)
      set((state) => ({
        backtests: [result, ...state.backtests],
        currentBacktest: result,
        trades: [],  // Clear trades since new backtest has no trades yet
        isLoading: false,
      }))
      return result
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to create backtest',
        isLoading: false,
      })
      throw error
    }
  },

  // Fetch single backtest details
  fetchBacktest: async (id) => {
    set({ isLoading: true, error: null })
    try {
      const result = await backtestApi.getBacktest(id)
      set({
        currentBacktest: result,
        isLoading: false,
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch backtest',
        isLoading: false,
      })
    }
  },

  // Fetch trades for a backtest (fetch all trades at once with max page size)
  fetchTrades: async (id, page = 1, pageSize = 10000) => {
    set({ isLoading: true, error: null })
    try {
      const response = await backtestApi.getBacktestTrades(id, page, pageSize)
      set({
        trades: response.items,
        isLoading: false,
      })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch trades',
        isLoading: false,
      })
    }
  },

  // Cancel running backtest
  cancelBacktest: async (id) => {
    set({ isLoading: true, error: null })
    try {
      const result = await backtestApi.cancelBacktest(id)
      set((state) => ({
        backtests: state.backtests.map((b) => (b.id === id ? result : b)),
        currentBacktest: state.currentBacktest?.id === id ? result : state.currentBacktest,
        isLoading: false,
      }))
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to cancel backtest',
        isLoading: false,
      })
    }
  },

  // Delete backtest
  deleteBacktest: async (id) => {
    set({ isLoading: true, error: null })
    try {
      await backtestApi.deleteBacktest(id)
      set((state) => ({
        backtests: state.backtests.filter((b) => b.id !== id),
        currentBacktest: state.currentBacktest?.id === id ? null : state.currentBacktest,
        isLoading: false,
      }))
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete backtest',
        isLoading: false,
      })
    }
  },

  // Set current backtest (clears trades to avoid showing stale data from previous selection)
  setCurrentBacktest: (backtest) => set({ currentBacktest: backtest, trades: [] }),

  // Update backtest with partial data (for WebSocket progress updates)
  updateBacktest: (id, updates) => set((state) => ({
    backtests: state.backtests.map((b) =>
      b.id === id ? { ...b, ...updates } : b
    ),
    currentBacktest: state.currentBacktest?.id === id
      ? { ...state.currentBacktest, ...updates }
      : state.currentBacktest,
  })),

  // Reset store
  reset: () => set({
    backtests: [],
    currentBacktest: null,
    trades: [],
    isLoading: false,
    error: null,
    currentPage: 1,
    totalPages: 1,
  }),
}))
