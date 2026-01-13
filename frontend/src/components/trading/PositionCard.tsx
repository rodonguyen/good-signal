import { useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import type { Position } from '@/types/trading'
import { TrendingUp, TrendingDown, X, Edit2 } from 'lucide-react'

interface PositionCardProps {
  position: Position
  onClose: (id: string, reason?: string) => Promise<void>
  onUpdateStopLoss: (id: string, stopLoss: number) => Promise<void>
  onUpdateTakeProfit: (id: string, takeProfit: number) => Promise<void>
  isLoading: boolean
}

export function PositionCard({
  position,
  onClose,
  onUpdateStopLoss,
  onUpdateTakeProfit,
  isLoading,
}: PositionCardProps) {
  const [closeDialogOpen, setCloseDialogOpen] = useState(false)
  const [closeReason, setCloseReason] = useState('')
  const [editStopLoss, setEditStopLoss] = useState(false)
  const [editTakeProfit, setEditTakeProfit] = useState(false)
  const [stopLossValue, setStopLossValue] = useState(position.stop_loss?.toString() || '')
  const [takeProfitValue, setTakeProfitValue] = useState(position.take_profit?.toString() || '')

  const handleClose = async () => {
    await onClose(position.id, closeReason || undefined)
    setCloseReason('')
    setCloseDialogOpen(false)
  }

  const handleUpdateStopLoss = async () => {
    const value = parseFloat(stopLossValue)
    if (!isNaN(value) && value > 0) {
      await onUpdateStopLoss(position.id, value)
      setEditStopLoss(false)
    }
  }

  const handleUpdateTakeProfit = async () => {
    const value = parseFloat(takeProfitValue)
    if (!isNaN(value) && value > 0) {
      await onUpdateTakeProfit(position.id, value)
      setEditTakeProfit(false)
    }
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value)
  }

  const formatQuantity = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      minimumFractionDigits: 4,
      maximumFractionDigits: 8,
    }).format(value)
  }

  const getPnlColor = (pnl: number) => {
    if (pnl > 0) return 'text-green-600'
    if (pnl < 0) return 'text-red-600'
    return 'text-gray-600'
  }

  const getPnlPercentage = () => {
    const pnlPercent = (position.unrealized_pnl / (position.entry_price * position.quantity)) * 100
    return pnlPercent.toFixed(2)
  }

  return (
    <Card className="hover:shadow-lg transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              {position.direction === 'LONG' ? (
                <TrendingUp className="h-5 w-5 text-green-600" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-600" />
              )}
              {position.symbol}
            </CardTitle>
            <div className="flex items-center gap-2">
              <Badge
                variant={position.direction === 'LONG' ? 'default' : 'destructive'}
              >
                {position.direction}
              </Badge>
              <Badge variant="outline">{position.status}</Badge>
              {position.strategy && (
                <Badge variant="secondary">{position.strategy}</Badge>
              )}
            </div>
          </div>
          {position.status === 'OPEN' && (
            <Dialog open={closeDialogOpen} onOpenChange={setCloseDialogOpen}>
              <DialogTrigger
                className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-9 w-9"
                disabled={isLoading}
              >
                <X className="h-4 w-4" />
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Close Position</DialogTitle>
                  <DialogDescription>
                    Close {position.symbol} {position.direction} position?
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <Input
                    placeholder="Reason for closing (optional)..."
                    value={closeReason}
                    onChange={(e) => setCloseReason(e.target.value)}
                  />
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setCloseDialogOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleClose}
                    disabled={isLoading}
                  >
                    Close Position
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Price Information */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <div className="text-xs text-muted-foreground mb-1">Entry Price</div>
            <div className="font-semibold">{formatCurrency(position.entry_price)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Current Price</div>
            <div className="font-semibold">{formatCurrency(position.current_price)}</div>
          </div>
        </div>

        {/* Quantity */}
        <div>
          <div className="text-xs text-muted-foreground mb-1">Quantity</div>
          <div className="font-semibold">{formatQuantity(position.quantity)}</div>
        </div>

        {/* P&L */}
        <div className="rounded-lg bg-muted p-3">
          <div className="text-xs text-muted-foreground mb-1">Unrealized P&L</div>
          <div className={`text-2xl font-bold ${getPnlColor(position.unrealized_pnl)}`}>
            {formatCurrency(position.unrealized_pnl)}
            <span className="text-sm ml-2">
              ({getPnlPercentage()}%)
            </span>
          </div>
        </div>

        {/* Stop Loss */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs text-muted-foreground">Stop Loss</div>
            {position.status === 'OPEN' && !editStopLoss && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEditStopLoss(true)}
              >
                <Edit2 className="h-3 w-3" />
              </Button>
            )}
          </div>
          {editStopLoss ? (
            <div className="flex gap-2">
              <Input
                type="number"
                step="0.01"
                value={stopLossValue}
                onChange={(e) => setStopLossValue(e.target.value)}
                placeholder="Enter stop loss..."
              />
              <Button
                size="sm"
                onClick={handleUpdateStopLoss}
                disabled={isLoading}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setEditStopLoss(false)
                  setStopLossValue(position.stop_loss?.toString() || '')
                }}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <div className="font-semibold">
              {position.stop_loss ? formatCurrency(position.stop_loss) : 'Not set'}
            </div>
          )}
        </div>

        {/* Take Profit */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs text-muted-foreground">Take Profit</div>
            {position.status === 'OPEN' && !editTakeProfit && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setEditTakeProfit(true)}
              >
                <Edit2 className="h-3 w-3" />
              </Button>
            )}
          </div>
          {editTakeProfit ? (
            <div className="flex gap-2">
              <Input
                type="number"
                step="0.01"
                value={takeProfitValue}
                onChange={(e) => setTakeProfitValue(e.target.value)}
                placeholder="Enter take profit..."
              />
              <Button
                size="sm"
                onClick={handleUpdateTakeProfit}
                disabled={isLoading}
              >
                Save
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setEditTakeProfit(false)
                  setTakeProfitValue(position.take_profit?.toString() || '')
                }}
              >
                Cancel
              </Button>
            </div>
          ) : (
            <div className="font-semibold">
              {position.take_profit ? formatCurrency(position.take_profit) : 'Not set'}
            </div>
          )}
        </div>

        {/* Timestamps */}
        <div className="text-xs text-muted-foreground space-y-1 pt-2 border-t">
          <div>Opened: {new Date(position.opened_at).toLocaleString()}</div>
          {position.closed_at && (
            <div>Closed: {new Date(position.closed_at).toLocaleString()}</div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
