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
    default_model: str = "claude-sonnet-4-20250514"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Paths
    data_dir: Path = Field(default_factory=lambda: Path("./data"))

    # Limits
    max_context_tokens: int = 100000
    max_response_tokens: int = 8192


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


def update_config(updates: dict[str, Any]) -> None:
    """Update config values (runtime only)."""
    for key, value in updates.items():
        if hasattr(settings, key):
            setattr(settings, key, value)
