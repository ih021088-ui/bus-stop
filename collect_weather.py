import requests
import pandas as pd

# 수원대 좌표 (경기도 화성시)
LAT, LON = 37.27, 126.99

def fetch_weather(start_date, end_date):
    r = requests.get('https://archive-api.open-meteo.com/v1/archive', params={
        'latitude': LAT,
        'longitude': LON,
        'start_date': start_date,
        'end_date': end_date,
        'daily': ','.join([
            'temperature_2m_max',
            'temperature_2m_min',
            'precipitation_sum',
            'rain_sum',
        ]),
        'timezone': 'Asia/Seoul',
    }, timeout=15)
    r.raise_for_status()
    data = r.json()['daily']

    df = pd.DataFrame({
        'date':        data['time'],
        'temp_max':    data['temperature_2m_max'],
        'temp_min':    data['temperature_2m_min'],
        'precip_mm':   data['precipitation_sum'],
        'rain_mm':     data['rain_sum'],
    })

    # 파생 피처
    df['temp_avg']   = ((df['temp_max'] + df['temp_min']) / 2).round(1)
    df['is_rainy']   = (df['precip_mm'] > 0.5).astype(int)   # 0.5mm 이상이면 비
    df['is_cold']    = (df['temp_avg'] < 5).astype(int)       # 5도 미만 추위
    df['is_hot']     = (df['temp_avg'] > 28).astype(int)      # 28도 초과 더위

    # 날짜 포맷을 xlsx 파일명 형식으로 맞춤
    df['date'] = df['date'].str.replace('-', '_')

    return df


if __name__ == '__main__':
    print('날씨 데이터 수집 중...')
    weather = fetch_weather('2025-03-01', '2026-04-30')
    weather.to_csv('./weather.csv', index=False, encoding='utf-8-sig')
    print(f'수집 완료: {len(weather)}일치')
    print(weather.head(10).to_string(index=False))
