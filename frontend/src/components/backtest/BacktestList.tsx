import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { BacktestResult } from '@/types/backtest'
import { Trash2, Eye } from 'lucide-react'

interface BacktestListProps {
  backtests: BacktestResult[]
  selectedId?: string
  onSelect: (backtest: BacktestResult) => void
  onDelete: (id: string) => void
  isLoading?: boolean
}

export default function BacktestList({
  backtests,
  selectedId,
  onSelect,
  onDelete,
  isLoading = false,
}: BacktestListProps) {
  const getStatusBadge = (status: string) => {
    const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
      pending: 'secondary',
      running: 'default',
      completed: 'outline',
      failed: 'destructive',
      cancelled: 'secondary',
    }
    return (
      <Badge variant={variants[status] || 'default'} className="text-xs">
        {status.toUpperCase()}
      </Badge>
    )
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const formatMetric = (value: number | undefined, suffix = '') => {
    if (value === undefined) return 'N/A'
    return `${value.toFixed(2)}${suffix}`
  }

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Saved Backtests</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center text-muted-foreground py-8">Loading backtests...</div>
        </CardContent>
      </Card>
    )
  }

  if (!backtests || backtests.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Saved Backtests</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center text-muted-foreground py-8">
            No backtests yet. Create one to get started!
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved Backtests</CardTitle>
        <CardDescription>{backtests.length} backtests</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3">
          {backtests.map((backtest) => (
            <div
              key={backtest.id}
              className={`
                border rounded-lg p-4 transition-colors cursor-pointer
                ${
                  selectedId === backtest.id
                    ? 'border-primary bg-primary/5'
                    : 'border-border hover:border-primary/50'
                }
              `}
              onClick={() => onSelect(backtest)}
            >
              <div className="space-y-3">
                {/* Header */}
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-1 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium">{backtest.symbols?.join(', ') || 'Unknown'}</span>
                      {getStatusBadge(backtest.status)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {formatDate(backtest.created_at)}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        onSelect(backtest)
                      }}
                      className="h-8 w-8 p-0"
                    >
                      <Eye className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        onDelete(backtest.id)
                      }}
                      className="h-8 w-8 p-0 hover:bg-destructive hover:text-destructive-foreground"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </div>

                {/* Strategy Info */}
                {backtest.strategies && backtest.strategies.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {backtest.strategies.map((strategy, idx) => (
                      <Badge key={idx} variant="secondary" className="text-xs">
                        {strategy.type}
                      </Badge>
                    ))}
                  </div>
                )}

                {/* Metrics Preview */}
                {backtest.metrics && (
                  <div className="grid grid-cols-3 gap-2 pt-2 border-t">
                    <div className="text-center">
                      <div className="text-xs text-muted-foreground">Return</div>
                      <div
                        className={`text-sm font-semibold ${
                          backtest.metrics.total_return_pct >= 0
                            ? 'text-green-500'
                            : 'text-red-500'
                        }`}
                      >
                        {formatMetric(backtest.metrics.total_return_pct * 100, '%')}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs text-muted-foreground">Win Rate</div>
                      <div className="text-sm font-semibold">
                        {formatMetric(backtest.metrics.win_rate * 100, '%')}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-xs text-muted-foreground">Trades</div>
                      <div className="text-sm font-semibold">{backtest.metrics.total_trades}</div>
                    </div>
                  </div>
                )}

                {/* Progress Bar for Running Backtests */}
                {backtest.status === 'running' && (
                  <div className="space-y-1">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>Progress</span>
                      <span>{backtest.progress}%</span>
                    </div>
                    <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary transition-all duration-300"
                        style={{ width: `${backtest.progress}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
