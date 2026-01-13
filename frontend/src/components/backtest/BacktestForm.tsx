import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import type { BacktestRequest, StrategyConfig, FilterConfig } from '@/types/backtest'
import { X } from 'lucide-react'

interface BacktestFormProps {
  onSubmit: (request: BacktestRequest) => void
  isLoading?: boolean
}

const AVAILABLE_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT']
const TIMEFRAMES = ['1m', '5m', '15m', '30m', '1h', '4h', '1d']

const DEFAULT_STRATEGIES: StrategyConfig[] = [
  {
    type: 'supertrend',
    enabled: true,
    signal_timeframe: '15m',
    params: {
      atr_period: 10,
      atr_multiplier: 3.0,
    },
  },
]

export default function BacktestForm({ onSubmit, isLoading = false }: BacktestFormProps) {
  const [symbols, setSymbols] = useState<string[]>(['BTCUSDT'])
  const [symbolInput, setSymbolInput] = useState('')
  const [strategies, setStrategies] = useState<StrategyConfig[]>(DEFAULT_STRATEGIES)
  const [filters] = useState<FilterConfig[]>([])
  const [timeframe, setTimeframe] = useState('15m')

  // Sync timeframe to all strategies when changed
  const updateTimeframe = (newTimeframe: string) => {
    setTimeframe(newTimeframe)
    setStrategies((prev) =>
      prev.map((s) => ({
        ...s,
        signal_timeframe: newTimeframe,
      }))
    )
  }

  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [feeRate, setFeeRate] = useState(0.001)
  const [initialEquity, setInitialEquity] = useState(10000)

  const addSymbol = (symbol: string) => {
    const upperSymbol = symbol.toUpperCase()
    if (upperSymbol && !symbols.includes(upperSymbol)) {
      setSymbols([...symbols, upperSymbol])
      setSymbolInput('')
    }
  }

  const removeSymbol = (symbol: string) => {
    setSymbols(symbols.filter((s) => s !== symbol))
  }

  const updateStrategyParam = (index: number, paramKey: string, value: number | string | boolean) => {
    const updated = [...strategies]
    updated[index] = {
      ...updated[index],
      params: {
        ...updated[index].params,
        [paramKey]: value,
      },
    }
    setStrategies(updated)
  }

  const toggleStrategyEnabled = (index: number) => {
    const updated = [...strategies]
    updated[index] = {
      ...updated[index],
      enabled: !updated[index].enabled,
    }
    setStrategies(updated)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    if (symbols.length === 0) {
      alert('Please select at least one symbol')
      return
    }

    const enabledStrategies = strategies.filter((s) => s.enabled)
    if (enabledStrategies.length === 0) {
      alert('Please enable at least one strategy')
      return
    }

    const request: BacktestRequest = {
      symbols,
      strategies: enabledStrategies,
      filters: filters.filter((f) => f.enabled),
      timeframe,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      fee_rate: feeRate,
      initial_equity: initialEquity,
    }

    onSubmit(request)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Backtest Configuration</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Symbols Selection */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Symbols</label>
            <div className="flex gap-2">
              <Select
                value={symbolInput}
                onChange={(e) => {
                  const value = e.target.value
                  setSymbolInput(value)
                  if (value) addSymbol(value)
                }}
              >
                <option value="">Select a symbol</option>
                {AVAILABLE_SYMBOLS.map((sym) => (
                  <option key={sym} value={sym}>
                    {sym}
                  </option>
                ))}
              </Select>
              <Input
                placeholder="Or type custom symbol"
                value={symbolInput}
                onChange={(e) => setSymbolInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addSymbol(symbolInput)
                  }
                }}
              />
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {symbols.map((symbol) => (
                <Badge key={symbol} variant="secondary" className="pl-2 pr-1">
                  {symbol}
                  <button
                    type="button"
                    onClick={() => removeSymbol(symbol)}
                    className="ml-1 hover:bg-secondary-foreground/20 rounded-full p-0.5"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
          </div>

          {/* Strategy Configuration */}
          <div className="space-y-3">
            <label className="text-sm font-medium">Strategies</label>
            {strategies.map((strategy, index) => (
              <Card key={index} className="p-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={strategy.enabled}
                        onChange={() => toggleStrategyEnabled(index)}
                        className="w-4 h-4"
                      />
                      <span className="font-medium capitalize">
                        {strategy.type.replace('_', ' ')}
                      </span>
                    </div>
                  </div>

                  {strategy.enabled && (
                    <div className="grid grid-cols-2 gap-3 pl-6">
                      {strategy.type === 'supertrend' && (
                        <>
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">ATR Period</label>
                            <Input
                              type="number"
                              value={strategy.params.atr_period as number}
                              onChange={(e) =>
                                updateStrategyParam(index, 'atr_period', Number(e.target.value))
                              }
                              min={1}
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="text-xs text-muted-foreground">ATR Multiplier</label>
                            <Input
                              type="number"
                              step="0.1"
                              value={strategy.params.atr_multiplier as number}
                              onChange={(e) =>
                                updateStrategyParam(index, 'atr_multiplier', Number(e.target.value))
                              }
                            />
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>

          {/* Timeframe and Date Range */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Timeframe</label>
              <Select value={timeframe} onChange={(e) => updateTimeframe(e.target.value)}>
                {TIMEFRAMES.map((tf) => (
                  <option key={tf} value={tf}>
                    {tf}
                  </option>
                ))}
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Start Date</label>
              <Input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">End Date</label>
              <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
            </div>
          </div>

          {/* Trading Parameters */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Fee Rate (%)</label>
              <Input
                type="number"
                step="0.001"
                value={feeRate * 100}
                onChange={(e) => setFeeRate(Number(e.target.value) / 100)}
                min={0}
                max={1}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Initial Equity (USDT)</label>
              <Input
                type="number"
                value={initialEquity}
                onChange={(e) => setInitialEquity(Number(e.target.value))}
                min={1}
              />
            </div>
          </div>

          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? 'Running Backtest...' : 'Run Backtest'}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}
