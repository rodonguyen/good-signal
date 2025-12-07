"""
Main orchestrator for trading bot.
Schedules periodic strategy execution and coordinates all components.
"""

import schedule
import time
import yaml
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

from src.data.bybit_fetcher import BybitFetcher
from src.indicators.bollinger_bands import BollingerBands
from src.indicators.zscore import ZScoreIndicator
from src.strategies.bb_trendline import BBTrendlineStrategy
from src.strategies.spike_detection import SpikeDetectionStrategy
from src.notifiers.discord_notifier import DiscordNotifier
from src.utils.datetime_utils import to_local_timezone

logger = logging.getLogger(__name__)


class TradingScheduler:
    """
    Main orchestrator for trading signal bot.

    Responsibilities:
    - Load configuration files
    - Initialize components (fetcher, notifier)
    - Schedule periodic strategy execution
    - Coordinate: Fetch → Calculate → Signal → Notify → Log
    - Handle errors and edge cases

    Usage:
        scheduler = TradingScheduler('config/assets.yaml', 'config/discord.yaml')
        scheduler.start()  # Runs forever
    """

    def __init__(self, config_path: str, discord_config_path: str):
        """
        Initialize trading scheduler.

        Args:
            config_path: Path to assets.yaml
            discord_config_path: Path to discord.yaml
        """
        logger.info("Initializing TradingScheduler...")

        # Load configurations
        self.assets_config = self._load_yaml(config_path)
        self.discord_config = self._load_yaml(discord_config_path)

        # Initialize notifier
        webhook_url = self.discord_config.get("webhook_url", "")
        self.notifier = DiscordNotifier(webhook_url)

        # Initialize data fetcher with notifier for error alerts
        self.fetcher = BybitFetcher(notifier=self.notifier)

        # Setup CSV logging
        self.signals_csv_path = Path("logs/signals.csv")
        self._setup_signals_csv()

        # Strategy/Indicator factory mapping
        self.strategy_map = {"BBTrendlineStrategy": BBTrendlineStrategy, "SpikeDetectionStrategy": SpikeDetectionStrategy}

        self.indicator_map = {"BollingerBands": BollingerBands, "ZScoreIndicator": ZScoreIndicator}

        # Test components during initialization
        self.test_components()

        logger.info("TradingScheduler initialized successfully")

    def _load_yaml(self, path: str) -> Dict:
        """Load YAML configuration file."""
        try:
            with open(path, "r") as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded config from {path}")
            return config
        except FileNotFoundError:
            logger.error(f"Config file not found: {path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML file {path}: {e}")
            raise

    def _setup_signals_csv(self):
        """Create signals.csv with headers if it doesn't exist."""
        self.signals_csv_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.signals_csv_path.exists():
            headers = [
                "timestamp",
                "symbol",
                "signal",
                "price",
                "threshold",
                "bb_upper",
                "bb_lower",
                "bb_middle",
                "slope",
                "distance",
                "bb_width",
                # Spike-specific columns
                "price_zscore",
                "volume_zscore",
                "price_return_pct",
                "volume_ratio",
                "confirmation",
            ]

            with open(self.signals_csv_path, "w") as f:
                f.write(",".join(headers) + "\n")

            logger.info(f"Created signals CSV at {self.signals_csv_path}")

    def _log_signal_to_csv(self, symbol: str, signal_data: Dict[str, Any]):
        """
        Append signal to CSV file.
        Supports both BBTrendline and Spike signals.

        Args:
            symbol: Trading pair
            signal_data: Signal dict from strategy
        """
        try:
            metadata = signal_data.get("metadata", {})

            # Convert timestamp to local timezone (handle both open_timestamp and timestamp)
            timestamp_key = "open_timestamp" if "open_timestamp" in signal_data else "timestamp"
            local_timestamp = to_local_timezone(signal_data[timestamp_key])

            row = [
                local_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                signal_data["signal"],
                f"{signal_data['price']:.2f}",
                f"{signal_data.get('threshold', 0):.2f}",
                f"{signal_data.get('bb_upper', 0):.2f}",
                f"{signal_data.get('bb_lower', 0):.2f}",
                f"{signal_data.get('bb_middle', 0):.2f}",
                f"{metadata.get('slope', 0):.2f}",
                f"{metadata.get('distance_to_threshold', 0):.2f}",
                f"{metadata.get('bb_width', 0):.2f}",
                # Spike-specific fields
                f"{signal_data.get('price_zscore', 0):.2f}",
                f"{signal_data.get('volume_zscore', 0):.2f}",
                f"{signal_data.get('price_return_pct', 0):.2f}",
                f"{signal_data.get('volume_ratio', 0):.2f}",
                metadata.get("confirmation", ""),
            ]

            with open(self.signals_csv_path, "a") as f:
                f.write(",".join(row) + "\n")

            logger.info(f"Signal logged to CSV: {symbol} {signal_data['signal']}")

        except Exception as e:
            logger.error(f"Error logging signal to CSV: {e}")

    def run_strategy(self, asset_config: Dict[str, Any]):
        """
        Execute strategy for a single asset.

        Args:
            asset_config: Asset configuration dict from assets.yaml

        Process:
        1. Fetch OHLCV data from Bybit
        2. Calculate indicators
        3. Run strategy
        4. If signal: notify + log to CSV
        5. Handle errors gracefully
        """
        symbol = asset_config["symbol"]
        timeframe = asset_config["timeframe"]
        strategy_name = asset_config["strategy"]
        indicator_name = asset_config["indicator"]
        indicator_params = asset_config.get("indicator_params", {})
        strategy_params = asset_config.get("strategy_params", {})  # NEW: Support strategy params

        logger.info(f"Running {strategy_name} for {symbol} ({timeframe})...")

        try:
            # Step 1: Fetch data
            df = self.fetcher.get_ohlcv(symbol, timeframe, limit=200)

            if df is None or df.empty:
                logger.warning(f"No data fetched for {symbol}, skipping")
                return

            # Step 2: Initialize and calculate indicator
            indicator_class = self.indicator_map.get(indicator_name)
            if not indicator_class:
                logger.error(f"Unknown indicator: {indicator_name}")
                return

            indicator = indicator_class(**indicator_params)
            df = indicator.calculate(df)

            logger.info(f"Calculated {indicator_name} for {symbol}")

            # Step 3: Initialize and run strategy
            strategy_class = self.strategy_map.get(strategy_name)
            if not strategy_class:
                logger.error(f"Unknown strategy: {strategy_name}")
                return

            strategy = strategy_class(**strategy_params)  # UPDATED: Pass strategy params
            signal_data = strategy.generate_signal(df)

            # Step 4: Process signal if generated
            if not signal_data:
                logger.info(f"No signal for {symbol}")
                return

            logger.info(f"Signal generated for {symbol}: " f"{signal_data['signal']} at {signal_data['price']:.2f}")

            # Format message using strategy
            formatted_message = strategy.format_signal_message(symbol, signal_data)

            # Send Discord notification
            success = self.notifier.send(formatted_message)  # UPDATED: Use send() instead of send_signal()
            if success:
                logger.info(f"Discord notification sent for {symbol}")
            else:
                logger.warning(f"Failed to send Discord notification for {symbol}")

            # Log to CSV
            self._log_signal_to_csv(symbol, signal_data)

        except Exception as e:
            logger.error(f"Error running strategy for {symbol}: {e}", exc_info=True)
            error_msg = f"Error processing {symbol}: {str(e)}"
            self.notifier.send_error(error_msg)

    def run_assets_by_timeframe(self, timeframe: str):
        """
        Execute strategies for assets with specific timeframe.

        Args:
            timeframe: Timeframe to filter assets by (e.g., '1h', '5m')
        """
        logger.info(f"Running {timeframe} strategies at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        assets = self.assets_config.get("assets", [])

        # Filter assets by timeframe
        timeframe_assets = [a for a in assets if a.get("timeframe") == timeframe]

        if not timeframe_assets:
            logger.debug(f"No assets configured for {timeframe} timeframe")
            return

        for asset_config in timeframe_assets:
            self.run_strategy(asset_config)
            time.sleep(1)  # Small delay between assets to avoid rate limits

        logger.info(f"Completed {timeframe} strategy run ({len(timeframe_assets)} assets)")
        logger.info("=" * 60)

    def test_components(self) -> bool:
        """
        Test all components before starting scheduler.

        Tests:
        - Bybit connection
        - Discord webhook
        - Config loading

        Returns:
            True if all tests pass, False otherwise
        """
        logger.info("Testing components...")

        all_pass = True

        # Test Bybit connection
        logger.info("Testing Bybit connection...")
        if self.fetcher.test_connection():
            logger.info("✓ Bybit connection OK")
        else:
            logger.error("✗ Bybit connection FAILED")
            all_pass = False

        # Test Discord webhook
        logger.info("Testing Discord webhook...")
        if self.notifier.test():
            logger.info("✓ Discord webhook OK")
        else:
            logger.error("✗ Discord webhook FAILED")
            all_pass = False

        # Verify assets config
        assets = self.assets_config.get("assets", [])
        if assets:
            logger.info(f"✓ Found {len(assets)} asset(s) configured")
        else:
            logger.error("✗ No assets configured")
            all_pass = False

        return all_pass

    def _get_unique_timeframes(self) -> List[str]:
        """
        Get unique timeframes from configured assets.

        Returns:
            List of unique timeframe strings (e.g., ['1h', '5m'])
        """
        assets = self.assets_config.get("assets", [])
        timeframes = set()

        for asset in assets:
            tf = asset.get("timeframe")
            if tf:
                timeframes.add(tf)

        return sorted(list(timeframes))

    def start(self):
        """
        Start the scheduler with multi-timeframe support.
        Runs indefinitely until interrupted.

        Supports multiple timeframes by scheduling each independently:
        - 5m: Every 5 minutes at :00, :05, :10, etc.
        - 15m: Every 15 minutes at :00, :15, :30, :45
        - 1h: Every hour at :00
        - 4h: Every 4 hours at :00
        - 1d: Every day at midnight
        """
        logger.info("Starting TradingScheduler with multi-timeframe support...")

        # Get unique timeframes from config
        timeframes = self._get_unique_timeframes()

        if not timeframes:
            logger.error("No timeframes configured in assets.yaml")
            return

        logger.info(f"Detected timeframes: {', '.join(timeframes)}")

        # Schedule each timeframe independently
        for tf in timeframes:
            if tf == "5m":
                schedule.every(5).minutes.do(self.run_assets_by_timeframe, timeframe="5m")
                logger.info("Scheduled 5-minute strategy runs")
            elif tf == "15m":
                schedule.every(15).minutes.do(self.run_assets_by_timeframe, timeframe="15m")
                logger.info("Scheduled 15-minute strategy runs")
            elif tf == "1h":
                schedule.every().hour.at(":00").do(self.run_assets_by_timeframe, timeframe="1h")
                logger.info("Scheduled hourly strategy runs")
            elif tf == "4h":
                schedule.every(4).hours.do(self.run_assets_by_timeframe, timeframe="4h")
                logger.info("Scheduled 4-hour strategy runs")
            elif tf == "1d":
                schedule.every().day.at("00:00").do(self.run_assets_by_timeframe, timeframe="1d")
                logger.info("Scheduled daily strategy runs")
            else:
                logger.warning(f"Unsupported timeframe: {tf} - skipping")

        # Run immediately on start for all timeframes
        logger.info("Running initial strategy execution for all timeframes...")
        for tf in timeframes:
            self.run_assets_by_timeframe(tf)

        # Start scheduler loop
        logger.info(f"Scheduler started for timeframes: {', '.join(timeframes)}. Press Ctrl+C to stop.")

        try:
            while True:
                schedule.run_pending()
                time.sleep(30)  # Check every 30 seconds (for 5m precision)
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            self.notifier.send_error(f"Scheduler crashed: {str(e)}")
