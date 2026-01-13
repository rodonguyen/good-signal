"""
Bybit exchange client for live trading operations.

Provides async methods for order placement, position management,
and account operations using ccxt library.
"""

import os
from datetime import datetime
from typing import Any, Optional

import ccxt.async_support as ccxt

from backend.core.exceptions import TradingError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class BybitClient:
    """
    Async client for Bybit exchange operations.

    Handles order placement, position management, and account queries
    with proper error handling and logging.

    Environment Variables:
        BYBIT_API_KEY: Bybit API key
        BYBIT_API_SECRET: Bybit API secret
        BYBIT_TESTNET: Set to "true" to use testnet (default: false)

    Example:
        >>> client = BybitClient()
        >>> await client.connect()
        >>> balance = await client.get_balance()
        >>> await client.close()
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: Optional[bool] = None,
    ) -> None:
        """
        Initialize Bybit client.

        Args:
            api_key: Bybit API key (defaults to BYBIT_API_KEY env var)
            api_secret: Bybit API secret (defaults to BYBIT_API_SECRET env var)
            testnet: Use testnet instead of mainnet (defaults to BYBIT_TESTNET env var)
        """
        self._api_key = api_key or os.getenv("BYBIT_API_KEY")
        self._api_secret = api_secret or os.getenv("BYBIT_API_SECRET")
        self._testnet = (
            testnet
            if testnet is not None
            else os.getenv("BYBIT_TESTNET", "false").lower() == "true"
        )

        if not self._api_key or not self._api_secret:
            logger.warning(
                "Bybit API credentials not configured - client will operate in read-only mode"
            )

        self._exchange: Optional[ccxt.bybit] = None
        self._connected = False

    async def connect(self) -> None:
        """
        Initialize connection to Bybit exchange.

        Creates ccxt exchange instance with proper configuration
        for derivatives (perpetual futures) trading.

        Raises:
            TradingError: If connection initialization fails
        """
        if self._connected and self._exchange:
            logger.debug("Bybit client already connected")
            return

        try:
            config: dict[str, Any] = {
                "enableRateLimit": True,
                "options": {
                    "defaultType": "linear",  # USDT-margined perpetual futures
                },
            }

            if self._api_key and self._api_secret:
                config["apiKey"] = self._api_key
                config["secret"] = self._api_secret

            # Use testnet if configured
            if self._testnet:
                config["urls"] = {
                    "api": {
                        "public": "https://api-testnet.bybit.com",
                        "private": "https://api-testnet.bybit.com",
                    }
                }
                logger.info("Connecting to Bybit TESTNET")
            else:
                logger.info("Connecting to Bybit MAINNET")

            self._exchange = ccxt.bybit(config)
            await self._exchange.load_markets()

            self._connected = True
            logger.info(
                "Bybit client connected successfully",
                testnet=self._testnet,
                authenticated=bool(self._api_key),
            )

        except Exception as e:
            logger.error("Failed to connect to Bybit", error=str(e))
            raise TradingError(
                message=f"Failed to initialize Bybit connection: {e}",
                error_code="BYBIT_CONNECTION_FAILED",
                details={"error": str(e), "testnet": self._testnet},
            )

    async def close(self) -> None:
        """
        Close connection to Bybit exchange.

        Cleans up resources and closes the ccxt exchange instance.
        """
        if self._exchange:
            await self._exchange.close()
            self._connected = False
            logger.info("Bybit client connection closed")

    def _ensure_connected(self) -> None:
        """
        Ensure client is connected before operations.

        Raises:
            TradingError: If client is not connected
        """
        if not self._connected or not self._exchange:
            raise TradingError(
                message="Bybit client not connected. Call connect() first.",
                error_code="BYBIT_NOT_CONNECTED",
            )

    def _ensure_authenticated(self) -> None:
        """
        Ensure client has API credentials for authenticated operations.

        Raises:
            TradingError: If client is not authenticated
        """
        if not self._api_key or not self._api_secret:
            raise TradingError(
                message="Bybit client not authenticated. Provide API credentials.",
                error_code="BYBIT_NOT_AUTHENTICATED",
            )

    async def get_balance(self, currency: str = "USDT") -> dict[str, float]:
        """
        Get account balance for specified currency.

        Args:
            currency: Currency to query (default: USDT)

        Returns:
            dict with keys: free, used, total

        Raises:
            TradingError: If balance query fails
        """
        self._ensure_connected()
        self._ensure_authenticated()

        try:
            balance = await self._exchange.fetch_balance()  # type: ignore

            currency_balance = balance.get(currency, {})
            result = {
                "free": float(currency_balance.get("free", 0.0)),
                "used": float(currency_balance.get("used", 0.0)),
                "total": float(currency_balance.get("total", 0.0)),
            }

            logger.debug(
                "Fetched account balance",
                currency=currency,
                balance=result,
            )
            return result

        except ccxt.NetworkError as e:
            logger.error("Network error fetching balance", error=str(e))
            raise TradingError(
                message=f"Network error fetching balance: {e}",
                error_code="BYBIT_NETWORK_ERROR",
                details={"error": str(e)},
            )
        except ccxt.ExchangeError as e:
            logger.error("Exchange error fetching balance", error=str(e))
            raise TradingError(
                message=f"Exchange error fetching balance: {e}",
                error_code="BYBIT_EXCHANGE_ERROR",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.error("Unexpected error fetching balance", error=str(e))
            raise TradingError(
                message=f"Failed to fetch balance: {e}",
                error_code="BYBIT_BALANCE_ERROR",
                details={"error": str(e)},
            )

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """
        Place a market order.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: Order side ('buy' or 'sell')
            quantity: Order quantity in base currency
            reduce_only: If True, order can only reduce position

        Returns:
            dict with order details: id, symbol, side, type, price, amount, status, etc.

        Raises:
            TradingError: If order placement fails
        """
        self._ensure_connected()
        self._ensure_authenticated()

        try:
            params = {}
            if reduce_only:
                params["reduce_only"] = True

            order = await self._exchange.create_market_order(  # type: ignore
                symbol=symbol,
                side=side,
                amount=quantity,
                params=params,
            )

            logger.info(
                "Market order placed",
                order_id=order.get("id"),
                symbol=symbol,
                side=side,
                quantity=quantity,
                reduce_only=reduce_only,
            )

            return order

        except ccxt.InsufficientFunds as e:
            logger.error("Insufficient funds for order", error=str(e))
            raise TradingError(
                message=f"Insufficient funds: {e}",
                error_code="BYBIT_INSUFFICIENT_FUNDS",
                details={"symbol": symbol, "side": side, "quantity": quantity},
            )
        except ccxt.InvalidOrder as e:
            logger.error("Invalid order parameters", error=str(e))
            raise TradingError(
                message=f"Invalid order: {e}",
                error_code="BYBIT_INVALID_ORDER",
                details={"symbol": symbol, "side": side, "quantity": quantity},
            )
        except ccxt.NetworkError as e:
            logger.error("Network error placing order", error=str(e))
            raise TradingError(
                message=f"Network error placing order: {e}",
                error_code="BYBIT_NETWORK_ERROR",
                details={"error": str(e)},
            )
        except ccxt.ExchangeError as e:
            logger.error("Exchange error placing order", error=str(e))
            raise TradingError(
                message=f"Exchange error placing order: {e}",
                error_code="BYBIT_EXCHANGE_ERROR",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.error("Unexpected error placing order", error=str(e))
            raise TradingError(
                message=f"Failed to place market order: {e}",
                error_code="BYBIT_ORDER_ERROR",
                details={"error": str(e)},
            )

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        reduce_only: bool = False,
    ) -> dict[str, Any]:
        """
        Place a limit order.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')
            side: Order side ('buy' or 'sell')
            quantity: Order quantity in base currency
            price: Limit price
            reduce_only: If True, order can only reduce position

        Returns:
            dict with order details: id, symbol, side, type, price, amount, status, etc.

        Raises:
            TradingError: If order placement fails
        """
        self._ensure_connected()
        self._ensure_authenticated()

        try:
            params = {}
            if reduce_only:
                params["reduce_only"] = True

            order = await self._exchange.create_limit_order(  # type: ignore
                symbol=symbol,
                side=side,
                amount=quantity,
                price=price,
                params=params,
            )

            logger.info(
                "Limit order placed",
                order_id=order.get("id"),
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=price,
                reduce_only=reduce_only,
            )

            return order

        except ccxt.InsufficientFunds as e:
            logger.error("Insufficient funds for order", error=str(e))
            raise TradingError(
                message=f"Insufficient funds: {e}",
                error_code="BYBIT_INSUFFICIENT_FUNDS",
                details={
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                },
            )
        except ccxt.InvalidOrder as e:
            logger.error("Invalid order parameters", error=str(e))
            raise TradingError(
                message=f"Invalid order: {e}",
                error_code="BYBIT_INVALID_ORDER",
                details={
                    "symbol": symbol,
                    "side": side,
                    "quantity": quantity,
                    "price": price,
                },
            )
        except ccxt.NetworkError as e:
            logger.error("Network error placing order", error=str(e))
            raise TradingError(
                message=f"Network error placing order: {e}",
                error_code="BYBIT_NETWORK_ERROR",
                details={"error": str(e)},
            )
        except ccxt.ExchangeError as e:
            logger.error("Exchange error placing order", error=str(e))
            raise TradingError(
                message=f"Exchange error placing order: {e}",
                error_code="BYBIT_EXCHANGE_ERROR",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.error("Unexpected error placing order", error=str(e))
            raise TradingError(
                message=f"Failed to place limit order: {e}",
                error_code="BYBIT_ORDER_ERROR",
                details={"error": str(e)},
            )

    async def cancel_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """
        Cancel an open order.

        Args:
            order_id: Exchange order ID
            symbol: Trading symbol

        Returns:
            dict with cancellation details

        Raises:
            TradingError: If order cancellation fails
        """
        self._ensure_connected()
        self._ensure_authenticated()

        try:
            result = await self._exchange.cancel_order(  # type: ignore
                id=order_id,
                symbol=symbol,
            )

            logger.info(
                "Order cancelled",
                order_id=order_id,
                symbol=symbol,
            )

            return result

        except ccxt.OrderNotFound as e:
            logger.error("Order not found for cancellation", error=str(e))
            raise TradingError(
                message=f"Order not found: {e}",
                error_code="BYBIT_ORDER_NOT_FOUND",
                details={"order_id": order_id, "symbol": symbol},
            )
        except ccxt.NetworkError as e:
            logger.error("Network error cancelling order", error=str(e))
            raise TradingError(
                message=f"Network error cancelling order: {e}",
                error_code="BYBIT_NETWORK_ERROR",
                details={"error": str(e)},
            )
        except ccxt.ExchangeError as e:
            logger.error("Exchange error cancelling order", error=str(e))
            raise TradingError(
                message=f"Exchange error cancelling order: {e}",
                error_code="BYBIT_EXCHANGE_ERROR",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.error("Unexpected error cancelling order", error=str(e))
            raise TradingError(
                message=f"Failed to cancel order: {e}",
                error_code="BYBIT_CANCEL_ERROR",
                details={"error": str(e)},
            )

    async def get_order_status(self, order_id: str, symbol: str) -> dict[str, Any]:
        """
        Get order status and details.

        Args:
            order_id: Exchange order ID
            symbol: Trading symbol

        Returns:
            dict with order details: status, filled, remaining, etc.

        Raises:
            TradingError: If order query fails
        """
        self._ensure_connected()
        self._ensure_authenticated()

        try:
            order = await self._exchange.fetch_order(  # type: ignore
                id=order_id,
                symbol=symbol,
            )

            logger.debug(
                "Fetched order status",
                order_id=order_id,
                status=order.get("status"),
            )

            return order

        except ccxt.OrderNotFound as e:
            logger.error("Order not found", error=str(e))
            raise TradingError(
                message=f"Order not found: {e}",
                error_code="BYBIT_ORDER_NOT_FOUND",
                details={"order_id": order_id, "symbol": symbol},
            )
        except ccxt.NetworkError as e:
            logger.error("Network error fetching order", error=str(e))
            raise TradingError(
                message=f"Network error fetching order: {e}",
                error_code="BYBIT_NETWORK_ERROR",
                details={"error": str(e)},
            )
        except ccxt.ExchangeError as e:
            logger.error("Exchange error fetching order", error=str(e))
            raise TradingError(
                message=f"Exchange error fetching order: {e}",
                error_code="BYBIT_EXCHANGE_ERROR",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.error("Unexpected error fetching order", error=str(e))
            raise TradingError(
                message=f"Failed to get order status: {e}",
                error_code="BYBIT_ORDER_STATUS_ERROR",
                details={"error": str(e)},
            )

    async def get_positions(self, symbol: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Get open positions from exchange.

        Args:
            symbol: Optional symbol filter (e.g., 'BTCUSDT')

        Returns:
            list of position dicts with details: symbol, side, size, entry_price, etc.

        Raises:
            TradingError: If position query fails
        """
        self._ensure_connected()
        self._ensure_authenticated()

        try:
            positions = await self._exchange.fetch_positions(  # type: ignore
                symbols=[symbol] if symbol else None
            )

            # Filter out zero positions
            open_positions = [
                pos
                for pos in positions
                if pos.get("contracts", 0) != 0 or pos.get("contractSize", 0) != 0
            ]

            logger.debug(
                "Fetched positions",
                count=len(open_positions),
                symbol=symbol,
            )

            return open_positions

        except ccxt.NetworkError as e:
            logger.error("Network error fetching positions", error=str(e))
            raise TradingError(
                message=f"Network error fetching positions: {e}",
                error_code="BYBIT_NETWORK_ERROR",
                details={"error": str(e)},
            )
        except ccxt.ExchangeError as e:
            logger.error("Exchange error fetching positions", error=str(e))
            raise TradingError(
                message=f"Exchange error fetching positions: {e}",
                error_code="BYBIT_EXCHANGE_ERROR",
                details={"error": str(e)},
            )
        except Exception as e:
            logger.error("Unexpected error fetching positions", error=str(e))
            raise TradingError(
                message=f"Failed to get positions: {e}",
                error_code="BYBIT_POSITIONS_ERROR",
                details={"error": str(e)},
            )

    async def close_position(self, symbol: str) -> dict[str, Any]:
        """
        Close entire position for a symbol.

        Places a market order to close the current position.

        Args:
            symbol: Trading symbol (e.g., 'BTCUSDT')

        Returns:
            dict with order details

        Raises:
            TradingError: If position closure fails or no position exists
        """
        self._ensure_connected()
        self._ensure_authenticated()

        try:
            # Get current position
            positions = await self.get_positions(symbol=symbol)

            if not positions:
                raise TradingError(
                    message=f"No open position found for {symbol}",
                    error_code="BYBIT_NO_POSITION",
                    details={"symbol": symbol},
                )

            position = positions[0]
            contracts = position.get("contracts", 0)
            side = position.get("side")

            if contracts == 0:
                raise TradingError(
                    message=f"Position size is zero for {symbol}",
                    error_code="BYBIT_NO_POSITION",
                    details={"symbol": symbol},
                )

            # Determine closing side (opposite of position side)
            close_side = "sell" if side == "long" else "buy"

            # Place market order to close position
            order = await self.place_market_order(
                symbol=symbol,
                side=close_side,
                quantity=abs(contracts),
                reduce_only=True,
            )

            logger.info(
                "Position closed",
                symbol=symbol,
                side=side,
                contracts=contracts,
                order_id=order.get("id"),
            )

            return order

        except TradingError:
            raise
        except Exception as e:
            logger.error("Unexpected error closing position", error=str(e))
            raise TradingError(
                message=f"Failed to close position: {e}",
                error_code="BYBIT_CLOSE_POSITION_ERROR",
                details={"symbol": symbol, "error": str(e)},
            )

    @property
    def is_connected(self) -> bool:
        """Check if client is connected."""
        return self._connected

    @property
    def is_testnet(self) -> bool:
        """Check if using testnet."""
        return self._testnet
