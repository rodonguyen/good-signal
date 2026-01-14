"""
Notification service for live trading events.

Provides async Discord notifications for trade entry/exit,
risk alerts, and system events.
"""

import asyncio
from typing import Optional
from datetime import datetime

import httpx

from backend.core.logging import get_logger
from backend.config import get_settings

logger = get_logger(__name__)


def _utc_now() -> str:
    """Generate UTC timestamp in ISO format with Z suffix."""
    return datetime.utcnow().isoformat() + "Z"


class NotificationService:
    """
    Async notification service for trading events.

    Sends formatted messages to Discord via webhooks.
    Handles trade entries, exits, risk alerts, and system events.

    Example:
        >>> service = NotificationService()
        >>> await service.notify_trade_entry(
        ...     symbol="BTCUSDT",
        ...     direction="long",
        ...     entry_price=42000.0,
        ...     quantity=0.1,
        ...     stop_loss=41000.0,
        ...     take_profit=44000.0,
        ... )
    """

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        """
        Initialize notification service.

        Args:
            webhook_url: Discord webhook URL. If None, uses settings.
            timeout: HTTP request timeout in seconds.
        """
        settings = get_settings()
        self._webhook_url = webhook_url or getattr(settings, "DISCORD_WEBHOOK_URL", None)
        self._timeout = timeout
        self._enabled = bool(self._webhook_url)

        if not self._enabled:
            logger.warning(
                "Discord notifications disabled - no webhook URL configured"
            )

    async def _send_message(self, content: str) -> bool:
        """
        Send message to Discord webhook.

        Args:
            content: Message content

        Returns:
            True if sent successfully
        """
        if not self._enabled:
            logger.debug("Notification skipped - Discord not configured")
            return False

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._webhook_url,
                    json={"content": content},
                )

                if response.status_code == 204:
                    logger.debug("Discord notification sent successfully")
                    return True
                else:
                    logger.error(
                        "Discord webhook failed",
                        status_code=response.status_code,
                        response=response.text,
                    )
                    return False

        except httpx.TimeoutException:
            logger.error("Discord webhook timeout")
            return False

        except httpx.HTTPError as e:
            logger.error("Discord webhook HTTP error", error=str(e))
            return False

        except Exception as e:
            logger.error("Unexpected notification error", error=str(e))
            return False

    async def _send_embed(
        self,
        title: str,
        description: str,
        color: int,
        fields: Optional[list[dict]] = None,
        footer: Optional[str] = None,
    ) -> bool:
        """
        Send rich embed to Discord.

        Args:
            title: Embed title
            description: Embed description
            color: Embed color (decimal)
            fields: Optional list of field dicts with name/value
            footer: Optional footer text

        Returns:
            True if sent successfully
        """
        if not self._enabled:
            return False

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": _utc_now(),
        }

        if fields:
            embed["fields"] = [
                {"name": f["name"], "value": str(f["value"]), "inline": f.get("inline", True)}
                for f in fields
            ]

        if footer:
            embed["footer"] = {"text": footer}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._webhook_url,
                    json={"embeds": [embed]},
                )

                if response.status_code == 204:
                    return True
                else:
                    logger.error(
                        "Discord embed failed",
                        status_code=response.status_code,
                    )
                    return False

        except Exception as e:
            logger.error("Embed notification error", error=str(e))
            return False

    async def notify_trade_entry(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        quantity: float,
        strategy_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        position_id: Optional[str] = None,
    ) -> bool:
        """
        Send trade entry notification.

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            direction: Trade direction (long/short)
            entry_price: Entry price
            quantity: Position size
            strategy_id: Strategy identifier
            stop_loss: Stop loss level
            take_profit: Take profit level
            position_id: Position identifier

        Returns:
            True if notification sent
        """
        # Color: green for long, red for short
        color = 0x00FF00 if direction == "long" else 0xFF0000
        emoji = "📈" if direction == "long" else "📉"

        fields = [
            {"name": "Symbol", "value": symbol},
            {"name": "Direction", "value": direction.upper()},
            {"name": "Entry Price", "value": f"${entry_price:,.2f}"},
            {"name": "Quantity", "value": f"{quantity:.6f}"},
            {"name": "Strategy", "value": strategy_id},
        ]

        if stop_loss:
            fields.append({"name": "Stop Loss", "value": f"${stop_loss:,.2f}"})
        if take_profit:
            fields.append({"name": "Take Profit", "value": f"${take_profit:,.2f}"})

        notional = entry_price * quantity
        fields.append({"name": "Notional Value", "value": f"${notional:,.2f}"})

        logger.info(
            "Sending trade entry notification",
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
        )

        return await self._send_embed(
            title=f"{emoji} TRADE ENTRY",
            description=f"New {direction} position opened",
            color=color,
            fields=fields,
            footer=f"Position ID: {position_id}" if position_id else None,
        )

    async def notify_trade_exit(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        realized_pnl: float,
        exit_reason: str,
        position_id: Optional[str] = None,
    ) -> bool:
        """
        Send trade exit notification.

        Args:
            symbol: Trading pair
            direction: Trade direction
            entry_price: Entry price
            exit_price: Exit price
            quantity: Position size
            realized_pnl: Realized profit/loss
            exit_reason: Reason for exit
            position_id: Position identifier

        Returns:
            True if notification sent
        """
        # Color based on P&L
        color = 0x00FF00 if realized_pnl >= 0 else 0xFF0000
        emoji = "✅" if realized_pnl >= 0 else "❌"
        pnl_sign = "+" if realized_pnl >= 0 else ""

        # Calculate percentage
        entry_value = entry_price * quantity
        pnl_pct = (realized_pnl / entry_value * 100) if entry_value > 0 else 0

        fields = [
            {"name": "Symbol", "value": symbol},
            {"name": "Direction", "value": direction.upper()},
            {"name": "Entry Price", "value": f"${entry_price:,.2f}"},
            {"name": "Exit Price", "value": f"${exit_price:,.2f}"},
            {"name": "Quantity", "value": f"{quantity:.6f}"},
            {"name": "Exit Reason", "value": exit_reason},
            {"name": "Realized P&L", "value": f"{pnl_sign}${realized_pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)"},
        ]

        logger.info(
            "Sending trade exit notification",
            symbol=symbol,
            realized_pnl=realized_pnl,
            exit_reason=exit_reason,
        )

        return await self._send_embed(
            title=f"{emoji} TRADE EXIT",
            description=f"Position closed - {exit_reason}",
            color=color,
            fields=fields,
            footer=f"Position ID: {position_id}" if position_id else None,
        )

    async def notify_risk_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "warning",
        action_taken: Optional[str] = None,
    ) -> bool:
        """
        Send risk alert notification.

        Args:
            alert_type: Type of alert (e.g., "daily_loss_limit", "kill_switch")
            message: Alert message
            severity: Alert severity (info, warning, critical)
            action_taken: Optional action description

        Returns:
            True if notification sent
        """
        # Color by severity
        colors = {
            "info": 0x0099FF,
            "warning": 0xFFCC00,
            "critical": 0xFF0000,
        }
        emojis = {
            "info": "ℹ️",
            "warning": "⚠️",
            "critical": "🚨",
        }

        color = colors.get(severity, 0xFFCC00)
        emoji = emojis.get(severity, "⚠️")

        fields = [
            {"name": "Alert Type", "value": alert_type, "inline": True},
            {"name": "Severity", "value": severity.upper(), "inline": True},
        ]

        if action_taken:
            fields.append({"name": "Action Taken", "value": action_taken, "inline": False})

        logger.warning(
            "Sending risk alert notification",
            alert_type=alert_type,
            severity=severity,
        )

        return await self._send_embed(
            title=f"{emoji} RISK ALERT",
            description=message,
            color=color,
            fields=fields,
        )

    async def notify_kill_switch(
        self,
        activated: bool,
        reason: Optional[str] = None,
    ) -> bool:
        """
        Send kill switch notification.

        Args:
            activated: True if activated, False if deactivated
            reason: Reason for activation

        Returns:
            True if notification sent
        """
        if activated:
            return await self._send_embed(
                title="🛑 KILL SWITCH ACTIVATED",
                description="All trading has been halted",
                color=0xFF0000,
                fields=[
                    {"name": "Reason", "value": reason or "Manual activation", "inline": False},
                    {"name": "Action", "value": "All new trades blocked. Existing positions may be closed.", "inline": False},
                ],
            )
        else:
            return await self._send_embed(
                title="✅ KILL SWITCH DEACTIVATED",
                description="Trading has been resumed",
                color=0x00FF00,
                fields=[
                    {"name": "Status", "value": "System is now accepting new trades", "inline": False},
                ],
            )

    async def notify_system_event(
        self,
        event_type: str,
        message: str,
    ) -> bool:
        """
        Send system event notification.

        Args:
            event_type: Type of event (startup, shutdown, error)
            message: Event message

        Returns:
            True if notification sent
        """
        colors = {
            "startup": 0x00FF00,
            "shutdown": 0xFFCC00,
            "error": 0xFF0000,
        }
        emojis = {
            "startup": "🟢",
            "shutdown": "🟡",
            "error": "🔴",
        }

        color = colors.get(event_type, 0x0099FF)
        emoji = emojis.get(event_type, "ℹ️")

        return await self._send_embed(
            title=f"{emoji} SYSTEM: {event_type.upper()}",
            description=message,
            color=color,
        )

    async def send_daily_summary(
        self,
        date: str,
        total_trades: int,
        winning_trades: int,
        total_pnl: float,
        open_positions: int,
    ) -> bool:
        """
        Send daily trading summary.

        Args:
            date: Summary date
            total_trades: Total trades executed
            winning_trades: Number of winning trades
            total_pnl: Total realized P&L
            open_positions: Number of open positions

        Returns:
            True if notification sent
        """
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        color = 0x00FF00 if total_pnl >= 0 else 0xFF0000
        pnl_sign = "+" if total_pnl >= 0 else ""

        fields = [
            {"name": "Date", "value": date, "inline": True},
            {"name": "Total Trades", "value": str(total_trades), "inline": True},
            {"name": "Win Rate", "value": f"{win_rate:.1f}%", "inline": True},
            {"name": "Daily P&L", "value": f"{pnl_sign}${total_pnl:,.2f}", "inline": True},
            {"name": "Open Positions", "value": str(open_positions), "inline": True},
        ]

        return await self._send_embed(
            title="📊 DAILY SUMMARY",
            description=f"Trading summary for {date}",
            color=color,
            fields=fields,
        )

    def is_enabled(self) -> bool:
        """Check if notifications are enabled."""
        return self._enabled
