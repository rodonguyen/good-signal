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
import type { RiskState } from '@/types/trading'
import { AlertTriangle, ShieldAlert, ShieldCheck } from 'lucide-react'

interface RiskControlsProps {
  riskState: RiskState | null
  isLoading: boolean
  onToggleKillSwitch: (active: boolean, reason?: string) => Promise<void>
  onUpdateLimits?: (limits: RiskState['risk_limits']) => Promise<void>
}

export function RiskControls({
  riskState,
  isLoading,
  onToggleKillSwitch,
  onUpdateLimits,
}: RiskControlsProps) {
  const [killSwitchReason, setKillSwitchReason] = useState('')
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editMode, setEditMode] = useState(false)
  const defaultLimits = {
    max_daily_loss: 1000,
    max_positions: 5,
    max_exposure: 50000,
    max_position_size: 10000,
  }
  const [limits, setLimits] = useState(riskState?.risk_limits ?? defaultLimits)

  const handleKillSwitchToggle = async () => {
    if (!riskState) return

    if (!riskState.kill_switch_active) {
      // Activating - need reason
      if (!killSwitchReason.trim()) {
        return
      }
      await onToggleKillSwitch(true, killSwitchReason)
      setKillSwitchReason('')
      setDialogOpen(false)
    } else {
      // Deactivating
      await onToggleKillSwitch(false)
    }
  }

  const handleUpdateLimits = async () => {
    if (!limits || !onUpdateLimits) return
    await onUpdateLimits(limits)
    setEditMode(false)
  }

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

  if (!riskState) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center text-muted-foreground">
            Loading risk controls...
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      {/* Kill Switch Card */}
      <Card className={riskState.kill_switch_active ? 'border-red-500 bg-red-50' : ''}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              {riskState.kill_switch_active ? (
                <ShieldAlert className="h-5 w-5 text-red-600" />
              ) : (
                <ShieldCheck className="h-5 w-5 text-green-600" />
              )}
              Kill Switch
            </CardTitle>
            <Badge
              variant={riskState.kill_switch_active ? 'destructive' : 'secondary'}
            >
              {riskState.kill_switch_active ? 'ACTIVE' : 'INACTIVE'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {riskState.kill_switch_active && riskState.kill_switch_reason && (
            <div className="rounded-lg bg-red-100 p-3 text-sm text-red-800">
              <strong>Reason:</strong> {riskState.kill_switch_reason}
              {riskState.kill_switch_activated_at && (
                <div className="mt-1 text-xs">
                  Activated: {new Date(riskState.kill_switch_activated_at).toLocaleString()}
                </div>
              )}
            </div>
          )}

          {riskState.kill_switch_active ? (
            <Button
              onClick={handleKillSwitchToggle}
              disabled={isLoading}
              variant="outline"
              className="w-full"
            >
              Deactivate Kill Switch
            </Button>
          ) : (
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger
                className="inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90 h-9 px-4 py-2 w-full"
                disabled={isLoading}
              >
                <AlertTriangle className="mr-2 h-4 w-4" />
                Activate Kill Switch
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Activate Kill Switch</DialogTitle>
                  <DialogDescription>
                    This will immediately stop all trading activity. Please provide a reason.
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-4">
                  <Input
                    placeholder="Reason for activation..."
                    value={killSwitchReason}
                    onChange={(e) => setKillSwitchReason(e.target.value)}
                  />
                </div>
                <DialogFooter>
                  <Button
                    variant="outline"
                    onClick={() => setDialogOpen(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="destructive"
                    onClick={handleKillSwitchToggle}
                    disabled={!killSwitchReason.trim() || isLoading}
                  >
                    Activate
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </CardContent>
      </Card>

      {/* Risk Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Daily P&L
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${getPnlColor(riskState.daily_pnl)}`}>
              {formatCurrency(riskState.daily_pnl)}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Max Loss: {formatCurrency(riskState.risk_limits?.max_daily_loss ?? defaultLimits.max_daily_loss)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Open Positions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {riskState.total_open_positions} / {riskState.risk_limits?.max_positions ?? defaultLimits.max_positions}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Current / Maximum
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Exposure
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {formatCurrency(riskState.total_exposure)}
            </div>
            <div className="text-xs text-muted-foreground mt-1">
              Max: {formatCurrency(riskState.risk_limits?.max_exposure ?? defaultLimits.max_exposure)}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Risk Limits Editor */}
      {onUpdateLimits && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Risk Limits</CardTitle>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (editMode) {
                    setLimits(riskState.risk_limits ?? defaultLimits)
                  }
                  setEditMode(!editMode)
                }}
              >
                {editMode ? 'Cancel' : 'Edit'}
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Max Daily Loss</label>
                <Input
                  type="number"
                  value={limits?.max_daily_loss || 0}
                  onChange={(e) =>
                    setLimits((prev) => ({
                      ...prev!,
                      max_daily_loss: parseFloat(e.target.value),
                    }))
                  }
                  disabled={!editMode}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Max Positions</label>
                <Input
                  type="number"
                  value={limits?.max_positions || 0}
                  onChange={(e) =>
                    setLimits((prev) => ({
                      ...prev!,
                      max_positions: parseInt(e.target.value),
                    }))
                  }
                  disabled={!editMode}
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Max Exposure</label>
                <Input
                  type="number"
                  value={limits?.max_exposure || 0}
                  onChange={(e) =>
                    setLimits((prev) => ({
                      ...prev!,
                      max_exposure: parseFloat(e.target.value),
                    }))
                  }
                  disabled={!editMode}
                />
              </div>
              {limits?.max_position_size !== undefined && (
                <div className="space-y-2">
                  <label className="text-sm font-medium">Max Position Size</label>
                  <Input
                    type="number"
                    value={limits.max_position_size || 0}
                    onChange={(e) =>
                      setLimits((prev) => ({
                        ...prev!,
                        max_position_size: parseFloat(e.target.value),
                      }))
                    }
                    disabled={!editMode}
                  />
                </div>
              )}
            </div>
            {editMode && (
              <div className="mt-4">
                <Button
                  onClick={handleUpdateLimits}
                  disabled={isLoading}
                  className="w-full"
                >
                  Save Changes
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
