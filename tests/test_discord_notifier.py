"""
Unit tests for DiscordNotifier.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from src.notifiers.discord_notifier import DiscordNotifier


def test_discord_notifier_init_with_url():
    """Test DiscordNotifier initialization with webhook_url parameter."""
    test_url = "https://discord.com/api/webhooks/test/test"

    notifier = DiscordNotifier(webhook_url=test_url)

    assert notifier.webhook_url == test_url
    assert notifier.timeout == 10


def test_discord_notifier_init_with_empty_url():
    """Test DiscordNotifier with empty webhook_url (should warn)."""
    notifier = DiscordNotifier(webhook_url="")

    assert notifier.webhook_url == ""
    assert notifier.timeout == 10


def test_discord_notifier_init_with_placeholder():
    """Test DiscordNotifier with placeholder URL (should warn)."""
    notifier = DiscordNotifier(webhook_url="PLACEHOLDER_ADD_YOUR_WEBHOOK")

    assert notifier.webhook_url == "PLACEHOLDER_ADD_YOUR_WEBHOOK"
    assert notifier.timeout == 10


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_success(mock_post):
    """Test successful message send."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_response.text = ""
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    result = notifier.send("Test message")

    assert result is True
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert call_args[0][0] == "https://discord.com/api/webhooks/test/test"
    assert call_args[1]["json"]["content"] == "Test message"
    assert call_args[1]["timeout"] == 10


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_failure_status_code(mock_post):
    """Test send failure with non-204 status code."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.text = "Webhook not found"
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    result = notifier.send("Test message")

    assert result is False


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_timeout(mock_post):
    """Test send timeout handling."""
    from requests import Timeout

    mock_post.side_effect = Timeout("Request timed out")

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    result = notifier.send("Test message")

    assert result is False


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_request_exception(mock_post):
    """Test send with RequestException."""
    from requests import RequestException

    mock_post.side_effect = RequestException("Connection error")

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    result = notifier.send("Test message")

    assert result is False


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_unexpected_exception(mock_post):
    """Test send with unexpected exception."""
    mock_post.side_effect = ValueError("Unexpected error")

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    result = notifier.send("Test message")

    assert result is False


@patch("src.notifiers.discord_notifier.requests.post")
def test_format_signal_message(mock_post):
    """Test that notifier can send pre-formatted signal messages."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    # Pre-formatted message from strategy
    formatted_message = """🟢 **BUY SIGNAL** 🟢

**Symbol:** BTCUSDT = $45,123.50
**Threshold:** $45,200.00

**Bollinger Bands:** $46,000.00 / $44,500.00 / $45,250.00"""

    result = notifier.send_signal(formatted_message)

    assert result is True
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "BUY SIGNAL" in message_content
    assert "BTCUSDT" in message_content
    assert "$45,123.50" in message_content


@patch("src.notifiers.discord_notifier.requests.post")
def test_format_signal_message_sell(mock_post):
    """Test that notifier can send pre-formatted SELL signal messages."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    # Pre-formatted message from strategy
    formatted_message = """🔴 **SELL SIGNAL** 🔴

**Symbol:** ETHUSDT = $44,800.00
**Threshold:** $44,700.00

**Bollinger Bands:** $46,000.00 / $44,000.00 / $45,000.00"""

    result = notifier.send_signal(formatted_message)

    assert result is True
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "SELL SIGNAL" in message_content
    assert "ETHUSDT" in message_content
    assert "$44,800.00" in message_content


@patch("src.notifiers.discord_notifier.requests.post")
def test_format_signal_message_cleans_symbol(mock_post):
    """Test that notifier sends messages with cleaned symbols."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    # Pre-formatted message with cleaned symbol (strategy handles cleaning)
    formatted_message = """🟢 **BUY SIGNAL** 🟢

**Symbol:** BTCUSDT = $45,000.00"""

    result = notifier.send_signal(formatted_message)

    # Should send BTCUSDT, not BTCUSDT:USDT (strategy cleans the symbol)
    assert result is True
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "BTCUSDT" in message_content


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_signal(mock_post):
    """Test send_signal method with pre-formatted message."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    # Pre-formatted message from strategy
    formatted_message = """🟢 **BUY SIGNAL** 🟢

**Symbol:** BTCUSDT = $45,000.00
**Threshold:** $45,100.00

**Bollinger Bands:** $46,000.00 / $44,000.00 / $45,000.00"""

    result = notifier.send_signal(formatted_message)

    assert result is True
    mock_post.assert_called_once()
    # Verify message contains signal info
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "BUY SIGNAL" in message_content
    assert "BTCUSDT" in message_content


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_signal_sell(mock_post):
    """Test send_signal with SELL signal."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    # Pre-formatted message from strategy
    formatted_message = """🔴 **SELL SIGNAL** 🔴

**Symbol:** ETHUSDT = $44,800.00
**Threshold:** $44,700.00

**Bollinger Bands:** $46,000.00 / $44,000.00 / $45,000.00"""

    result = notifier.send_signal(formatted_message)

    assert result is True
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "SELL SIGNAL" in message_content
    assert "🔴" in message_content  # Red emoji for SELL


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_error(mock_post):
    """Test send_error method."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    result = notifier.send_error("Test error message")

    assert result is True
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "ERROR" in message_content
    assert "Test error message" in message_content


@patch("src.notifiers.discord_notifier.requests.post")
def test_test_method(mock_post):
    """Test test() method."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    result = notifier.test()

    assert result is True
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "Bot is online" in message_content


def test_repr():
    """Test __repr__ method."""
    notifier1 = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    assert "webhook_configured=True" in repr(notifier1)

    notifier2 = DiscordNotifier(webhook_url="")
    assert "webhook_configured=False" in repr(notifier2)


@patch("src.notifiers.discord_notifier.requests.post")
def test_format_signal_message_missing_metadata(mock_post):
    """Test sending messages works regardless of metadata."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    # Pre-formatted message (strategy handles missing metadata gracefully)
    formatted_message = """🟢 **BUY SIGNAL** 🟢

**Symbol:** BTCUSDT = $45,000.00"""

    result = notifier.send_signal(formatted_message)

    # Should still work with minimal message
    assert result is True
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "BUY SIGNAL" in message_content
    assert "BTCUSDT" in message_content


@patch("src.notifiers.discord_notifier.requests.post")
def test_format_signal_message_partial_metadata(mock_post):
    """Test sending messages works with partial information."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    # Pre-formatted message with some metadata (strategy handles partial metadata)
    formatted_message = """🟢 **BUY SIGNAL** 🟢

**Symbol:** BTCUSDT = $45,000.00
**Threshold:** $45,100.00
**Slope:** +100.00"""

    result = notifier.send_signal(formatted_message)

    # Should work with partial information
    assert result is True
    call_args = mock_post.call_args
    message_content = call_args[1]["json"]["content"]
    assert "BUY SIGNAL" in message_content
    assert "+100.00" in message_content  # slope should be present
