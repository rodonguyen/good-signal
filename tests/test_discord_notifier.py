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


def test_format_signal_message():
    """Test signal message formatting."""
    notifier = DiscordNotifier(webhook_url="test")

    signal_data = {
        "signal": "BUY",
        "price": 45123.50,
        "threshold": 45200.00,
        "bb_upper": 46000.00,
        "bb_lower": 44500.00,
        "bb_middle": 45250.00,
        "timestamp": datetime(2024, 12, 2, 14, 0, 0),
        "metadata": {
            "slope": 100.0,
            "distance_to_threshold": 76.50,
            "bb_width": 1500.00,
        },
    }

    message = notifier._format_signal_message("BTCUSDT", signal_data, "🟢")

    assert "BUY SIGNAL" in message
    assert "BTCUSDT" in message
    assert "$45,123.50" in message
    assert "$45,200.00" in message
    assert "$46,000.00" in message
    assert "$44,500.00" in message
    assert "$45,250.00" in message
    assert "$1,500.00" in message
    assert "+100.00" in message
    assert "2024-12-02 14:00:00 UTC" in message


def test_format_signal_message_sell():
    """Test signal message formatting for SELL signal."""
    notifier = DiscordNotifier(webhook_url="test")

    signal_data = {
        "signal": "SELL",
        "price": 44800.00,
        "threshold": 44700.00,
        "bb_upper": 46000.00,
        "bb_lower": 44000.00,
        "bb_middle": 45000.00,
        "timestamp": datetime(2024, 12, 2, 15, 30, 0),
        "metadata": {
            "slope": -50.0,
            "distance_to_threshold": 100.00,
            "bb_width": 2000.00,
        },
    }

    message = notifier._format_signal_message("ETHUSDT", signal_data, "🔴")

    assert "SELL SIGNAL" in message
    assert "ETHUSDT" in message
    assert "$44,800.00" in message
    assert "-50.00" in message


def test_format_signal_message_cleans_symbol():
    """Test that symbol cleaning removes :USDT suffix."""
    notifier = DiscordNotifier(webhook_url="test")

    signal_data = {
        "signal": "BUY",
        "price": 45000.00,
        "threshold": 45100.00,
        "bb_upper": 46000.00,
        "bb_lower": 44000.00,
        "bb_middle": 45000.00,
        "timestamp": datetime.now(),
        "metadata": {},
    }

    message = notifier._format_signal_message("BTCUSDT:USDT", signal_data, "🟢")

    # Should show BTCUSDT, not BTCUSDT:USDT
    assert "BTCUSDT" in message
    assert "BTCUSDT:USDT" not in message


@patch("src.notifiers.discord_notifier.requests.post")
def test_send_signal(mock_post):
    """Test send_signal method."""
    mock_response = Mock()
    mock_response.status_code = 204
    mock_post.return_value = mock_response

    notifier = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")

    signal_data = {
        "signal": "BUY",
        "price": 45000.00,
        "threshold": 45100.00,
        "bb_upper": 46000.00,
        "bb_lower": 44000.00,
        "bb_middle": 45000.00,
        "timestamp": datetime.now(),
        "metadata": {
            "slope": 100.0,
            "distance_to_threshold": 100.00,
            "bb_width": 2000.00,
        },
    }

    result = notifier.send_signal("BTCUSDT", signal_data)

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

    signal_data = {
        "signal": "SELL",
        "price": 44800.00,
        "threshold": 44700.00,
        "bb_upper": 46000.00,
        "bb_lower": 44000.00,
        "bb_middle": 45000.00,
        "timestamp": datetime.now(),
        "metadata": {},
    }

    result = notifier.send_signal("ETHUSDT", signal_data)

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
    assert "Discord webhook test successful" in message_content


def test_repr():
    """Test __repr__ method."""
    notifier1 = DiscordNotifier(webhook_url="https://discord.com/api/webhooks/test/test")
    assert "webhook_configured=True" in repr(notifier1)

    notifier2 = DiscordNotifier(webhook_url="")
    assert "webhook_configured=False" in repr(notifier2)


def test_format_signal_message_missing_metadata():
    """Test formatting with missing metadata fields."""
    notifier = DiscordNotifier(webhook_url="test")

    signal_data = {
        "signal": "BUY",
        "price": 45000.00,
        "threshold": 45100.00,
        "bb_upper": 46000.00,
        "bb_lower": 44000.00,
        "bb_middle": 45000.00,
        "timestamp": datetime.now(),
        # Missing metadata
    }

    message = notifier._format_signal_message("BTCUSDT", signal_data, "🟢")

    # Should still work with default values
    assert "BUY SIGNAL" in message
    assert "BTCUSDT" in message


def test_format_signal_message_partial_metadata():
    """Test formatting with partial metadata."""
    notifier = DiscordNotifier(webhook_url="test")

    signal_data = {
        "signal": "BUY",
        "price": 45000.00,
        "threshold": 45100.00,
        "bb_upper": 46000.00,
        "bb_lower": 44000.00,
        "bb_middle": 45000.00,
        "timestamp": datetime.now(),
        "metadata": {
            "slope": 100.0,
            # Missing distance_to_threshold and bb_width
        },
    }

    message = notifier._format_signal_message("BTCUSDT", signal_data, "🟢")

    # Should use default values for missing metadata
    assert "BUY SIGNAL" in message
    assert "+100.00" in message  # slope should be present
