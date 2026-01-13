import { useCallback, useEffect, useRef, useState } from 'react'

interface UseWebSocketOptions {
  url: string
  onMessage?: (data: unknown) => void
  onError?: (error: Event) => void
  onOpen?: () => void
  onClose?: () => void
  reconnect?: boolean
  reconnectInterval?: number
  maxReconnectAttempts?: number
}

interface WebSocketState {
  isConnected: boolean
  isConnecting: boolean
  error: string | null
  reconnectAttempts: number
}

export function useWebSocket(options: UseWebSocketOptions) {
  const {
    url,
    onMessage,
    onError,
    onOpen,
    onClose,
    reconnect = true,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options

  const [state, setState] = useState<WebSocketState>({
    isConnected: false,
    isConnecting: false,
    error: null,
    reconnectAttempts: 0,
  })

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | undefined>(undefined)
  const reconnectAttemptsRef = useRef(0)

  const calculateBackoff = useCallback((attempt: number): number => {
    // Exponential backoff with jitter: base * 2^attempt + random jitter
    const base = reconnectInterval
    const maxDelay = 30000 // Max 30 seconds
    const exponentialDelay = Math.min(base * Math.pow(2, attempt), maxDelay)
    const jitter = Math.random() * 1000 // Add up to 1 second of jitter
    return exponentialDelay + jitter
  }, [reconnectInterval])

  const connect = useCallback(() => {
    // Don't reconnect if we've exceeded max attempts
    if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
      setState(prev => ({
        ...prev,
        error: `Failed to connect after ${maxReconnectAttempts} attempts`,
        isConnecting: false,
      }))
      return
    }

    try {
      setState(prev => ({ ...prev, isConnecting: true, error: null }))

      const ws = new WebSocket(url)

      ws.onopen = () => {
        reconnectAttemptsRef.current = 0
        setState({
          isConnected: true,
          isConnecting: false,
          error: null,
          reconnectAttempts: 0,
        })
        onOpen?.()
      }

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          onMessage?.(data)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      ws.onerror = (error) => {
        setState(prev => ({
          ...prev,
          error: 'WebSocket connection error',
        }))
        onError?.(error)
      }

      ws.onclose = (event) => {
        setState(prev => ({
          ...prev,
          isConnected: false,
          isConnecting: false,
        }))
        onClose?.()

        // Only reconnect on abnormal closure
        if (reconnect && !event.wasClean) {
          const attempt = reconnectAttemptsRef.current
          reconnectAttemptsRef.current += 1

          const delay = calculateBackoff(attempt)

          setState(prev => ({
            ...prev,
            reconnectAttempts: reconnectAttemptsRef.current,
            error: `Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})`,
          }))

          reconnectTimeoutRef.current = window.setTimeout(connect, delay)
        }
      }

      wsRef.current = ws
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error)
      setState(prev => ({
        ...prev,
        isConnecting: false,
        error: error instanceof Error ? error.message : 'Failed to connect',
      }))
    }
  }, [url, reconnect, maxReconnectAttempts, calculateBackoff, onMessage, onError, onOpen, onClose])

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = undefined
    }

    if (wsRef.current) {
      // Close with normal closure code to prevent reconnection
      wsRef.current.close(1000, 'User disconnected')
      wsRef.current = null
    }

    reconnectAttemptsRef.current = 0
    setState({
      isConnected: false,
      isConnecting: false,
      error: null,
      reconnectAttempts: 0,
    })
  }, [])

  const send = useCallback((data: unknown): boolean => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
      return true
    }
    return false
  }, [])

  const resetConnection = useCallback(() => {
    reconnectAttemptsRef.current = 0
    disconnect()
    connect()
  }, [connect, disconnect])

  useEffect(() => {
    connect()
    return disconnect
  }, [url]) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    isConnected: state.isConnected,
    isConnecting: state.isConnecting,
    error: state.error,
    reconnectAttempts: state.reconnectAttempts,
    send,
    disconnect,
    resetConnection,
  }
}
