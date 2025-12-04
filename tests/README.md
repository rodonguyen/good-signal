# Test Suite

## Running Tests

### Run all tests:
```bash
python -m pytest
```

### Run with coverage:
```bash
python -m pytest --cov=src --cov-report=html
```

### Run specific test file:
```bash
python -m pytest tests/test_bollinger_bands.py
```

### Run specific test:
```bash
python -m pytest tests/test_bb_trendline_strategy.py::test_buy_signal_upper_breakout
```

### Run with markers:
```bash
python -m pytest -m unit          # Only unit tests
python -m pytest -m integration   # Only integration tests
python -m pytest -m "not slow"    # Skip slow tests
```

## Test Structure

- `conftest.py` - Shared fixtures and configuration
- `test_bollinger_bands.py` - Bollinger Bands indicator tests
- `test_bb_trendline_strategy.py` - Strategy logic tests
- `test_bybit_fetcher.py` - Data fetcher tests (mocked)

## Fixtures

- `sample_ohlcv_data` - Sample OHLCV DataFrame
- `sample_ohlcv_with_bb` - OHLCV with Bollinger Bands calculated
- `mock_bybit_fetcher` - Mocked BybitFetcher (no real API calls)
- `mock_discord_notifier` - Mocked DiscordNotifier (no real webhooks)

