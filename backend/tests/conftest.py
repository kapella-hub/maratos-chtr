"""Pytest fixtures for backend tests."""

# Import persistence fixtures so pytest recognizes them
from tests.conftest_persistence import test_db, event_loop

# Re-export so pytest can find them
__all__ = ["test_db", "event_loop"]
