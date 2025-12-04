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
from src.strategies.bb_trendline import BBTrendlineStrategy
from src.notifiers.discord_notifier import DiscordNotifier

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
        self.strategy_map = {"BBTrendlineStrategy": BBTrendlineStrategy}

        self.indicator_map = {"BollingerBands": BollingerBands}

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
            ]

            with open(self.signals_csv_path, "w") as f:
                f.write(",".join(headers) + "\n")

            logger.info(f"Created signals CSV at {self.signals_csv_path}")

    def _log_signal_to_csv(self, symbol: str, signal_data: Dict[str, Any]):
        """
        Append signal to CSV file.

        Args:
            symbol: Trading pair
            signal_data: Signal dict from strategy
        """
        try:
            metadata = signal_data.get("metadata", {})

            row = [
                signal_data["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                symbol,
                signal_data["signal"],
                f"{signal_data['price']:.2f}",
                f"{signal_data['threshold']:.2f}",
                f"{signal_data['bb_upper']:.2f}",
                f"{signal_data['bb_lower']:.2f}",
                f"{signal_data['bb_middle']:.2f}",
                f"{metadata.get('slope', 0):.2f}",
                f"{metadata.get('distance_to_threshold', 0):.2f}",
                f"{metadata.get('bb_width', 0):.2f}",
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
        2. Calculate indicators (Bollinger Bands)
        3. Run strategy (BBTrendlineStrategy)
        4. If signal: notify + log to CSV
        5. Handle errors gracefully
        """
        symbol = asset_config["symbol"]
        timeframe = asset_config["timeframe"]
        strategy_name = asset_config["strategy"]
        indicator_name = asset_config["indicator"]
        indicator_params = asset_config.get("indicator_params", {})

        logger.info(f"Running strategy for {symbol}...")

        try:
            # Step 1: Fetch data
            df = self.fetcher.get_ohlcv(symbol, timeframe, limit=100)

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

            strategy = strategy_class()
            signal_data = strategy.generate_signal(df)

            # Step 4: Process signal if generated
            if signal_data:
                logger.info(f"Signal generated for {symbol}: " f"{signal_data['signal']} at {signal_data['price']:.2f}")

                # Send Discord notification
                success = self.notifier.send_signal(symbol, signal_data)
                if success:
                    logger.info(f"Discord notification sent for {symbol}")
                else:
                    logger.warning(f"Failed to send Discord notification for {symbol}")

                # Log to CSV
                self._log_signal_to_csv(symbol, signal_data)

            else:
                logger.info(f"No signal for {symbol}")

                # Send status update notification when no signal
                current_price = float(df.iloc[-1]["close"])
                bb_upper = float(df.iloc[-1]["bb_upper"])
                bb_lower = float(df.iloc[-1]["bb_lower"])
                timestamp = df.iloc[-1]["timestamp"]

                status_message = (
                    f"💤Update: {symbol} | ${current_price:,.2f} "
                    f"(BB Upper: ${bb_upper:,.2f} | Lower: ${bb_lower:,.2f})\n"
                    f"No breakout detected  |  {timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                self.notifier.send(status_message)

        except Exception as e:
            logger.error(f"Error running strategy for {symbol}: {e}", exc_info=True)
            error_msg = f"Error processing {symbol}: {str(e)}"
            self.notifier.send_error(error_msg)

    def run_all_assets(self):
        """
        Execute strategies for all configured assets.
        Called by scheduler every hour.
        """
        logger.info(f"Running strategies at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        assets = self.assets_config.get("assets", [])

        if not assets:
            logger.warning("⚠️No assets configured in assets.yaml")
            return

        for asset_config in assets:
            self.run_strategy(asset_config)
            time.sleep(1)  # Small delay between assets to avoid rate limits

        logger.info("Completed strategy run for all assets")
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

    def start(self):
        """
        Start the scheduler with 1h interval.
        Runs indefinitely until interrupted.
        """
        logger.info("Starting TradingScheduler...")

        # Schedule runs at sharp hours (1:00, 2:00, etc.)
        schedule.every().hour.at(":00").do(self.run_all_assets)

        # Run immediately on start
        logger.info("Running initial strategy execution...")
        self.run_all_assets()

        # Start scheduler loop
        logger.info("Scheduler started. Running every 1 hour. Press Ctrl+C to stop.")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            self.notifier.send_error(f"Scheduler crashed: {str(e)}")
