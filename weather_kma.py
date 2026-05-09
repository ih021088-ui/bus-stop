import requests
from datetime import datetime

LAT, LON = 37.27, 126.99


def fetch_weather(date_str: str) -> dict:
    """date_str: YYYY-MM-DD. 과거/미래 모두 Open-Meteo 사용."""
    target = datetime.strptime(date_str, '%Y-%m-%d').date()
    today  = datetime.now().date()
    base   = (
        'https://archive-api.open-meteo.com/v1/archive'
        if target <= today else
        'https://api.open-meteo.com/v1/forecast'
    )

    r = requests.get(base, params={
        'latitude':   LAT,
        'longitude':  LON,
        'start_date': date_str,
        'end_date':   date_str,
        'daily':      'temperature_2m_max,temperature_2m_min,precipitation_sum',
        'timezone':   'Asia/Seoul',
    }, timeout=10)
    r.raise_for_status()

    daily    = r.json()['daily']
    temp_max = daily['temperature_2m_max'][0] or 15.0
    temp_min = daily['temperature_2m_min'][0] or 10.0
    precip   = daily['precipitation_sum'][0]  or 0.0
    temp_avg = round((temp_max + temp_min) / 2, 1)

    return {
        'temp_avg':  temp_avg,
        'precip_mm': precip,
        'is_rainy':  int(precip   >  0.5),
        'is_cold':   int(temp_avg <  5.0),
        'is_hot':    int(temp_avg > 28.0),
    }
