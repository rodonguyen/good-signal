import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { PositionCard } from './PositionCard'
import type { Position, PositionStatus } from '@/types/trading'
import { Filter, TrendingUp } from 'lucide-react'

interface PositionsListProps {
  positions: Position[]
  onClose: (id: string, reason?: string) => Promise<void>
  onUpdateStopLoss: (id: string, stopLoss: number) => Promise<void>
  onUpdateTakeProfit: (id: string, takeProfit: number) => Promise<void>
  isLoading: boolean
}

export function PositionsList({
  positions,
  onClose,
  onUpdateStopLoss,
  onUpdateTakeProfit,
  isLoading,
}: PositionsListProps) {
  const [statusFilter, setStatusFilter] = useState<PositionStatus | 'ALL'>('ALL')

  const filteredPositions = positions.filter((position) =>
    statusFilter === 'ALL' ? true : position.status === statusFilter
  )

  const openPositions = positions.filter((p) => p.status === 'OPEN')
  const totalUnrealizedPnl = openPositions.reduce(
    (sum, p) => sum + p.unrealized_pnl,
    0
  )

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  }

  const getPnlColor = (pnl: number) => {
    if (pnl > 0) return 'text-green-600'
    if (pnl < 0) return 'text-red-600'
    return 'text-gray-600'
  }

  return (
    <div className="space-y-4">
      {/* Header with filters and summary */}
      <Card>
        <CardHeader>
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2">
                <TrendingUp className="h-5 w-5" />
                Positions
              </CardTitle>
              {openPositions.length > 0 && (
                <div className={`text-sm mt-1 ${getPnlColor(totalUnrealizedPnl)}`}>
                  Total Unrealized P&L: {formatCurrency(totalUnrealizedPnl)}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <div className="flex flex-wrap gap-2">
                <Badge
                  variant={statusFilter === 'ALL' ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setStatusFilter('ALL')}
                >
                  All ({positions.length})
                </Badge>
                <Badge
                  variant={statusFilter === 'OPEN' ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setStatusFilter('OPEN')}
                >
                  Open ({positions.filter((p) => p.status === 'OPEN').length})
                </Badge>
                <Badge
                  variant={statusFilter === 'CLOSED' ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setStatusFilter('CLOSED')}
                >
                  Closed ({positions.filter((p) => p.status === 'CLOSED').length})
                </Badge>
                <Badge
                  variant={statusFilter === 'PENDING' ? 'default' : 'outline'}
                  className="cursor-pointer"
                  onClick={() => setStatusFilter('PENDING')}
                >
                  Pending ({positions.filter((p) => p.status === 'PENDING').length})
                </Badge>
              </div>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Positions Grid */}
      {filteredPositions.length === 0 ? (
        <Card>
          <CardContent className="p-12">
            <div className="text-center space-y-2">
              <div className="text-muted-foreground">
                {statusFilter === 'ALL'
                  ? 'No positions found'
                  : `No ${statusFilter.toLowerCase()} positions`}
              </div>
              {statusFilter !== 'ALL' && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setStatusFilter('ALL')}
                >
                  Show all positions
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredPositions.map((position) => (
            <PositionCard
              key={position.id}
              position={position}
              onClose={onClose}
              onUpdateStopLoss={onUpdateStopLoss}
              onUpdateTakeProfit={onUpdateTakeProfit}
              isLoading={isLoading}
            />
          ))}
        </div>
      )}
    </div>
  )
}
