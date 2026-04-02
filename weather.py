"""
weather.py — Fetch current weather + 24h precipitation probability from Open-Meteo.
No API key required. Results cached in memory for 30 minutes per farm.
"""

import time
import urllib.request
import urllib.parse
import json

# In-memory cache: { farm_id: { 'data': {...}, 'fetched_at': timestamp } }
_cache = {}
CACHE_TTL = 1800  # 30 minutes

# WMO Weather Code descriptions
_WMO_CODES = {
    0:  ('Clear Sky',           '☀️'),
    1:  ('Mainly Clear',        '🌤️'),
    2:  ('Partly Cloudy',       '⛅'),
    3:  ('Overcast',            '☁️'),
    45: ('Foggy',               '🌫️'),
    48: ('Icy Fog',             '🌫️'),
    51: ('Light Drizzle',       '🌦️'),
    53: ('Drizzle',             '🌦️'),
    55: ('Heavy Drizzle',       '🌧️'),
    61: ('Light Rain',          '🌧️'),
    63: ('Rain',                '🌧️'),
    65: ('Heavy Rain',          '🌧️'),
    71: ('Light Snow',          '🌨️'),
    73: ('Snow',                '🌨️'),
    75: ('Heavy Snow',          '❄️'),
    77: ('Snow Grains',         '❄️'),
    80: ('Rain Showers',        '🌦️'),
    81: ('Rain Showers',        '🌧️'),
    82: ('Violent Showers',     '⛈️'),
    85: ('Snow Showers',        '🌨️'),
    86: ('Heavy Snow Showers',  '❄️'),
    95: ('Thunderstorm',        '⛈️'),
    96: ('Thunderstorm + Hail', '⛈️'),
    99: ('Thunderstorm + Hail', '⛈️'),
}


def _describe_code(code):
    if code is None:
        return 'Unknown', '❓'
    return _WMO_CODES.get(int(code), ('Unknown', '❓'))


def fetch_weather(farm_id, lat, lng):
    """
    Fetch weather for the given coordinates.
    Returns a dict with current conditions and 24h rain probability.
    Uses cache; raises on network/parse errors.
    """
    now = time.time()
    cached = _cache.get(farm_id)
    if cached and (now - cached['fetched_at']) < CACHE_TTL:
        return cached['data']

    params = urllib.parse.urlencode({
        'latitude': lat,
        'longitude': lng,
        'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,precipitation',
        'hourly': 'temperature_2m,precipitation_probability',
        'past_hours': 23,
        'forecast_days': 1,
        'timezone': 'auto',
        'wind_speed_unit': 'kmh',
    })
    url = f'https://api.open-meteo.com/v1/forecast?{params}'

    req = urllib.request.Request(url, headers={'User-Agent': 'FarmInsights/1.0'})
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = json.loads(resp.read().decode())

    current = raw.get('current', {})
    hourly = raw.get('hourly', {})

    # Past 24 hours of temperature (first 24 values with past_hours=23 + current hour)
    temps_all = hourly.get('temperature_2m', [])
    temp_24h = [t for t in temps_all[:24] if t is not None]

    # Max precipitation probability across the next 24 hourly values (after the past 23h)
    probs = hourly.get('precipitation_probability', [])
    future_probs = probs[23:]  # skip the past hours
    rain_prob_24h = max(future_probs[:24]) if future_probs else None

    weather_code = current.get('weather_code')
    description, icon = _describe_code(weather_code)

    data = {
        'temperature': current.get('temperature_2m'),
        'humidity': current.get('relative_humidity_2m'),
        'wind_speed': current.get('wind_speed_10m'),
        'precipitation': current.get('precipitation'),
        'weather_code': weather_code,
        'description': description,
        'icon': icon,
        'rain_prob_24h': rain_prob_24h,
        'temp_24h': temp_24h,
        'timezone': raw.get('timezone'),
        'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }

    _cache[farm_id] = {'data': data, 'fetched_at': now}
    return data
