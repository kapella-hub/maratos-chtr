"""Fixtures for persistence tests."""

import asyncio
import os
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Must set before any app imports
os.environ["MARATOS_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
def event_loop():
    """Create a new event loop for each test function."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_db(tmp_path):
    """Create a fresh test database for each test.

    This fixture:
    1. Creates a new file-based SQLite database
    2. Creates all tables
    3. Patches the app's async_session_factory and engine
    4. Restores the original after the test
    """
    # Import here to ensure env vars are set first
    from app.database import Base
    import app.database as db_module

    # Save original factory and engine
    original_factory = db_module.async_session_factory
    original_engine = db_module.engine

    # Use a file-based SQLite database for reliable table persistence
    db_path = tmp_path / "test.db"
    db_url = f"sqlite+aiosqlite:///{db_path}"

    # Create a test engine
    test_engine = create_async_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,  # Set to True for SQL debugging
    )

    # Create all tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create and patch session factory
    test_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    # Patch the db_module - repositories import from db_module.async_session_factory
    db_module.async_session_factory = test_factory
    db_module.engine = test_engine

    yield test_factory

    # Restore original
    db_module.async_session_factory = original_factory
    db_module.engine = original_engine

    # Cleanup
    await test_engine.dispose()
