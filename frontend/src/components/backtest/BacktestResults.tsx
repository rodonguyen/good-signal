import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Table } from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import type { BacktestResult, BacktestTrade } from '@/types/backtest'
import { TrendingUp, TrendingDown, ChevronLeft, ChevronRight } from 'lucide-react'
import EquityChart from '@/components/charts/EquityChart'
import { useMemo, useState } from 'react'

interface BacktestResultsProps {
  backtest: BacktestResult
  trades?: BacktestTrade[]
  onLoadTrades?: () => void
}

export default function BacktestResults({ backtest, trades = [], onLoadTrades }: BacktestResultsProps) {
  const isRunning = backtest.status === 'running'
  const isCompleted = backtest.status === 'completed'
  const metrics = backtest.metrics

  const formatNumber = (num: number | undefined | null, decimals = 2): string => {
    if (num == null) return 'N/A'
    return num.toFixed(decimals)
  }

  const formatPercent = (num: number | undefined | null): string => {
    if (num == null) return 'N/A'
    return `${(num * 100).toFixed(2)}%`
  }

  const formatCurrency = (num: number | undefined | null): string => {
    if (num == null) return 'N/A'
    return `$${num.toFixed(2)}`
  }

  // Pagination state
  const [currentPage, setCurrentPage] = useState(1)
  const tradesPerPage = 1000

  // Calculate PnL percentage from prices
  const calculatePnlPct = (trade: BacktestTrade): number => {
    if (trade.entry_price === 0) return 0
    if (trade.direction === 'long') {
      return (trade.exit_price - trade.entry_price) / trade.entry_price
    } else {
      return (trade.entry_price - trade.exit_price) / trade.entry_price
    }
  }

  // Generate equity curve data from trades
  const equityData = useMemo(() => {
    if (trades.length === 0 || backtest.initial_equity === undefined) return []

    const startingEquity = backtest.initial_equity
    const equityByDate = new Map<string, number>()

    // Add initial equity point at start date or first trade
    const firstTradeTime = trades[0]?.entry_time
    if (firstTradeTime) {
      const startDate = new Date(firstTradeTime).toISOString().split('T')[0]
      equityByDate.set(startDate, startingEquity)
    }

    // Calculate cumulative equity after each trade, keeping only last value per date
    let cumulativePnL = 0
    trades.forEach((trade) => {
      cumulativePnL += trade.portfolio_pnl ?? trade.net_pnl
      const currentEquity = startingEquity + cumulativePnL
      const tradeDate = new Date(trade.exit_time).toISOString().split('T')[0]
      // Overwrite with latest equity value for this date
      equityByDate.set(tradeDate, currentEquity)
    })

    // Convert to array and sort by date ascending
    const data = Array.from(equityByDate.entries())
      .map(([time, value]) => ({ time, value }))
      .sort((a, b) => a.time.localeCompare(b.time))

    return data
  }, [trades, backtest.initial_equity])

  // Generate symbol price data from trades
  const priceData = useMemo(() => {
    if (trades.length === 0) return []

    const priceByDate = new Map<string, number>()

    trades.forEach((trade) => {
      // Add entry price at entry time
      const entryDate = new Date(trade.entry_time).toISOString().split('T')[0]
      priceByDate.set(entryDate, trade.entry_price)

      // Add exit price at exit time (will overwrite if same day)
      const exitDate = new Date(trade.exit_time).toISOString().split('T')[0]
      priceByDate.set(exitDate, trade.exit_price)
    })

    // Convert to array and sort by date ascending
    return Array.from(priceByDate.entries())
      .map(([time, value]) => ({ time, value }))
      .sort((a, b) => a.time.localeCompare(b.time))
  }, [trades])

  // Pagination calculations
  const totalPages = Math.ceil(trades.length / tradesPerPage)
  const startIndex = (currentPage - 1) * tradesPerPage
  const endIndex = startIndex + tradesPerPage
  const paginatedTrades = trades.slice(startIndex, endIndex)

  const getStatusBadge = () => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      pending: 'secondary',
      running: 'default',
      completed: 'outline',
      failed: 'destructive',
      cancelled: 'secondary',
    }

    // Lighter red for failed badge
    const extraClasses = backtest.status === 'failed' ? 'bg-red-400 text-white hover:bg-red-500 border-red-400' : ''

    return (
      <Badge variant={variants[backtest.status] || 'default'} className={extraClasses}>
        {backtest.status.toUpperCase()}
      </Badge>
    )
  }

  return (
    <div className="space-y-6">
      {/* Status and Progress */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Backtest Status</CardTitle>
            {getStatusBadge()}
          </div>
          <CardDescription>
            Symbols: {backtest.symbols?.join(', ') || 'N/A'} | Timeframe: {backtest.timeframe || 'N/A'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isRunning && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Progress</span>
                <span>{backtest.progress}%</span>
              </div>
              <Progress value={backtest.progress} max={100} />
            </div>
          )}
          {backtest.status === 'failed' && backtest.error_message && (
            <div className="text-sm text-red-600 font-semibold">
              Error: {backtest.error_message}
            </div>
          )}
          {isCompleted && (
            <div className="text-sm text-muted-foreground">
              Completed at: {new Date(backtest.completed_at || '').toLocaleString()}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
          <CardDescription>Backtest parameters used for this run</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Strategies */}
            <div className="space-y-1 col-span-2">
              <div className="text-sm text-muted-foreground">Strategy</div>
              {backtest.strategies && backtest.strategies.length > 0 ? (
                <div className="space-y-2">
                  {backtest.strategies.map((strategy, index) => (
                    <div key={index} className="text-sm">
                      <span className="font-semibold capitalize">{strategy.type}</span>
                      {strategy.params && Object.keys(strategy.params).length > 0 && (
                        <span className="text-muted-foreground ml-2">
                          ({Object.entries(strategy.params).map(([key, value]) =>
                            `${key}: ${value}`
                          ).join(', ')})
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-sm">N/A</div>
              )}
            </div>

            {/* Timeframe */}
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">Timeframe</div>
              <div className="text-lg font-semibold">{backtest.timeframe || 'N/A'}</div>
            </div>

            {/* Fee Rate */}
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">Fee Rate</div>
              <div className="text-lg font-semibold">
                {backtest.fee_rate !== undefined ? `${(backtest.fee_rate * 100).toFixed(2)}%` : 'N/A'}
              </div>
            </div>

            {/* Initial Equity */}
            <div className="space-y-1">
              <div className="text-sm text-muted-foreground">Initial Equity</div>
              <div className="text-lg font-semibold">
                {formatCurrency(backtest.initial_equity)}
              </div>
            </div>

            {/* Date Range - from config if available */}
            {backtest.config?.start_date || backtest.config?.end_date ? (
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Date Range</div>
                <div className="text-sm">
                  {backtest.config?.start_date || 'Start'} → {backtest.config?.end_date || 'End'}
                </div>
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>

      {/* Metrics */}
      {metrics && (
        <Card>
          <CardHeader>
            <CardTitle>Performance Metrics</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {/* Total Return */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Total Return</div>
                <div className="flex items-center gap-2">
                  <div className="text-2xl font-bold">
                    {formatPercent(metrics.total_return_pct)}
                  </div>
                  {metrics.total_return_pct > 0 ? (
                    <TrendingUp className="h-5 w-5 text-green-500" />
                  ) : (
                    <TrendingDown className="h-5 w-5 text-red-500" />
                  )}
                </div>
                <div className="text-xs text-muted-foreground">
                  {formatCurrency(metrics.total_return)}
                </div>
              </div>

              {/* Sharpe Ratio */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Sharpe Ratio</div>
                <div className="text-2xl font-bold">{formatNumber(metrics.sharpe_ratio)}</div>
              </div>

              {/* Max Drawdown */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Max Drawdown</div>
                <div className="text-2xl font-bold text-red-500">
                  {metrics.max_drawdown != null ? `${metrics.max_drawdown.toFixed(2)}%` : 'N/A'}
                </div>
              </div>

              {/* Win Rate */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Win Rate</div>
                <div className="text-2xl font-bold">{formatPercent(metrics.win_rate)}</div>
                <div className="text-xs text-muted-foreground">
                  {metrics.winning_trades}/{metrics.total_trades} trades
                </div>
              </div>

              {/* Profit Factor */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Profit Factor</div>
                <div className="text-2xl font-bold">{formatNumber(metrics.profit_factor)}</div>
              </div>

              {/* Average Win */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Avg Win</div>
                <div className="text-lg font-semibold text-green-500">
                  {formatCurrency(metrics.avg_win)}
                </div>
              </div>

              {/* Average Loss */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Avg Loss</div>
                <div className="text-lg font-semibold text-red-500">
                  {formatCurrency(metrics.avg_loss)}
                </div>
              </div>

              {/* Total Trades */}
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Total Trades</div>
                <div className="text-2xl font-bold">{metrics.total_trades}</div>
                <div className="text-xs text-muted-foreground">
                  {metrics.winning_trades}W / {metrics.losing_trades}L
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Equity Summary */}
      {backtest.initial_equity !== undefined && backtest.final_equity !== undefined && (
        <Card>
          <CardHeader>
            <CardTitle>Equity Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Initial Equity</div>
                <div className="text-xl font-bold">
                  {formatCurrency(backtest.initial_equity)}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">Final Equity</div>
                <div className="text-xl font-bold">
                  {formatCurrency(backtest.final_equity)}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Equity Curve Chart */}
      {trades.length > 0 && equityData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Equity Curve</CardTitle>
            <CardDescription>
              Portfolio value over time ({equityData.length} data points)
              {priceData.length > 0 && ` • Symbol price overlay (${priceData.length} data points)`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EquityChart equityData={equityData} priceData={priceData} height={400} />
          </CardContent>
        </Card>
      )}

      {/* Trades Table */}
      {trades.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Trade History</CardTitle>
            <CardDescription>
              Showing {startIndex + 1}-{Math.min(endIndex, trades.length)} of {trades.length} trades
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <Table>
                <thead>
                  <tr>
                    <th className="text-left p-2">Symbol</th>
                    <th className="text-left p-2">Direction</th>
                    <th className="text-right p-2">Size</th>
                    <th className="text-left p-2">Entry</th>
                    <th className="text-left p-2">Exit</th>
                    <th className="text-right p-2">Entry Price</th>
                    <th className="text-right p-2">Exit Price</th>
                    <th className="text-right p-2">PnL</th>
                    <th className="text-right p-2">PnL %</th>
                    <th className="text-right p-2">Equity</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedTrades.map((trade) => {
                    const pnlPct = calculatePnlPct(trade)
                    const pnl = trade.portfolio_pnl ?? trade.net_pnl
                    return (
                      <tr key={trade.id} className="border-t">
                        <td className="p-2">{trade.symbol}</td>
                        <td className="p-2">
                          <Badge variant={trade.direction === 'long' ? 'default' : 'secondary'}>
                            {trade.direction.toUpperCase()}
                          </Badge>
                        </td>
                        <td className="p-2 text-right text-sm text-muted-foreground">
                          {trade.position_size != null ? trade.position_size.toFixed(3) : '-'}
                        </td>
                        <td className="p-2 text-sm">
                          {new Date(trade.entry_time).toLocaleString()}
                        </td>
                        <td className="p-2 text-sm">
                          {new Date(trade.exit_time).toLocaleString()}
                        </td>
                        <td className="p-2 text-right">{formatCurrency(trade.entry_price)}</td>
                        <td className="p-2 text-right">{formatCurrency(trade.exit_price)}</td>
                        <td
                          className={`p-2 text-right font-semibold ${
                            pnl >= 0 ? 'text-green-500' : 'text-red-500'
                          }`}
                        >
                          {formatCurrency(pnl)}
                        </td>
                        <td
                          className={`p-2 text-right ${
                            pnlPct >= 0 ? 'text-green-500' : 'text-red-500'
                          }`}
                        >
                          {formatPercent(pnlPct)}
                        </td>
                        <td className="p-2 text-right">
                          {trade.equity != null ? formatCurrency(trade.equity) : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </Table>
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4 pt-4 border-t">
                <div className="text-sm text-muted-foreground">
                  Page {currentPage} of {totalPages}
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                  >
                    Next
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Load Trades Button */}
      {trades.length === 0 && isCompleted && onLoadTrades && (
        <Card>
          <CardContent className="pt-6">
            <button
              onClick={onLoadTrades}
              className="w-full py-2 text-sm text-muted-foreground hover:text-foreground"
            >
              Load Trade History
            </button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
