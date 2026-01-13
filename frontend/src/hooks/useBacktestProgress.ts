import { useCallback } from 'react'
import { useWebSocket } from './useWebSocket'
import { useBacktestStore } from '@/stores/useBacktestStore'

interface BacktestProgressEvent {
  type: 'backtest:progress' | 'backtest:complete' | 'backtest:error'
  backtest_id: string
  progress?: number
  status?: string
  current_symbol?: string
  results?: {
    total_return?: number
    sharpe_ratio?: number
    max_drawdown?: number
    win_rate?: number
    profit_factor?: number
    total_trades?: number
  }
  error?: string
}

export function useBacktestProgress() {
  const { updateBacktest, fetchBacktest, fetchBacktests } = useBacktestStore()

  const handleMessage = useCallback((data: unknown) => {
    const event = data as BacktestProgressEvent

    switch (event.type) {
      case 'backtest:progress':
        // Update the backtest progress in the store
        updateBacktest(event.backtest_id, {
          progress: event.progress ?? 0,
          status: 'running',
        })
        break

      case 'backtest:complete':
        // Fetch the complete backtest details
        fetchBacktest(event.backtest_id)
        fetchBacktests()
        break

      case 'backtest:error':
        updateBacktest(event.backtest_id, {
          status: 'failed',
          error_message: event.error,
        })
        break
    }
  }, [updateBacktest, fetchBacktest, fetchBacktests])

  const { isConnected, isConnecting, error, reconnectAttempts, send, resetConnection } = useWebSocket({
    url: 'ws://localhost:8000/ws',
    onMessage: handleMessage,
    onOpen: () => {
      // Subscribe to backtest events
      send({ type: 'subscribe', channels: ['backtest'] })
    },
    reconnect: true,
    reconnectInterval: 5000,
    maxReconnectAttempts: 10,
  })

  return {
    isConnected,
    isConnecting,
    connectionError: error,
    reconnectAttempts,
    resetConnection,
  }
}
