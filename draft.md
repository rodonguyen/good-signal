Try supertrend again in 4h timeframe
filter idea: use some indicator to identify strong trend in higher timeframe (day)
see what filters he used


WFO: should save results somewhere after each cycle to save memory, analyse code and remove unnecessary data/variables from memory if not used
```python
Portfolio Summary:
  Total trades: 143
  Initial capital: $1,000.00
  Final equity: $535.82
  Total return: -46.42%
  Max drawdown: -53.52%
Building portfolio...
  Loaded 137 trades for ETHUSDT
  Total trades loaded: 137
  Applied position sizing: risk_based
  Saved to: data\portfolio\portfolio_trades.csv

Portfolio Summary:
  Total trades: 137
  Initial capital: $1,000.00
  Final equity: $312.03
  Total return: -68.80%
  Max drawdown: -81.70%
Building portfolio...
  Loaded 137 trades for ETHUSDT
  Total trades loaded: 137
  Applied position sizing: risk_based
  Saved to: data\portfolio\portfolio_trades.csv

Portfolio Summary:
  Total trades: 137
  Initial capital: $1,000.00
  Final equity: $341.38
  Total return: -65.86%
  Max drawdown: -78.51%
Traceback (most recent call last):
  File "E:\Personal\GitHub\good-signal\wfo.py", line 320, in <module>
    main()
    ~~~~^^
  File "E:\Personal\GitHub\good-signal\wfo.py", line 298, in main
    cycle_results = optimizer.run_all_cycles()
  File "E:\Personal\GitHub\good-signal\src\backtest\optimization\walk_forward.py", line 449, in run_all_cycles
    logger.info(f"Processing cycle {cycle_num}/{total_cycles}")
             ~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Personal\GitHub\good-signal\src\backtest\optimization\walk_forward.py", line 377, in run_cycle
    logger.info(f"  Progress: {i}/{len(param_grid)} ({i/len(param_grid)*100:.1f}%)")
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Personal\GitHub\good-signal\src\backtest\optimization\walk_forward.py", line 240, in _run_single_backtest
    trades_df = self.strategy.generate_trades(minute_df, context=ctx, params=strategy_params)
  File "E:\Personal\GitHub\good-signal\src\backtest\strategies\atr_breakout.py", line 73, in generate_trades
    daily_bars = indicator.calculate(minute_df)
  File "E:\Personal\GitHub\good-signal\src\indicators\atr_breakout_levels.py", line 93, in calculate
    daily_bars = aggregate_24h_periods(df, day_start_hour=self.day_start_hour)
  File "E:\Personal\GitHub\good-signal\src\backtest\utils\crypto_day_utils.py", line 54, in aggregate_24h_periods
    df["day"] = df["timestamp"].apply(lambda x: define_crypto_day(x, day_start_hour))
                ~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\RodoNguyen\AppData\Local\Programs\Python\Python314\Lib\site-packages\pandas\core\series.py", line 4943, in apply
    ).apply()
      ~~~~~^^
  File "C:\Users\RodoNguyen\AppData\Local\Programs\Python\Python314\Lib\site-packages\pandas\core\apply.py", line 1422, in apply
    return self.apply_standard()
           ~~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\RodoNguyen\AppData\Local\Programs\Python\Python314\Lib\site-packages\pandas\core\apply.py", line 1502, in apply_standard
    mapped = obj._map_values(
        mapper=curried, na_action=action, convert=self.convert_dtype
    )
  File "C:\Users\RodoNguyen\AppData\Local\Programs\Python\Python314\Lib\site-packages\pandas\core\base.py", line 923, in _map_values
    return arr.map(mapper, na_action=na_action)
           ~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\RodoNguyen\AppData\Local\Programs\Python\Python314\Lib\site-packages\pandas\core\arrays\_mixins.py", line 81, in method
    return meth(self, *args, **kwargs)
  File "C:\Users\RodoNguyen\AppData\Local\Programs\Python\Python314\Lib\site-packages\pandas\core\arrays\datetimelike.py", line 763, in map
    result = map_array(self, mapper, na_action=na_action)
  File "C:\Users\RodoNguyen\AppData\Local\Programs\Python\Python314\Lib\site-packages\pandas\core\algorithms.py", line 1743, in map_array
    return lib.map_infer(values, mapper, convert=convert)
           ~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "pandas/_libs/lib.pyx", line 3008, in pandas._libs.lib.map_infer
  File "pandas/_libs/lib.pyx", line 2555, in pandas._libs.lib.maybe_convert_objects
numpy._core._exceptions._ArrayMemoryError: Unable to allocate 2.00 MiB for an array with shape (261820,) and data type float64
```