"""Configuration management for MaratOS."""

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_prefix="MARATOS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "MaratOS"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/maratos.db"

    # LLM
    default_model: str = "claude-sonnet-4.5"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Paths
    data_dir: Path = Field(default_factory=lambda: Path("./data"))
    workspace_dir: Path = Field(default_factory=lambda: Path.home() / "maratos-workspace")

    # Limits
    max_context_tokens: int = 100000
    max_response_tokens: int = 8192
    
    # === Channel Settings ===
    
    # Telegram
    telegram_enabled: bool = False
    telegram_token: str | None = None
    telegram_allowed_users: str = ""  # Comma-separated user IDs
    
    # iMessage
    imessage_enabled: bool = False
    imessage_allowed_senders: str = ""  # Comma-separated phone/email
    
    # Webex
    webex_enabled: bool = False
    webex_token: str | None = None
    webex_webhook_secret: str | None = None
    webex_allowed_users: str = ""  # Comma-separated user IDs
    webex_allowed_rooms: str = ""  # Comma-separated room IDs


settings = Settings()


def get_config_dict() -> dict[str, Any]:
    """Get config as dict for API responses."""
    return {
        "app_name": settings.app_name,
        "debug": settings.debug,
        "default_model": settings.default_model,
        "max_context_tokens": settings.max_context_tokens,
        "max_response_tokens": settings.max_response_tokens,
    }


def get_channel_config() -> dict[str, Any]:
    """Get channel configuration."""
    config = {}
    
    if settings.telegram_enabled and settings.telegram_token:
        config["telegram"] = {
            "enabled": True,
            "token": settings.telegram_token,
            "allowed_users": [u.strip() for u in settings.telegram_allowed_users.split(",") if u.strip()],
        }
    
    if settings.imessage_enabled:
        config["imessage"] = {
            "enabled": True,
            "allowed_senders": [s.strip() for s in settings.imessage_allowed_senders.split(",") if s.strip()],
        }
    
    if settings.webex_enabled and settings.webex_token:
        config["webex"] = {
            "enabled": True,
            "token": settings.webex_token,
            "webhook_secret": settings.webex_webhook_secret,
            "allowed_users": [u.strip() for u in settings.webex_allowed_users.split(",") if u.strip()],
            "allowed_rooms": [r.strip() for r in settings.webex_allowed_rooms.split(",") if r.strip()],
        }
    
    return config


def update_config(updates: dict[str, Any]) -> None:
    """Update config values (runtime only)."""
    for key, value in updates.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
