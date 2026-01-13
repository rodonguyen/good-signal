"""
Application configuration using Pydantic Settings.

Loads configuration from environment variables with sensible defaults
for development. Production deployments should set all values explicitly.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Attributes:
        DATABASE_URL: Database connection string (async driver recommended)
        DEBUG: Enable debug mode (disable in production)
        MAX_BACKTEST_WORKERS: Maximum concurrent backtest workers
        LOG_LEVEL: Logging level for the application
        APP_NAME: Application name for logging and identification
        APP_VERSION: Application version string
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Database configuration
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./data/db/good_signal.db",
        description="Database connection URL (use async driver for production)",
    )

    # Application mode
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode (disable in production)",
    )

    # Worker configuration
    MAX_BACKTEST_WORKERS: int = Field(
        default=2,
        ge=1,
        le=16,
        description="Maximum number of concurrent backtest workers",
    )

    # Logging configuration
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Application logging level",
    )

    # Application metadata
    APP_NAME: str = Field(
        default="good-signal",
        description="Application name",
    )

    APP_VERSION: str = Field(
        default="1.0.0",
        description="Application version",
    )

    # CORS configuration
    CORS_ORIGINS: list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://localhost:5175",
            "http://localhost:5176",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5175",
            "http://127.0.0.1:5176",
        ],
        description="Allowed CORS origins",
    )

    # Discord notifications
    DISCORD_WEBHOOK_URL: str = Field(
        default="",
        description="Discord webhook URL for trade notifications",
    )

    # Bybit API configuration
    BYBIT_API_KEY: str = Field(
        default="",
        description="Bybit API key for trading",
    )
    BYBIT_API_SECRET: str = Field(
        default="",
        description="Bybit API secret for trading",
    )
    BYBIT_TESTNET: bool = Field(
        default=True,
        description="Use Bybit testnet instead of mainnet",
    )

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def uppercase_log_level(cls, v: str) -> str:
        """Ensure log level is uppercase."""
        if isinstance(v, str):
            return v.upper()
        return v

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return "sqlite" in self.DATABASE_URL.lower()

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.DEBUG


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are loaded only once
    and reused across the application lifecycle.

    Returns:
        Settings instance with loaded configuration.
    """
    return Settings()
