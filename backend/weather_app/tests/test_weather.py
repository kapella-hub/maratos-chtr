import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from backend.main import app


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_get_weather_mock_mode(client):
    """Test weather endpoint returns mock data when no API key."""
    async with client as c:
        resp = await c.get("/api/weather/London")
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "London"
    assert "temp" in data
    assert "humidity" in data
    assert "description" in data


@pytest.mark.asyncio
async def test_get_forecast_mock_mode(client):
    """Test forecast endpoint returns mock data when no API key."""
    async with client as c:
        resp = await c.get("/api/forecast/Paris")
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "Paris"
    assert len(data["forecast"]) == 5


@pytest.mark.asyncio
async def test_weather_special_chars():
    """Test weather endpoint handles city names with spaces."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/api/weather/New%20York")
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "New York"
