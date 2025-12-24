1 month data, 0.4, 0.1 wins 50%, PnL 441

Then do step 5 with html + JS, but just show:
- price candlestick history
- buy sell markers on chart (arrow up green or arrow down red) based on trades.direction, trades.entryTime, trades.entryPrice.
- stop loss or take profit markers on chart (red or green cicles) based on trades.exitReason, trades.exitTime, trades.exitPrice.
- From trades.entryTime to trades.exitTime, show dotted lines of upperlevel, lowerlevel
- For each day that has trades, show the upperlevel from trades.upperLevel with dotted green line, lowerlevel from trades.lowerLevel with dotted orange line, the SL level from trades.stopLevel with dotted yellow line

Then do step 6 with html + JS, but just show:
- price candlestick history
- buy sell markers on chart (arrow up green / arrow down red)
- stop loss or take profit markers on chart (cicles)
- the breakout level, SL level of the day that has trades

- Analyse and confirm if portfolio report from @portfolio analysis is using allowed trades or all trades 
filter True range of the last 9 hours is <0.06%
