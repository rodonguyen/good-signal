import { useEffect, useRef } from 'react'
import { createChart, LineSeries, type IChartApi, type LineData } from 'lightweight-charts'

interface EquityDataPoint {
  time: string
  value: number
}

interface PriceDataPoint {
  time: string
  value: number
}

interface EquityChartProps {
  equityData: EquityDataPoint[]
  priceData?: PriceDataPoint[]  // Optional symbol price data
  height?: number
}

/**
 * EquityChart - Displays equity curve as a line chart using TradingView lightweight-charts
 *
 * Usage:
 * <EquityChart
 *   equityData={[
 *     { time: '2024-01-01', value: 10000 },
 *     { time: '2024-01-02', value: 10250 }
 *   ]}
 * />
 */
export default function EquityChart({ equityData, priceData, height = 300 }: EquityChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const equitySeriesRef = useRef<any>(null)
  const priceSeriesRef = useRef<any>(null)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    const container = chartContainerRef.current

    // Create chart with dark theme
    const chart = createChart(container, {
      height,
      layout: {
        background: { color: '#1a1a1a' },
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { color: '#2a2a2a' },
        horzLines: { color: '#2a2a2a' },
      },
      rightPriceScale: {
        borderColor: '#2a2a2a',
      },
      timeScale: {
        borderColor: '#2a2a2a',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        vertLine: {
          color: '#6b7280',
          width: 1,
          style: 1,
          labelBackgroundColor: '#3b82f6',
        },
        horzLine: {
          color: '#6b7280',
          width: 1,
          style: 1,
          labelBackgroundColor: '#3b82f6',
        },
      },
    })

    chartRef.current = chart

    // Add line series for equity curve on right axis
    const equitySeries = chart.addSeries(LineSeries, {
      color: '#3b82f6',
      lineWidth: 2,
      crosshairMarkerVisible: true,
      crosshairMarkerRadius: 4,
      crosshairMarkerBorderColor: '#3b82f6',
      crosshairMarkerBackgroundColor: '#ffffff',
      lastValueVisible: true,
      priceLineVisible: true,
      priceScaleId: 'right',
      priceFormat: {
        type: 'custom',
        formatter: (price: number) => `$${price.toFixed(2)}`,
      },
    })

    equitySeriesRef.current = equitySeries

    // Add line series for symbol price on left axis (if priceData provided)
    if (priceData && priceData.length > 0) {
      const priceSeries = chart.addSeries(LineSeries, {
        color: '#f59e0b',  // Orange color for price
        lineWidth: 1.5,
        crosshairMarkerVisible: true,
        crosshairMarkerRadius: 3,
        crosshairMarkerBorderColor: '#f59e0b',
        crosshairMarkerBackgroundColor: '#ffffff',
        lastValueVisible: true,
        priceLineVisible: false,
        priceScaleId: 'left',
        priceFormat: {
          type: 'custom',
          formatter: (price: number) => `$${price.toFixed(2)}`,
        },
      })

      priceSeriesRef.current = priceSeries
    }

    // Auto-resize with container
    resizeObserverRef.current = new ResizeObserver((entries) => {
      if (entries.length === 0 || entries[0].target !== container) return
      const { width } = entries[0].contentRect
      chart.applyOptions({ width })
    })

    resizeObserverRef.current.observe(container)

    // Cleanup on unmount
    return () => {
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect()
      }
      if (chartRef.current) {
        chartRef.current.remove()
      }
      chartRef.current = null
      equitySeriesRef.current = null
      priceSeriesRef.current = null
    }
  }, [height, priceData])

  // Update equity data when equityData changes
  useEffect(() => {
    if (!equitySeriesRef.current || equityData.length === 0) return

    // Convert string dates to timestamps for lightweight-charts
    const chartData: LineData[] = equityData.map((point) => ({
      time: point.time as any, // lightweight-charts accepts ISO string or timestamp
      value: point.value,
    }))

    equitySeriesRef.current.setData(chartData)

    // Fit content to show all data
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent()
    }
  }, [equityData])

  // Update price data when priceData changes
  useEffect(() => {
    if (!priceSeriesRef.current || !priceData || priceData.length === 0) return

    // Convert string dates to timestamps for lightweight-charts
    const chartData: LineData[] = priceData.map((point) => ({
      time: point.time as any,
      value: point.value,
    }))

    priceSeriesRef.current.setData(chartData)
  }, [priceData])

  return (
    <div
      ref={chartContainerRef}
      className="rounded-lg border border-border bg-[#1a1a1a]"
      style={{ minHeight: height }}
    />
  )
}
