"""
Discord webhook notification implementation.
Sends formatted trading signals to Discord channel.
"""

import requests
import logging
from typing import Dict, Any
from datetime import datetime
from .base import BaseNotifier

logger = logging.getLogger(__name__)


class DiscordNotifier(BaseNotifier):
    """
    Discord webhook notifier for trading signals.

    Features:
    - Rich formatted messages
    - Emoji indicators for signal type
    - Color-coded embeds (optional)
    - Error handling for webhook failures

    Setup:
    1. Create Discord webhook in channel settings
    2. Copy webhook URL
    3. Add to discord.yaml config
    """

    def __init__(self, webhook_url: str):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL from channel settings
        """
        if not webhook_url or webhook_url == "PLACEHOLDER_ADD_YOUR_WEBHOOK":
            logger.warning("⚠️Discord webhook not configured!")

        self.webhook_url = webhook_url
        self.timeout = 10  # seconds

    def send(self, message: str) -> bool:
        """
        Send message to Discord via webhook.

        Args:
            message: Plain text message to send

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            payload = {"content": message}

            response = requests.post(self.webhook_url, json=payload, timeout=self.timeout)

            if response.status_code == 204:
                logger.info("Discord notification sent successfully")
                return True
            else:
                logger.error(f"Discord webhook failed: {response.status_code} - {response.text}")
                return False

        except requests.Timeout:
            logger.error("Discord webhook timeout")
            return False

        except requests.RequestException as e:
            logger.error(f"Discord webhook error: {e}")
            return False

        except Exception as e:
            logger.error(f"Unexpected error sending Discord notification: {e}")
            return False

    def send_signal(self, symbol: str, signal_data: Dict[str, Any]) -> bool:
        """
        Send formatted trading signal to Discord.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            signal_data: Signal dict from strategy

        Returns:
            True if sent successfully, False otherwise
        """
        signal_type = signal_data["signal"]
        emoji = "🟢" if signal_type == "BUY" else "🔴"

        # Format message
        message = self._format_signal_message(symbol, signal_data, emoji)

        return self.send(message)

    def _format_signal_message(self, symbol: str, signal_data: Dict[str, Any], emoji: str) -> str:
        """
        Format trading signal into readable Discord message.

        Args:
            symbol: Trading pair
            signal_data: Signal dict
            emoji: Signal emoji indicator

        Returns:
            Formatted message string
        """
        # Clean symbol for display (remove :USDT suffix if present)
        display_symbol = symbol.replace(":USDT", "")

        # Extract data
        signal_type = signal_data["signal"]
        price = signal_data["price"]
        threshold = signal_data["threshold"]
        bb_upper = signal_data["bb_upper"]
        bb_lower = signal_data["bb_lower"]
        bb_middle = signal_data["bb_middle"]
        timestamp = signal_data["timestamp"]

        # Extract metadata
        metadata = signal_data.get("metadata", {})
        slope = metadata.get("slope", 0)
        distance = metadata.get("distance_to_threshold", 0)
        bb_width = metadata.get("bb_width", 0)

        # Build message
        message = f"""
{emoji} **{signal_type} SIGNAL** {emoji}

**Symbol:** {display_symbol}
**Price:** ${price:,.2f}
**Threshold:** ${threshold:,.2f}
**Distance:** ${distance:,.2f} ({abs(distance/price)*100:.2f}%)

**Bollinger Bands:**
• Upper: ${bb_upper:,.2f}
• Middle: ${bb_middle:,.2f}
• Lower: ${bb_lower:,.2f}
• Width: ${bb_width:,.2f}

**Trendline:**
• Slope: {slope:+.2f}

**Time:** {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""

        return message.strip()

    def send_error(self, error_message: str) -> bool:
        """
        Send error notification to Discord.

        Args:
            error_message: Error description

        Returns:
            True if sent successfully, False otherwise
        """
        formatted = f"⚠️ **ERROR** ⚠️\n\n{error_message}"
        return self.send(formatted)

    def test(self) -> bool:
        """
        Test Discord webhook by sending test message.

        Returns:
            True if test successful, False otherwise
        """
        test_message = "✅ Discord webhook test successful - Bot is online!"
        return self.send(test_message)

    def __repr__(self) -> str:
        return f"DiscordNotifier(webhook_configured={bool(self.webhook_url)})"
