from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import os
from pathlib import Path

app = FastAPI(title="Weather App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
BASE_URL = "https://api.openweathermap.org/data/2.5"


@app.get("/api/weather/{city}")
async def get_weather(city: str):
    """Get current weather for a city."""
    if not API_KEY:
        # Return mock data if no API key
        return {
            "city": city,
            "temp": 22,
            "feels_like": 21,
            "humidity": 65,
            "description": "Partly cloudy",
            "icon": "02d",
            "wind_speed": 12,
        }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/weather",
            params={"q": city, "appid": API_KEY, "units": "metric"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="City not found")
        data = resp.json()
        return {
            "city": data["name"],
            "temp": round(data["main"]["temp"]),
            "feels_like": round(data["main"]["feels_like"]),
            "humidity": data["main"]["humidity"],
            "description": data["weather"][0]["description"].title(),
            "icon": data["weather"][0]["icon"],
            "wind_speed": round(data["wind"]["speed"] * 3.6),  # m/s to km/h
        }


@app.get("/api/forecast/{city}")
async def get_forecast(city: str):
    """Get 5-day forecast for a city."""
    if not API_KEY:
        # Return mock data
        return {
            "city": city,
            "forecast": [
                {"day": "Mon", "temp": 22, "icon": "02d"},
                {"day": "Tue", "temp": 24, "icon": "01d"},
                {"day": "Wed", "temp": 19, "icon": "10d"},
                {"day": "Thu", "temp": 21, "icon": "03d"},
                {"day": "Fri", "temp": 23, "icon": "01d"},
            ],
        }
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/forecast",
            params={"q": city, "appid": API_KEY, "units": "metric"},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="City not found")
        data = resp.json()
        
        # Get one forecast per day (noon)
        daily = {}
        for item in data["list"]:
            date = item["dt_txt"].split()[0]
            if date not in daily and "12:00:00" in item["dt_txt"]:
                daily[date] = {
                    "day": item["dt_txt"].split()[0],
                    "temp": round(item["main"]["temp"]),
                    "icon": item["weather"][0]["icon"],
                }
        
        return {"city": data["city"]["name"], "forecast": list(daily.values())[:5]}


# Serve static files
static_path = Path(__file__).parent.parent / "frontend"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=static_path), name="static")

    @app.get("/")
    async def root():
        return FileResponse(static_path / "index.html")
