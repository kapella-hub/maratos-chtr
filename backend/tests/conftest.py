"""Pytest fixtures for backend tests."""

import pytest

# Import persistence fixtures so pytest recognizes them
from tests.conftest_persistence import test_db

# Re-export so pytest can find them
__all__ = ["test_db"]


# Configure pytest-asyncio to use auto mode for async tests
# This allows async tests to work without explicit event_loop fixtures
def pytest_configure(config):
    """Configure pytest-asyncio mode."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
