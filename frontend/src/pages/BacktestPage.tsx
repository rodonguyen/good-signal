import { useEffect, useState } from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import BacktestForm from '@/components/backtest/BacktestForm'
import BacktestResults from '@/components/backtest/BacktestResults'
import BacktestList from '@/components/backtest/BacktestList'
import { useBacktestStore } from '@/stores/useBacktestStore'
import { useBacktestProgress } from '@/hooks/useBacktestProgress'
import type { BacktestRequest } from '@/types/backtest'

export default function BacktestPage() {
  const [activeTab, setActiveTab] = useState('new')

  // Connect to WebSocket for real-time progress updates
  useBacktestProgress()

  const {
    backtests,
    currentBacktest,
    trades,
    isLoading,
    error,
    fetchBacktests,
    createBacktest,
    setCurrentBacktest,
    fetchTrades,
    deleteBacktest,
    cancelBacktest,
  } = useBacktestStore()

  // Fetch backtests on mount
  useEffect(() => {
    fetchBacktests()
  }, [fetchBacktests])

  const handleSubmit = async (request: BacktestRequest) => {
    try {
      await createBacktest(request)
      // Refresh the list after creation
      await fetchBacktests()
    } catch (error) {
      console.error('Failed to create backtest:', error)
    }
  }

  const handleSelectBacktest = async (backtest: typeof currentBacktest) => {
    setCurrentBacktest(backtest)
    // Fetch full backtest details including metrics
    if (backtest) {
      await useBacktestStore.getState().fetchBacktest(backtest.id)
      // Auto-switch to results tab when selecting a backtest
      setActiveTab('results')
    }
  }

  const handleLoadTrades = () => {
    if (currentBacktest) {
      fetchTrades(currentBacktest.id)
    }
  }

  const handleDelete = async (id: string) => {
    // Find the backtest to check its status
    const backtest = backtests.find((b) => b.id === id)

    // Show helpful message if trying to delete pending/running backtest
    if (backtest && (backtest.status === 'pending' || backtest.status === 'running')) {
      useBacktestStore.setState({
        error: `Cannot delete ${backtest.status} backtest. Please cancel it first using the cancel button (X icon).`,
      })
      return
    }

    try {
      await deleteBacktest(id)
      // If deleted backtest was selected, clear selection
      if (currentBacktest?.id === id) {
        setCurrentBacktest(null)
      }
      // Clear any previous errors
      useBacktestStore.setState({ error: null })
    } catch (error) {
      console.error('Failed to delete backtest:', error)
      // Error will be set by the store
    }
  }

  const handleCancel = async (id: string) => {
    try {
      await cancelBacktest(id)
      // Refresh the list to show updated status
      await fetchBacktests()
      // Clear any previous errors
      useBacktestStore.setState({ error: null })
    } catch (error) {
      console.error('Failed to cancel backtest:', error)
      // Error will be set by the store
    }
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-3xl font-bold">Backtest Strategy</h1>
      </div>

      {error && (
        <div className="bg-destructive/10 text-destructive px-4 py-3 rounded-lg">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
        <TabsList>
          <TabsTrigger value="new">New Backtest</TabsTrigger>
          <TabsTrigger value="results">Results</TabsTrigger>
        </TabsList>

        <TabsContent value="new" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Backtest Form */}
            <div className="lg:col-span-2">
              <BacktestForm onSubmit={handleSubmit} isLoading={isLoading} />
            </div>

            {/* Backtest List */}
            <div className="lg:col-span-1">
              <BacktestList
                backtests={backtests}
                selectedId={currentBacktest?.id}
                onSelect={handleSelectBacktest}
                onDelete={handleDelete}
                onCancel={handleCancel}
                isLoading={isLoading}
              />
            </div>
          </div>
        </TabsContent>

        <TabsContent value="results" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Results */}
            <div className="lg:col-span-2">
              {currentBacktest ? (
                <BacktestResults
                  backtest={currentBacktest}
                  trades={trades}
                  onLoadTrades={handleLoadTrades}
                />
              ) : (
                <div className="text-center py-12 text-muted-foreground border rounded-lg">
                  <p className="text-lg">No backtest selected</p>
                  <p className="text-sm">Select a backtest from the list to view results</p>
                </div>
              )}
            </div>

            {/* Backtest List - Always visible */}
            <div className="lg:col-span-1">
              <BacktestList
                backtests={backtests}
                selectedId={currentBacktest?.id}
                onSelect={handleSelectBacktest}
                onDelete={handleDelete}
                onCancel={handleCancel}
                isLoading={isLoading}
              />
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
