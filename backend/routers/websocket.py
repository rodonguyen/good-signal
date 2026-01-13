"""
WebSocket handler for real-time updates.

Provides WebSocket connections for broadcasting backtest progress,
live trading updates, and other real-time notifications.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from backend.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class ConnectionManager:
    """
    Manages WebSocket connections and channel subscriptions.

    Provides thread-safe operations for connection lifecycle management,
    channel-based pub/sub, and message broadcasting.

    Attributes:
        active_connections: Map of client_id to WebSocket connection.
        subscriptions: Map of channel name to set of subscribed client_ids.

    Example:
        >>> manager = ConnectionManager()
        >>> await manager.connect(websocket, "client-123")
        >>> manager.subscribe("client-123", ["backtest", "trades"])
        >>> await manager.broadcast_to_channel("backtest", {"type": "progress", "value": 0.5})
    """

    def __init__(self) -> None:
        """Initialize the ConnectionManager."""
        self._active_connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, set[str]] = {}
        self._client_channels: dict[str, set[str]] = {}  # Track channels per client
        self._lock = asyncio.Lock()

    @property
    def active_connections(self) -> dict[str, WebSocket]:
        """Get the active connections dictionary."""
        return self._active_connections

    @property
    def subscriptions(self) -> dict[str, set[str]]:
        """Get the channel subscriptions dictionary."""
        return self._subscriptions

    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """
        Accept and register a WebSocket connection.

        Args:
            websocket: WebSocket connection to accept.
            client_id: Unique identifier for the client.
        """
        await websocket.accept()

        async with self._lock:
            self._active_connections[client_id] = websocket
            self._client_channels[client_id] = set()

        logger.info("WebSocket connected", client_id=client_id)

    def disconnect(self, client_id: str) -> None:
        """
        Disconnect and cleanup a WebSocket connection.

        Removes the connection and all channel subscriptions.

        Args:
            client_id: Unique identifier for the client.
        """
        if client_id in self._active_connections:
            del self._active_connections[client_id]

        # Remove from all channel subscriptions
        if client_id in self._client_channels:
            for channel in self._client_channels[client_id]:
                if channel in self._subscriptions:
                    self._subscriptions[channel].discard(client_id)
            del self._client_channels[client_id]

        logger.info("WebSocket disconnected", client_id=client_id)

    def subscribe(self, client_id: str, channels: list[str]) -> None:
        """
        Subscribe a client to one or more channels.

        Args:
            client_id: Unique identifier for the client.
            channels: List of channel names to subscribe to.
        """
        if client_id not in self._active_connections:
            logger.warning("Cannot subscribe disconnected client", client_id=client_id)
            return

        for channel in channels:
            if channel not in self._subscriptions:
                self._subscriptions[channel] = set()
            self._subscriptions[channel].add(client_id)

            if client_id in self._client_channels:
                self._client_channels[client_id].add(channel)

        logger.debug(
            "Client subscribed to channels",
            client_id=client_id,
            channels=channels,
        )

    def unsubscribe(self, client_id: str, channels: list[str]) -> None:
        """
        Unsubscribe a client from one or more channels.

        Args:
            client_id: Unique identifier for the client.
            channels: List of channel names to unsubscribe from.
        """
        for channel in channels:
            if channel in self._subscriptions:
                self._subscriptions[channel].discard(client_id)

            if client_id in self._client_channels:
                self._client_channels[client_id].discard(channel)

        logger.debug(
            "Client unsubscribed from channels",
            client_id=client_id,
            channels=channels,
        )

    def get_subscribed_channels(self, client_id: str) -> list[str]:
        """
        Get channels a client is subscribed to.

        Args:
            client_id: Unique identifier for the client.

        Returns:
            list[str]: List of subscribed channel names.
        """
        return list(self._client_channels.get(client_id, set()))

    async def send_personal_message(
        self,
        client_id: str,
        message: dict[str, Any],
    ) -> bool:
        """
        Send a message to a specific client.

        Args:
            client_id: Unique identifier for the client.
            message: Message dictionary to send.

        Returns:
            bool: True if message was sent, False if client not connected.
        """
        if client_id not in self._active_connections:
            return False

        try:
            await self._active_connections[client_id].send_json(message)
            return True
        except Exception as e:
            logger.warning(
                "Failed to send message to client",
                client_id=client_id,
                error=str(e),
            )
            self.disconnect(client_id)
            return False

    async def broadcast_to_channel(
        self,
        channel: str,
        message: dict[str, Any],
    ) -> int:
        """
        Broadcast a message to all clients subscribed to a channel.

        Args:
            channel: Channel name to broadcast to.
            message: Message dictionary to broadcast.

        Returns:
            int: Number of clients the message was sent to.
        """
        if channel not in self._subscriptions:
            return 0

        sent_count = 0
        failed_clients: list[str] = []

        # Create a copy of the set to avoid modification during iteration
        client_ids = list(self._subscriptions[channel])

        for client_id in client_ids:
            if client_id in self._active_connections:
                try:
                    await self._active_connections[client_id].send_json(message)
                    sent_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to broadcast to client",
                        client_id=client_id,
                        channel=channel,
                        error=str(e),
                    )
                    failed_clients.append(client_id)

        # Clean up failed connections
        for client_id in failed_clients:
            self.disconnect(client_id)

        return sent_count

    async def broadcast_to_all(self, message: dict[str, Any]) -> int:
        """
        Broadcast a message to all connected clients.

        Args:
            message: Message dictionary to broadcast.

        Returns:
            int: Number of clients the message was sent to.
        """
        sent_count = 0
        failed_clients: list[str] = []

        for client_id, websocket in list(self._active_connections.items()):
            try:
                await websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "Failed to broadcast to client",
                    client_id=client_id,
                    error=str(e),
                )
                failed_clients.append(client_id)

        # Clean up failed connections
        for client_id in failed_clients:
            self.disconnect(client_id)

        return sent_count

    async def close_all(self, code: int = status.WS_1000_NORMAL_CLOSURE) -> None:
        """
        Close all active connections.

        Args:
            code: WebSocket close code.
        """
        for client_id, websocket in list(self._active_connections.items()):
            try:
                await websocket.close(code=code)
            except Exception as e:
                logger.warning(
                    "Error closing connection",
                    client_id=client_id,
                    error=str(e),
                )

        self._active_connections.clear()
        self._subscriptions.clear()
        self._client_channels.clear()

        logger.info("All WebSocket connections closed")


# Global connection manager instance
manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return manager


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    WebSocket endpoint for real-time updates.

    Accepts connections, handles subscription messages, and maintains
    the connection until the client disconnects.

    Message Protocol:
        Subscribe: {"type": "subscribe", "channels": ["backtest", "trades"]}
        Unsubscribe: {"type": "unsubscribe", "channels": ["backtest"]}
        Ping: {"type": "ping"}
        Pong response: {"type": "pong", "timestamp": "..."}

    Broadcast Message Format:
        {
            "type": "{channel}:{event}",
            "payload": {...}
        }
    """
    client_id = str(uuid.uuid4())

    await manager.connect(websocket, client_id)

    # Send connection confirmation
    await websocket.send_json({
        "type": "connected",
        "payload": {
            "client_id": client_id,
            "message": "WebSocket connection established",
        },
    })

    try:
        while True:
            # Receive and parse message
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "payload": {
                        "message": "Invalid JSON message",
                    },
                })
                continue

            message_type = data.get("type")

            if message_type == "subscribe":
                channels = data.get("channels", [])
                if isinstance(channels, list):
                    manager.subscribe(client_id, channels)
                    await websocket.send_json({
                        "type": "subscribed",
                        "payload": {
                            "channels": channels,
                        },
                    })

            elif message_type == "unsubscribe":
                channels = data.get("channels", [])
                if isinstance(channels, list):
                    manager.unsubscribe(client_id, channels)
                    await websocket.send_json({
                        "type": "unsubscribed",
                        "payload": {
                            "channels": channels,
                        },
                    })

            elif message_type == "ping":
                from datetime import datetime
                await websocket.send_json({
                    "type": "pong",
                    "payload": {
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                })

            elif message_type == "get_subscriptions":
                subscribed = manager.get_subscribed_channels(client_id)
                await websocket.send_json({
                    "type": "subscriptions",
                    "payload": {
                        "channels": subscribed,
                    },
                })

            else:
                await websocket.send_json({
                    "type": "error",
                    "payload": {
                        "message": f"Unknown message type: {message_type}",
                    },
                })

    except WebSocketDisconnect:
        manager.disconnect(client_id)

    except Exception as e:
        logger.error(
            "WebSocket error",
            client_id=client_id,
            error=str(e),
            exc_info=True,
        )
        manager.disconnect(client_id)


# ============================================================================
# Broadcast Helper Functions
# ============================================================================


async def broadcast_backtest_progress(
    backtest_id: str,
    progress: float,
    status: str,
    current_symbol: Optional[str] = None,
) -> int:
    """
    Broadcast backtest progress update to subscribed clients.

    Args:
        backtest_id: Unique backtest identifier.
        progress: Progress value between 0.0 and 1.0.
        status: Current status (pending, running, completed, failed, cancelled).
        current_symbol: Currently processing symbol (optional).

    Returns:
        int: Number of clients the message was sent to.
    """
    message = {
        "type": "backtest:progress",
        "payload": {
            "backtest_id": backtest_id,
            "progress": progress,
            "status": status,
            "current_symbol": current_symbol,
        },
    }
    return await manager.broadcast_to_channel("backtest", message)


async def broadcast_backtest_completed(
    backtest_id: str,
    results: dict[str, Any],
) -> int:
    """
    Broadcast backtest completion notification.

    Args:
        backtest_id: Unique backtest identifier.
        results: Backtest results summary.

    Returns:
        int: Number of clients the message was sent to.
    """
    message = {
        "type": "backtest:completed",
        "payload": {
            "backtest_id": backtest_id,
            "results": results,
        },
    }
    return await manager.broadcast_to_channel("backtest", message)


async def broadcast_backtest_failed(
    backtest_id: str,
    error: str,
) -> int:
    """
    Broadcast backtest failure notification.

    Args:
        backtest_id: Unique backtest identifier.
        error: Error message.

    Returns:
        int: Number of clients the message was sent to.
    """
    message = {
        "type": "backtest:failed",
        "payload": {
            "backtest_id": backtest_id,
            "error": error,
        },
    }
    return await manager.broadcast_to_channel("backtest", message)


async def broadcast_trade_signal(
    symbol: str,
    direction: str,
    strategy_id: str,
    entry_price: float,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """
    Broadcast trade signal to subscribed clients.

    Args:
        symbol: Trading symbol.
        direction: Trade direction (long/short).
        strategy_id: Strategy identifier.
        entry_price: Entry price.
        stop_loss: Stop loss level (optional).
        take_profit: Take profit level (optional).
        metadata: Additional signal metadata (optional).

    Returns:
        int: Number of clients the message was sent to.
    """
    message = {
        "type": "signal:new",
        "payload": {
            "symbol": symbol,
            "direction": direction,
            "strategy_id": strategy_id,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "metadata": metadata or {},
        },
    }
    return await manager.broadcast_to_channel("signals", message)


async def broadcast_position_update(
    position_id: str,
    symbol: str,
    status: str,
    unrealized_pnl: Optional[float] = None,
    realized_pnl: Optional[float] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """
    Broadcast position update to subscribed clients.

    Args:
        position_id: Position identifier.
        symbol: Trading symbol.
        status: Position status.
        unrealized_pnl: Unrealized P&L (optional).
        realized_pnl: Realized P&L (optional).
        metadata: Additional position metadata (optional).

    Returns:
        int: Number of clients the message was sent to.
    """
    message = {
        "type": "position:update",
        "payload": {
            "position_id": position_id,
            "symbol": symbol,
            "status": status,
            "unrealized_pnl": unrealized_pnl,
            "realized_pnl": realized_pnl,
            "metadata": metadata or {},
        },
    }
    return await manager.broadcast_to_channel("positions", message)


async def broadcast_system_notification(
    title: str,
    message: str,
    level: str = "info",
    metadata: Optional[dict[str, Any]] = None,
) -> int:
    """
    Broadcast system notification to all connected clients.

    Args:
        title: Notification title.
        message: Notification message.
        level: Notification level (info, warning, error).
        metadata: Additional metadata (optional).

    Returns:
        int: Number of clients the message was sent to.
    """
    notification = {
        "type": "system:notification",
        "payload": {
            "title": title,
            "message": message,
            "level": level,
            "metadata": metadata or {},
        },
    }
    return await manager.broadcast_to_all(notification)
