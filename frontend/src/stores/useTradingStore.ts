import { create } from 'zustand'
import type {
  RiskState,
  Position,
  RiskLimits,
} from '@/types/trading'
import {
  getRiskState,
  activateKillSwitch,
  deactivateKillSwitch,
  updateRiskLimits,
  listPositions,
  closePosition,
  updateStopLoss,
  updateTakeProfit,
} from '@/api/trading'
import type { ListPositionsParams } from '@/api/trading'

interface TradingStore {
  // State
  riskState: RiskState | null
  positions: Position[]
  isLoading: boolean
  error: string | null

  // Actions
  fetchRiskState: () => Promise<void>
  toggleKillSwitch: (active: boolean, reason?: string) => Promise<void>
  updateLimits: (limits: RiskLimits) => Promise<void>
  fetchPositions: (params?: ListPositionsParams) => Promise<void>
  closePosition: (id: string, reason?: string) => Promise<void>
  updatePositionStopLoss: (id: string, stopLoss: number) => Promise<void>
  updatePositionTakeProfit: (id: string, takeProfit: number) => Promise<void>
  clearError: () => void
}

export const useTradingStore = create<TradingStore>((set, get) => ({
  // Initial state
  riskState: null,
  positions: [],
  isLoading: false,
  error: null,

  // Fetch risk state
  fetchRiskState: async () => {
    set({ isLoading: true, error: null })
    try {
      const riskState = await getRiskState()
      set({ riskState, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch risk state',
        isLoading: false,
      })
    }
  },

  // Toggle kill switch
  toggleKillSwitch: async (active: boolean, reason?: string) => {
    set({ isLoading: true, error: null })
    try {
      let riskState: RiskState
      if (active) {
        if (!reason) {
          throw new Error('Reason is required to activate kill switch')
        }
        riskState = await activateKillSwitch(reason)
      } else {
        riskState = await deactivateKillSwitch()
      }
      set({ riskState, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to toggle kill switch',
        isLoading: false,
      })
      throw error
    }
  },

  // Update risk limits
  updateLimits: async (limits: RiskLimits) => {
    set({ isLoading: true, error: null })
    try {
      const riskState = await updateRiskLimits(limits)
      set({ riskState, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to update risk limits',
        isLoading: false,
      })
      throw error
    }
  },

  // Fetch positions
  fetchPositions: async (params?: ListPositionsParams) => {
    set({ isLoading: true, error: null })
    try {
      const positions = await listPositions(params)
      set({ positions, isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to fetch positions',
        isLoading: false,
      })
    }
  },

  // Close position
  closePosition: async (id: string, reason?: string) => {
    set({ isLoading: true, error: null })
    try {
      await closePosition(id, reason)
      // Refresh positions list
      await get().fetchPositions()
      set({ isLoading: false })
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to close position',
        isLoading: false,
      })
      throw error
    }
  },

  // Update position stop loss
  updatePositionStopLoss: async (id: string, stopLoss: number) => {
    set({ isLoading: true, error: null })
    try {
      const updatedPosition = await updateStopLoss(id, stopLoss)
      // Update position in the list
      set((state) => ({
        positions: state.positions.map((p) =>
          p.id === id ? updatedPosition : p
        ),
        isLoading: false,
      }))
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to update stop loss',
        isLoading: false,
      })
      throw error
    }
  },

  // Update position take profit
  updatePositionTakeProfit: async (id: string, takeProfit: number) => {
    set({ isLoading: true, error: null })
    try {
      const updatedPosition = await updateTakeProfit(id, takeProfit)
      // Update position in the list
      set((state) => ({
        positions: state.positions.map((p) =>
          p.id === id ? updatedPosition : p
        ),
        isLoading: false,
      }))
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to update take profit',
        isLoading: false,
      })
      throw error
    }
  },

  // Clear error
  clearError: () => set({ error: null }),
}))
