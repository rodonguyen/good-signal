import { useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { RiskControls } from '@/components/trading/RiskControls'
import { PositionsList } from '@/components/trading/PositionsList'
import { useTradingStore } from '@/stores/useTradingStore'
import { AlertCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function LiveTradingPage() {
  const {
    riskState,
    positions,
    isLoading,
    error,
    fetchRiskState,
    toggleKillSwitch,
    updateLimits,
    fetchPositions,
    closePosition,
    updatePositionStopLoss,
    updatePositionTakeProfit,
    clearError,
  } = useTradingStore()

  // Initial data fetch
  useEffect(() => {
    fetchRiskState()
    fetchPositions({ status: 'OPEN' })
  }, [fetchRiskState, fetchPositions])

  // Auto-refresh positions every 5 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      if (!isLoading) {
        fetchPositions({ status: 'OPEN' })
        fetchRiskState()
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [fetchPositions, fetchRiskState, isLoading])

  const handleRefresh = () => {
    fetchRiskState()
    fetchPositions()
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h1 className="text-3xl font-bold">Live Trading</h1>
          <p className="text-muted-foreground mt-1">
            Monitor and manage your trading positions in real-time
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            onClick={handleRefresh}
            disabled={isLoading}
          >
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Badge
            variant={riskState?.kill_switch_active ? 'destructive' : 'secondary'}
          >
            {riskState?.kill_switch_active ? 'Trading Halted' : 'Active'}
          </Badge>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <Card className="border-red-500 bg-red-50">
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-5 w-5 text-red-600 mt-0.5" />
                <div>
                  <div className="font-semibold text-red-900">Error</div>
                  <div className="text-sm text-red-800">{error}</div>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={clearError}
              >
                Dismiss
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Risk Controls */}
      <RiskControls
        riskState={riskState}
        isLoading={isLoading}
        onToggleKillSwitch={toggleKillSwitch}
        onUpdateLimits={updateLimits}
      />

      {/* Positions List */}
      <PositionsList
        positions={positions}
        onClose={closePosition}
        onUpdateStopLoss={updatePositionStopLoss}
        onUpdateTakeProfit={updatePositionTakeProfit}
        isLoading={isLoading}
      />

      {/* Auto-refresh indicator */}
      <div className="text-center text-xs text-muted-foreground">
        Auto-refreshing every 5 seconds
      </div>
    </div>
  )
}
