# Weather App

A simple weather app with FastAPI backend and vanilla JS frontend.

## Setup

```bash
cd weather_app
pip install -r requirements.txt
```

## Run

```bash
uvicorn backend.main:app --reload --port 8000
```

Open http://localhost:8000

## API Key (Optional)

For real weather data, get a free API key from [OpenWeatherMap](https://openweathermap.org/api) and set:

```bash
export OPENWEATHER_API_KEY=your_key
```

Without an API key, the app returns mock data.
