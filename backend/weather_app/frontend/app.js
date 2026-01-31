const cityInput = document.getElementById('city-input');
const weatherCard = document.getElementById('weather-card');
const errorDiv = document.getElementById('error');

cityInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') searchWeather();
});

async function searchWeather() {
    const city = cityInput.value.trim();
    if (!city) return;

    errorDiv.classList.add('hidden');
    weatherCard.classList.add('hidden');

    try {
        const [weatherRes, forecastRes] = await Promise.all([
            fetch(`/api/weather/${encodeURIComponent(city)}`),
            fetch(`/api/forecast/${encodeURIComponent(city)}`)
        ]);

        if (!weatherRes.ok) throw new Error('City not found');

        const weather = await weatherRes.json();
        const forecast = await forecastRes.json();

        displayWeather(weather);
        displayForecast(forecast);
        weatherCard.classList.remove('hidden');
    } catch (err) {
        errorDiv.textContent = err.message || 'Failed to fetch weather';
        errorDiv.classList.remove('hidden');
    }
}

function displayWeather(data) {
    document.getElementById('city-name').textContent = data.city;
    document.getElementById('temperature').textContent = `${data.temp}°`;
    document.getElementById('description').textContent = data.description;
    document.getElementById('humidity').textContent = data.humidity;
    document.getElementById('feels-like').textContent = data.feels_like;
    document.getElementById('wind').textContent = data.wind_speed;
    document.getElementById('weather-icon').src = 
        `https://openweathermap.org/img/wn/${data.icon}@2x.png`;
}

function displayForecast(data) {
    const container = document.getElementById('forecast-container');
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    
    container.innerHTML = data.forecast.map((day, i) => {
        const date = new Date();
        date.setDate(date.getDate() + i + 1);
        const dayName = days[date.getDay()];
        
        return `
            <div class="forecast-day">
                <div class="day">${dayName}</div>
                <img src="https://openweathermap.org/img/wn/${day.icon}.png" alt="">
                <div class="temp">${day.temp}°</div>
            </div>
        `;
    }).join('');
}

// Load default city
searchWeather.call(null, 'London');
cityInput.value = 'London';
setTimeout(searchWeather, 100);
