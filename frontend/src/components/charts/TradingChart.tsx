import { useEffect, useRef } from 'react'
import { createChart, type IChartApi } from 'lightweight-charts'

interface CandlestickData {
  time: number
  open: number
  high: number
  low: number
  close: number
}

interface TradingChartProps {
  data: CandlestickData[]
  width?: number
  height?: number
}

export default function TradingChart({ data, width = 800, height = 400 }: TradingChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!chartContainerRef.current) return

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      width,
      height,
      layout: {
        background: { color: 'transparent' },
        textColor: 'hsl(var(--foreground))',
      },
      grid: {
        vertLines: { color: 'hsl(var(--border))' },
        horzLines: { color: 'hsl(var(--border))' },
      },
    })

    chartRef.current = chart

    // Cleanup
    return () => {
      chart.remove()
    }
  }, [width, height])

  useEffect(() => {
    if (chartRef.current && data.length > 0) {
      // Add candlestick series when data is available
      const candlestickSeries = (chartRef.current as any).addCandlestickSeries?.({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
      })

      if (candlestickSeries) {
        candlestickSeries.setData(data)
        chartRef.current.timeScale().fitContent()
      }
    }
  }, [data])

  return <div ref={chartContainerRef} className="rounded-lg border bg-card" />
}
