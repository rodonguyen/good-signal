# Full stack app:

The current code base includes bare CLI execution of backtesting and signal notification.

easy initiate backtest from one of the strategies, load backtest result history, start live trading, adjust config for backtest and live trading, show live trading position.

ignore breakout_ARCHIVED and bayesian_method_poc for now

# Major features:

Backtest:
- able to multi-select the datasets to run backtest on
- multi-select the strategies 
- multi-select filters
- set any other configs: fees, 
- show backtest results
- saved backtest results locally with all the chosen configs so that can re-load if choose the same configs to backtest later: data range, data length, trading symbol, strategy, filters,...
- configs for portfolio: risk per trade, initial equity
- visualise backtest results (use tradingview lightweight-charts https://tradingview.github.io/lightweight-charts/tutorials) and stats 

Live trading:
- allow to choose configs similar to backtest, symbol to trade, use bybit via cctx api
- use the response or api to record positions locally
- display current position, pnl on screen for easy view
- send trade initiation, fill notification via discord channel (with PNL if close position) 

Technical details:
- backend: use Python based framework
- frontend: use something lightweight, easy to show complex scientific, plot, chart and trading data, evaluate react, tailwind, vite, shadcn