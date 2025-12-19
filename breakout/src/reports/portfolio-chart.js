/**
 * Minimal Portfolio Chart Module
 * Displays candlestick price history with buy/sell markers and TP/SL exit markers
 */

(function() {
    'use strict';

    const PortfolioChart = {
        /**
         * Initialize portfolio chart
         * @param {string} containerId - DOM element ID for chart container
         * @param {Object} chartData - Chart data with candlestickData and trades
         * @param {Object} options - Chart options (height, etc.)
         */
        init(containerId, chartData, options = {}) {
            if (typeof LightweightCharts === 'undefined') {
                console.error('LightweightCharts library not loaded');
                return;
            }

            const container = document.getElementById(containerId);
            if (!container) {
                console.error(`Container not found: ${containerId}`);
                return;
            }

            // Create chart with dark theme
            const chart = LightweightCharts.createChart(container, {
                layout: {
                    background: { color: '#131722' },
                    textColor: '#d1d4dc'
                },
                grid: {
                    vertLines: { color: '#2a2e39' },
                    horzLines: { color: '#2a2e39' }
                },
                crosshair: {
                    mode: LightweightCharts.CrosshairMode.Normal
                },
                timeScale: {
                    timeVisible: true,
                    secondsVisible: true
                },
                width: container.clientWidth,
                height: options.height || 700
            });

            // Add candlestick series
            const { CandlestickSeries } = LightweightCharts;
            const candlestickSeries = chart.addSeries(CandlestickSeries, {
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350'
            });

            // Set candlestick data
            if (chartData.candlestickData && chartData.candlestickData.length > 0) {
                candlestickSeries.setData(chartData.candlestickData);
            }

            // Build markers and level lines from trades
            if (chartData.trades && chartData.trades.length > 0) {
                const markers = [];
                const { LineSeries } = LightweightCharts;
                const processedDays = new Set();

                chartData.trades.forEach(trade => {
                    // Entry marker: green arrowUp for long, red arrowDown for short
                    if (trade.entryTime && trade.direction) {
                        const isLong = trade.direction === 'long';
                        markers.push({
                            time: trade.entryTime,
                            position: 'aboveBar',
                            color: isLong ? '#00ff00' : '#ff0000',
                            shape: isLong ? 'arrowUp' : 'arrowDown',
                            size: 2
                        });
                    }

                    // Exit marker: green circle for profit, red circle for loss
                    if (trade.exitTime) {
                        // Use portfolioPnl if available, otherwise entryPrice - exitPrice
                        const isProfit = trade.portfolioPnl !== undefined 
                            ? trade.portfolioPnl >= 0 
                            : (trade.entryPrice - trade.exitPrice) >= 0;
                        markers.push({
                            time: trade.exitTime,
                            position: 'belowBar',
                            color: isProfit ? '#00ff00' : '#ff0000',
                            shape: 'circle',
                            size: 2
                        });
                    }

                    // Add level lines for days with trades
                    if (trade.entryTime) {
                        const entryDate = new Date(trade.entryTime * 1000);
                        // Find closest 13:00 UTC on the left (before entry time)
                        let start13UTC = new Date(Date.UTC(
                            entryDate.getUTCFullYear(),
                            entryDate.getUTCMonth(),
                            entryDate.getUTCDate(),
                            13, 0, 0, 0
                        ));
                        if (start13UTC.getTime() > entryDate.getTime()) {
                            start13UTC.setUTCDate(start13UTC.getUTCDate() - 1);
                        }
                        const dayKey = start13UTC.getTime() / 1000;
                        
                        if (!processedDays.has(dayKey)) {
                            processedDays.add(dayKey);
                            const endTime = dayKey + 86400; // 24 hours later
                            
                            // Upper level - dotted green
                            if (trade.upperLevel != null) {
                                const upperSeries = chart.addSeries(LineSeries, {
                                    color: '#00ff00',
                                    lineWidth: 1,
                                    lineStyle: LightweightCharts.LineStyle.Dotted,
                                    priceLineVisible: false,
                                    lastValueVisible: false,
                                    crosshairMarkerVisible: false
                                });
                                upperSeries.setData([
                                    { time: dayKey, value: trade.upperLevel },
                                    { time: endTime, value: trade.upperLevel }
                                ]);
                            }
                            
                            // Lower level - dotted orange
                            if (trade.lowerLevel != null) {
                                const lowerSeries = chart.addSeries(LineSeries, {
                                    color: '#ffa500',
                                    lineWidth: 1,
                                    lineStyle: LightweightCharts.LineStyle.Dotted,
                                    priceLineVisible: false,
                                    lastValueVisible: false,
                                    crosshairMarkerVisible: false
                                });
                                lowerSeries.setData([
                                    { time: dayKey, value: trade.lowerLevel },
                                    { time: endTime, value: trade.lowerLevel }
                                ]);
                            }
                            
                            // Stop loss level - dotted yellow
                            if (trade.stopLevel != null) {
                                const stopSeries = chart.addSeries(LineSeries, {
                                    color: '#ffff00',
                                    lineWidth: 1,
                                    lineStyle: LightweightCharts.LineStyle.Dotted,
                                    priceLineVisible: false,
                                    lastValueVisible: false,
                                    crosshairMarkerVisible: false
                                });
                                stopSeries.setData([
                                    { time: dayKey, value: trade.stopLevel },
                                    { time: endTime, value: trade.stopLevel }
                                ]);
                            }
                        }
                    }
                });

                // Add markers using createSeriesMarkers
                if (markers.length > 0) {
                    try {
                        // Try destructuring from LightweightCharts
                        const { createSeriesMarkers } = LightweightCharts;
                        if (typeof createSeriesMarkers === 'function') {
                            createSeriesMarkers(candlestickSeries, markers);
                        } else if (typeof window.createSeriesMarkers === 'function') {
                            // Try global scope
                            window.createSeriesMarkers(candlestickSeries, markers);
                        } else {
                            console.error('createSeriesMarkers not available');
                        }
                    } catch (error) {
                        console.error('Error adding markers:', error);
                    }
                }
            }

            // Fit content to view
            chart.timeScale().fitContent();

            // Handle window resize
            window.addEventListener('resize', () => {
                chart.applyOptions({ width: container.clientWidth });
            });
        }
    };

    // Export to global scope
    window.PortfolioChart = PortfolioChart;

})();
