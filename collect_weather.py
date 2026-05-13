"""
날씨 데이터 수집기

- 과거 데이터: Open-Meteo (무료, 키 불필요)
- 오늘/미래 예보: 기상청 단기예보 API (KMA_API_KEY)

사용법:
  python collect_weather.py          # 오늘까지 자동 업데이트
  python collect_weather.py --full   # 전체 재수집
"""

import os
import sys
import requests
import pandas as pd
from datetime import date, timedelta
from dotenv import load_dotenv

load_dotenv()

LAT, LON = 37.27, 126.99  # 수원대 좌표 (경기도 화성시)

# 기상청 단기예보 격자 좌표 (수원대 근처: nx=60, ny=121)
KMA_NX, KMA_NY = 60, 121


def fetch_historical(start_date: str, end_date: str) -> pd.DataFrame:
    """Open-Meteo로 과거 날씨 수집 (날짜 형식: YYYY-MM-DD)"""
    r = requests.get('https://archive-api.open-meteo.com/v1/archive', params={
        'latitude': LAT,
        'longitude': LON,
        'start_date': start_date,
        'end_date': end_date,
        'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum',
        'timezone': 'Asia/Seoul',
    }, timeout=15)
    r.raise_for_status()
    data = r.json()['daily']

    df = pd.DataFrame({
        'date':      data['time'],
        'temp_max':  data['temperature_2m_max'],
        'temp_min':  data['temperature_2m_min'],
        'precip_mm': data['precipitation_sum'],
        'rain_mm':   data['rain_sum'],
    })
    return _add_derived(df)


def fetch_today_forecast() -> pd.DataFrame | None:
    """기상청 단기예보 API로 오늘 날씨 수집, 실패 시 Open-Meteo로 폴백"""
    today = date.today()

    # 1차: 기상청 단기예보
    result = _fetch_kma_today(today)
    if result is not None:
        return result

    # 2차 폴백: Open-Meteo
    print('[폴백] Open-Meteo 예보 사용')
    return _fetch_openmeteo_today(today)


def _fetch_kma_today(today: date) -> pd.DataFrame | None:
    """기상청 단기예보 API (수원대 근처 격자 nx=60, ny=121)"""
    api_key = os.getenv('KMA_API_KEY') or os.getenv('PUBLIC_DATA_API_KEY')
    if not api_key:
        print('[경고] KMA_API_KEY 없음')
        return None

    # 기상청은 하루 8회 발표(02/05/08/11/14/17/20/23시), 가장 최근 발표 시각 선택
    hour = today.hour if hasattr(today, 'hour') else 0
    base_times = [2, 5, 8, 11, 14, 17, 20, 23]
    from datetime import datetime
    current_hour = datetime.now().hour
    base_time = max((t for t in base_times if t <= current_hour), default=23)
    base_date_str = today.strftime('%Y%m%d')
    base_time_str = f'{base_time:02d}00'

    url = 'http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst'
    try:
        r = requests.get(url, params={
            'serviceKey': api_key,
            'numOfRows': 500,
            'pageNo': 1,
            'dataType': 'JSON',
            'base_date': base_date_str,
            'base_time': base_time_str,
            'nx': KMA_NX,
            'ny': KMA_NY,
        }, timeout=10)
        r.raise_for_status()
        j = r.json()
        if j['response']['header']['resultCode'] != '00':
            print(f'[경고] 기상청 API 오류: {j["response"]["header"]["resultMsg"]}')
            return None
        items = j['response']['body']['items']['item']
    except Exception as e:
        print(f'[경고] 기상청 API 실패: {e}')
        return None

    # 오늘 날짜 예보만 추출
    today_str = base_date_str
    temp_vals, pcp_vals = [], []
    for item in items:
        if item['fcstDate'] != today_str:
            continue
        if item['category'] == 'TMP':
            try:
                temp_vals.append(float(item['fcstValue']))
            except ValueError:
                pass
        if item['category'] == 'PCP':
            val = item['fcstValue']
            if val in ('강수없음', '-'):
                pcp_vals.append(0.0)
            else:
                try:
                    pcp_vals.append(float(str(val).replace('mm', '').strip()))
                except ValueError:
                    pcp_vals.append(0.0)

    if not temp_vals:
        print('[경고] 기상청 응답에 기온 데이터 없음')
        return None

    temp_max = max(temp_vals)
    temp_min = min(temp_vals)
    precip   = sum(pcp_vals)

    print(f'[기상청] 오늘 예보: 최고 {temp_max}°C / 최저 {temp_min}°C / 강수 {precip}mm')
    df = pd.DataFrame([{
        'date':      today.strftime('%Y-%m-%d'),
        'temp_max':  temp_max,
        'temp_min':  temp_min,
        'precip_mm': precip,
        'rain_mm':   precip,
    }])
    return _add_derived(df)


