"""Data module alias for historical_data_provider."""

# Create module aliases FIRST before any imports to avoid circular dependencies
import sys
import importlib.util
from pathlib import Path

_provider_path = Path(__file__).parent.parent / "historical_data_provider"

# Create cache module alias FIRST (needed by ohlcv_store)
cache_spec = importlib.util.spec_from_file_location(
    "src.backtest.data.cache",
    _provider_path / "cache.py"
)
cache_module = importlib.util.module_from_spec(cache_spec)
sys.modules["src.backtest.data.cache"] = cache_module
cache_spec.loader.exec_module(cache_module)

# Create base module alias
base_spec = importlib.util.spec_from_file_location(
    "src.backtest.data.base",
    _provider_path / "base.py"
)
base_module = importlib.util.module_from_spec(base_spec)
sys.modules["src.backtest.data.base"] = base_module
base_spec.loader.exec_module(base_module)

# Create bybit_provider module alias
bybit_provider_spec = importlib.util.spec_from_file_location(
    "src.backtest.data.bybit_provider",
    _provider_path / "bybit_provider.py"
)
bybit_provider_module = importlib.util.module_from_spec(bybit_provider_spec)
sys.modules["src.backtest.data.bybit_provider"] = bybit_provider_module
bybit_provider_spec.loader.exec_module(bybit_provider_module)

# Create bybit_downloader module alias
bybit_downloader_spec = importlib.util.spec_from_file_location(
    "src.backtest.data.bybit_downloader",
    _provider_path / "bybit_downloader.py"
)
bybit_downloader_module = importlib.util.module_from_spec(bybit_downloader_spec)
sys.modules["src.backtest.data.bybit_downloader"] = bybit_downloader_module
bybit_downloader_spec.loader.exec_module(bybit_downloader_module)

# NOW we can import ohlcv_store (it needs cache to be available)
ohlcv_store_spec = importlib.util.spec_from_file_location(
    "src.backtest.data.ohlcv_store",
    _provider_path / "ohlcv_store.py"
)
ohlcv_store_module = importlib.util.module_from_spec(ohlcv_store_spec)
sys.modules["src.backtest.data.ohlcv_store"] = ohlcv_store_module
ohlcv_store_spec.loader.exec_module(ohlcv_store_module)

# Re-export for convenience
from src.backtest.historical_data_provider.ohlcv_store import OhlcvStore, OhlcvStoreConfig
from src.backtest.historical_data_provider.bybit_provider import BybitDataProvider
from src.backtest.historical_data_provider.base import HistoricalDataProvider
from src.backtest.historical_data_provider.bybit_downloader import BybitDownloader
from src.backtest.historical_data_provider.cache import CacheKey, FileDependency, ParquetDataFrameCache

__all__ = [
    "OhlcvStore",
    "OhlcvStoreConfig",
    "BybitDataProvider",
    "HistoricalDataProvider",
    "BybitDownloader",
    "CacheKey",
    "FileDependency",
    "ParquetDataFrameCache",
]

