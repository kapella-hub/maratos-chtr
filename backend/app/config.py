"""Configuration management for MaratOS."""

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Path for persisted settings
SETTINGS_FILE = Path("./data/settings.json")


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
    skills_dir: Path = Field(default_factory=lambda: Path.home() / ".maratos" / "skills")

    # Filesystem Security - directories where writes are allowed
    # Comma-separated list of paths. Writes allowed in these dirs and their subdirs.
    # Example: "/Users/me/Projects,/tmp/scratch"
    # If empty, only workspace_dir allows writes.
    allowed_write_dirs: str = ""

    # Limits
    max_context_tokens: int = 100000
    max_response_tokens: int = 8192

    # Timeouts (seconds)
    llm_timeout: int = 120  # 2 minutes for LLM calls
    tool_timeout: int = 60  # 1 minute for tool execution
    http_timeout: int = 30  # 30 seconds for HTTP requests

    # Message history settings
    max_history_messages: int = 50  # Max messages to load from history
    summarize_after_messages: int = 30  # Summarize older messages after this threshold

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_chat: str = "20/minute"  # Chat endpoint limit
    rate_limit_default: str = "100/minute"  # Default limit for other endpoints
    
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

    # === Git Settings ===
    git_auto_commit: bool = True  # Auto-commit changes after tasks
    git_push_to_remote: bool = False  # Push to remote after commits
    git_create_pr: bool = False  # Create PR when project completes
    git_default_branch: str = "main"  # Default base branch for PRs
    git_commit_prefix: str = ""  # Optional prefix for commit messages (e.g., "[AUTO]")
    git_remote_name: str = "origin"  # Git remote name

    # === GitLab Integration ===
    gitlab_url: str = ""  # GitLab instance URL (e.g., https://gitlab.example.com)
    gitlab_token: str = ""  # Personal access token with api scope
    gitlab_namespace: str = ""  # Default namespace/group for new projects (e.g., group/subgroup)
    gitlab_skip_ssl: bool = False  # Skip SSL verification (for internal servers with self-signed certs)

    @field_validator("gitlab_url")
    @classmethod
    def validate_gitlab_url(cls, v: str) -> str:
        """Validate GitLab URL format."""
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("GitLab URL must start with http:// or https://")
        return v.rstrip("/") if v else v

    @field_validator("rate_limit_chat", "rate_limit_default")
    @classmethod
    def validate_rate_limit(cls, v: str) -> str:
        """Validate rate limit format (e.g., '20/minute')."""
        if "/" not in v:
            raise ValueError("Rate limit must be in format 'N/period' (e.g., '20/minute')")
        return v


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
    """Update config values and persist to file."""
    for key, value in updates.items():
        if hasattr(settings, key):
            setattr(settings, key, value)

    # Persist to file
    save_settings()


def save_settings() -> None:
    """Save current settings to file."""
    # Only save settings that should persist (not from .env)
    persist_keys = [
        "default_model", "debug", "allowed_write_dirs",
        "telegram_enabled", "telegram_token", "telegram_allowed_users",
        "imessage_enabled", "imessage_allowed_senders",
        "webex_enabled", "webex_token", "webex_webhook_secret",
        "webex_allowed_users", "webex_allowed_rooms",
        # Git settings
        "git_auto_commit", "git_push_to_remote", "git_create_pr",
        "git_default_branch", "git_commit_prefix", "git_remote_name",
        # GitLab integration
        "gitlab_url", "gitlab_token", "gitlab_namespace", "gitlab_skip_ssl",
    ]

    data = {}
    for key in persist_keys:
        if hasattr(settings, key):
            value = getattr(settings, key)
            # Convert Path to string
            if isinstance(value, Path):
                value = str(value)
            data[key] = value

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_settings() -> None:
    """Load settings from file on startup."""
    if not SETTINGS_FILE.exists():
        return

    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)

        # Validate settings before applying
        # Create a test settings object to check for validation errors
        try:
            current_dict = settings.model_dump()
            current_dict.update({k: v for k, v in data.items() if v is not None})
            Settings(**current_dict)  # This will raise ValidationError if invalid
        except ValidationError as e:
            logger.warning(f"Settings validation failed, using defaults: {e}")
            return

        # Apply validated settings
        for key, value in data.items():
            if hasattr(settings, key) and value is not None:
                setattr(settings, key, value)

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in settings file: {e}")
    except Exception as e:
        logger.error(f"Could not load settings: {e}")


def get_allowed_write_dirs() -> list[Path]:
    """Get all directories where writes are allowed.

    Returns workspace_dir plus any custom allowed_write_dirs.
    """
    dirs = [settings.workspace_dir]

    if settings.allowed_write_dirs:
        for dir_str in settings.allowed_write_dirs.split(","):
            dir_str = dir_str.strip()
            if dir_str:
                path = Path(dir_str).expanduser().resolve()
                if path not in dirs:
                    dirs.append(path)

    return dirs


def validate_critical_settings() -> None:
    """Validate critical settings and log warnings for potential issues."""
    # Check for missing API key
    if not settings.anthropic_api_key:
        logger.warning(
            "MARATOS_ANTHROPIC_API_KEY not set - LLM calls will fail. "
            "Set this environment variable or add to .env file."
        )

    # Warn about SSL skip
    if settings.gitlab_skip_ssl:
        logger.warning(
            "GitLab SSL verification is disabled (gitlab_skip_ssl=True). "
            "Only use this in development with self-signed certificates."
        )

    # Warn about debug mode in production-like settings
    if settings.debug and settings.host == "0.0.0.0":
        logger.warning(
            "Running in debug mode with public host binding (0.0.0.0). "
            "Disable debug mode for production deployments."
        )


# Load persisted settings on startup
load_settings()
validate_critical_settings()