def _fetch_openmeteo_today(today: date) -> pd.DataFrame | None:
    """Open-Meteo 예보 API (폴백용)"""
    today_str = today.strftime('%Y-%m-%d')
    try:
        r = requests.get('https://api.open-meteo.com/v1/forecast', params={
            'latitude': LAT,
            'longitude': LON,
            'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum,rain_sum',
            'timezone': 'Asia/Seoul',
            'start_date': today_str,
            'end_date': today_str,
        }, timeout=10)
        r.raise_for_status()
        data = r.json()['daily']
    except Exception as e:
        print(f'[경고] Open-Meteo 폴백도 실패: {e}')
        return None

    print(f'[Open-Meteo] 오늘 예보: 최고 {data["temperature_2m_max"][0]}°C / 최저 {data["temperature_2m_min"][0]}°C / 강수 {data["precipitation_sum"][0]}mm')
    df = pd.DataFrame({
        'date':      data['time'],
        'temp_max':  data['temperature_2m_max'],
        'temp_min':  data['temperature_2m_min'],
        'precip_mm': data['precipitation_sum'],
        'rain_mm':   data['rain_sum'],
    })
    return _add_derived(df)


def _add_derived(df: pd.DataFrame) -> pd.DataFrame:
    df['temp_avg'] = ((df['temp_max'] + df['temp_min']) / 2).round(1)
    df['is_rainy'] = (df['precip_mm'] > 0.5).astype(int)
    df['is_cold']  = (df['temp_avg'] < 5).astype(int)
    df['is_hot']   = (df['temp_avg'] > 28).astype(int)
    df['date']     = df['date'].str.replace('-', '_')
    return df


def update_weather_csv(csv_path: str = './weather.csv', full: bool = False):
    """weather.csv를 오늘까지 최신화"""
    today_str = date.today().strftime('%Y-%m-%d')

    if not full and os.path.exists(csv_path):
        existing = pd.read_csv(csv_path)
        last_date = existing['date'].max().replace('_', '-')

        if last_date >= today_str:
            print(f'이미 최신 ({last_date}), 업데이트 불필요')
            return existing

        # 마지막 날짜 다음날부터 어제까지 과거 데이터 수집
        fetch_start = (
            pd.to_datetime(last_date) + timedelta(days=1)
        ).strftime('%Y-%m-%d')
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

        new_parts = [existing]

        if fetch_start <= yesterday:
            print(f'과거 날씨 수집: {fetch_start} ~ {yesterday}')
            hist = fetch_historical(fetch_start, yesterday)
            new_parts.append(hist)

        # 오늘 예보 추가
        today_row = fetch_today_forecast()
        if today_row is not None:
            new_parts.append(today_row)

        result = pd.concat(new_parts, ignore_index=True).drop_duplicates('date')
    else:
        print(f'전체 수집: 2025-03-01 ~ {today_str}')
        yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
        result = fetch_historical('2025-03-01', yesterday)
        today_row = fetch_today_forecast()
        if today_row is not None:
            result = pd.concat([result, today_row], ignore_index=True).drop_duplicates('date')

    result = result.sort_values('date').reset_index(drop=True)
    result.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f'저장 완료: {len(result)}일치 ({result["date"].min()} ~ {result["date"].max()})')
    return result


if __name__ == '__main__':
    full = '--full' in sys.argv
    update_weather_csv(full=full)
