"""
Discord webhook notification implementation.
Sends formatted trading signals to Discord channel.
"""

import requests
import logging
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

    def send_signal(self, message: str) -> bool:
        """
        Send message to Discord.

        Args:
            message: Pre-formatted message string from strategy

        Returns:
            True if sent successfully, False otherwise
        """
        return self.send(message)

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
        test_message = "✅ Bot is online!"
        return self.send(test_message)

    def __repr__(self) -> str:
        return f"DiscordNotifier(webhook_configured={bool(self.webhook_url)})"
