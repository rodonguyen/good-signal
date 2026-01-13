"""
Trading Signal Bot - Main Entry Point

Description:
    Monitors Bitcoin (and other assets) using Bollinger Band trendline strategy.
    Sends signals via Discord webhook when breakouts occur.

Usage:
    python main.py

Requirements:
    - Python 3.9+
    - Dependencies in requirements.txt
    - Discord webhook configured in config/discord.yaml
    - Assets configured in config/assets.yaml
"""

import logging
import sys
from pathlib import Path

from src.scheduler import TradingScheduler


def setup_logging():
    """
    Configure logging for the application.

    Logging Strategy:
    - Console: INFO level (general operations)
    - File (future): DEBUG level (detailed debugging)
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Reduce noise from external libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("ccxt").setLevel(logging.WARNING)


def validate_config_files():
    """
    Check if required configuration files exist.

    Raises:
        FileNotFoundError: If required config files are missing
    """
    required_files = ["config/assets.yaml", "config/discord.yaml"]

    for file_path in required_files:
        if not Path(file_path).exists():
            raise FileNotFoundError(f"Required config file not found: {file_path}\n" f"Please create it before running the bot.")


def main():
    """Main entry point for trading signal bot."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("=" * 70)
    logger.info("TRADING SIGNAL BOT - Starting Up")
    logger.info("=" * 70)

    try:
        # Validate config files exist
        validate_config_files()

        # Initialize scheduler
        scheduler = TradingScheduler(config_path="config/assets.yaml", discord_config_path="config/discord.yaml")

        # Start scheduler (runs forever)
        scheduler.start()

    except FileNotFoundError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        logger.info("=" * 70)
        logger.info("Shutdown requested by user")
        logger.info("TRADING SIGNAL BOT - Shut Down")
        logger.info("=" * 70)
        sys.exit(0)

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
