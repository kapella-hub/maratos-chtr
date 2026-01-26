"""Tests for configuration validation."""

import pytest
from pydantic import ValidationError


class TestConfigValidation:
    """Tests for Settings validation."""

    def test_gitlab_url_validation_valid_https(self):
        """Test valid HTTPS GitLab URL is accepted."""
        from app.config import Settings
        s = Settings(gitlab_url="https://gitlab.example.com")
        assert s.gitlab_url == "https://gitlab.example.com"

    def test_gitlab_url_validation_valid_http(self):
        """Test valid HTTP GitLab URL is accepted."""
        from app.config import Settings
        s = Settings(gitlab_url="http://gitlab.local")
        assert s.gitlab_url == "http://gitlab.local"

    def test_gitlab_url_validation_empty_allowed(self):
        """Test empty GitLab URL is allowed."""
        from app.config import Settings
        s = Settings(gitlab_url="")
        assert s.gitlab_url == ""

    def test_gitlab_url_validation_invalid_rejected(self):
        """Test invalid GitLab URL is rejected."""
        from app.config import Settings
        with pytest.raises(ValidationError) as exc_info:
            Settings(gitlab_url="gitlab.example.com")
        assert "http" in str(exc_info.value).lower()

    def test_gitlab_url_trailing_slash_removed(self):
        """Test trailing slash is removed from GitLab URL."""
        from app.config import Settings
        s = Settings(gitlab_url="https://gitlab.example.com/")
        assert s.gitlab_url == "https://gitlab.example.com"

    def test_rate_limit_validation_valid(self):
        """Test valid rate limit format."""
        from app.config import Settings
        s = Settings(rate_limit_chat="20/minute", rate_limit_default="100/minute")
        assert s.rate_limit_chat == "20/minute"

    def test_rate_limit_validation_invalid(self):
        """Test invalid rate limit format is rejected."""
        from app.config import Settings
        with pytest.raises(ValidationError) as exc_info:
            Settings(rate_limit_chat="20perminute")
        assert "format" in str(exc_info.value).lower() or "/" in str(exc_info.value)


class TestConfigHelpers:
    """Tests for config helper functions."""

    def test_get_allowed_write_dirs_includes_workspace(self):
        """Test workspace is always included in allowed dirs."""
        from app.config import get_allowed_write_dirs, settings
        dirs = get_allowed_write_dirs()
        assert settings.workspace_dir in dirs

    def test_get_config_dict_keys(self):
        """Test get_config_dict returns expected keys."""
        from app.config import get_config_dict
        config = get_config_dict()
        assert "app_name" in config
        assert "debug" in config
        assert "default_model" in config
        assert "max_context_tokens" in config
        assert "max_response_tokens" in config
