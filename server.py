"""
7790 버스 혼잡도 예측 API
GET /predict?hour=15
GET /predict?hour=15&date=2026-05-13
GET /arrival          → 모든 정류장의 실시간 도착정보
GET /health
"""

import os
import pickle
import requests
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from urllib.parse import unquote

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# ── 설정 ──────────────────────────────────────────────────────────────────
API_KEY   = unquote(os.environ.get(
    'PUBLIC_DATA_API_KEY',
    'J1NNfn5UJ4zegGKBELL2lGTySAkSdNuFdugnZ0Pf5/e2OsLWJOSJOEeSiQObz15Ns1opof3iEqWhwbhTAg5U4A=='
))
GBIS_URL  = 'https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2'
ROUTE_ID  = 200000149   # 7790 경기버스

DEPART_STOPS = ['효행초등학교정문', '아이파크정문', '신명아파트', '수원대입구']
ARRIVE_STOP  = '사당역9번출구앞'
ALL_STOPS    = DEPART_STOPS + [ARRIVE_STOP]

STATION_IDS = {
    '효행초등학교정문': '233002245',
    '아이파크정문':     '233002371',
    '신명아파트':       '233002255',
    '수원대입구':       '233003021',
    '사당역9번출구앞':  '119000302',
}
CAPACITY = {0: 45, 1: 45, 2: 70}   # lowPlate → 정원

FEATURES = [
    'hour', 'weekday', 'week_num', 'sem_num',
    'is_exam', 'is_exam_mid', 'is_exam_fin', 'is_pre_exam', 'is_holiday',
    'boardings_lag1',
    'temp_avg', 'precip_mm', 'is_rainy', 'is_cold', 'is_hot',
]

# ── 앱 초기화 ─────────────────────────────────────────────────────────────
app = FastAPI(title='7790 버스 예측 API')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')
if os.path.isdir(FRONTEND_DIR):
    app.mount('/static', StaticFiles(directory=FRONTEND_DIR), name='static')

@app.get('/')
def root():
    index = os.path.join(FRONTEND_DIR, 'index.html')
    if os.path.exists(index):
        return FileResponse(index)
    return {'status': 'ok'}

# ── 모델 & 데이터 로드 ────────────────────────────────────────────────────
MODEL_DIR = './models'
models: dict = {}
history: pd.DataFrame | None = None

def load_resources():
    global models, history
    for stop in ALL_STOPS:
        path = os.path.join(MODEL_DIR, f'model_{stop}.pkl')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                models[stop] = pickle.load(f)
    if os.path.exists('./preprocessed.csv'):
        history = pd.read_csv('./preprocessed.csv')
        history.columns = [c.lstrip('\ufeff') for c in history.columns]

load_resources()

# ── 학사 캘린더 ───────────────────────────────────────────────────────────
WEEK_MAP: dict = {}
SEM_MAP:  dict = {}
MIDTERM_SET: set = set()
FINAL_SET:   set = set()
HOLIDAYS = {'2025_03_01','2025_05_05','2025_05_06','2025_06_06','2026_03_01','2026_05_05'}

def _build_calendar():
    week_entries = [
        ('2025-03-04','2025-03-07','2025_1',1),('2025-03-10','2025-03-14','2025_1',2),
        ('2025-03-17','2025-03-21','2025_1',3),('2025-03-24','2025-03-28','2025_1',4),
        ('2025-03-31','2025-04-04','2025_1',5),('2025-04-07','2025-04-11','2025_1',6),
        ('2025-04-14','2025-04-18','2025_1',7),('2025-04-21','2025-04-25','2025_1',8),
        ('2025-04-28','2025-05-02','2025_1',9),('2025-05-05','2025-05-09','2025_1',10),
        ('2025-05-12','2025-05-16','2025_1',11),('2025-05-19','2025-05-23','2025_1',12),
        ('2025-05-26','2025-05-30','2025_1',13),('2025-06-02','2025-06-06','2025_1',14),
        ('2025-06-09','2025-06-13','2025_1',15),('2025-06-16','2025-06-20','2025_1',16),
        ('2025-06-23','2025-06-27','2025_1',17),
        ('2025-08-25','2025-08-29','2025_2',1),('2025-09-01','2025-09-05','2025_2',2),
        ('2025-09-08','2025-09-12','2025_2',3),
        ('2026-03-04','2026-03-06','2026_1',1),('2026-03-09','2026-03-13','2026_1',2),
        ('2026-03-16','2026-03-20','2026_1',3),('2026-03-23','2026-03-27','2026_1',4),
        ('2026-03-30','2026-04-03','2026_1',5),('2026-04-06','2026-04-10','2026_1',6),
        ('2026-04-13','2026-04-17','2026_1',7),('2026-04-20','2026-04-24','2026_1',8),
        ('2026-04-27','2026-05-01','2026_1',9),('2026-05-04','2026-05-08','2026_1',10),
        ('2026-05-11','2026-05-15','2026_1',11),('2026-05-18','2026-05-22','2026_1',12),
        ('2026-05-25','2026-05-29','2026_1',13),('2026-06-01','2026-06-05','2026_1',14),
        ('2026-06-08','2026-06-12','2026_1',15),('2026-06-15','2026-06-19','2026_1',16),
    ]
    for s, e, sem, wk in week_entries:
        d = datetime.strptime(s, '%Y-%m-%d')
        end = datetime.strptime(e, '%Y-%m-%d')
        while d <= end:
            key = d.strftime('%Y_%m_%d')
            WEEK_MAP[key] = wk
            SEM_MAP[key]  = sem
            d += timedelta(days=1)

    def dr(s, e):
        d, end, res = datetime.strptime(s,'%Y-%m-%d'), datetime.strptime(e,'%Y-%m-%d'), set()
        while d <= end:
            res.add(d.strftime('%Y_%m_%d')); d += timedelta(days=1)
        return res

    MIDTERM_SET.update(dr('2025-04-16','2025-04-30') | dr('2026-04-16','2026-04-30'))
    FINAL_SET.update(dr('2025-06-04','2025-06-17'))

_build_calendar()

PRE_EXAM_WEEKS = {('2025_1',6),('2026_1',6),('2025_1',13)}

def get_calendar_features(dt: datetime) -> dict:
    key      = dt.strftime('%Y_%m_%d')
    sem      = SEM_MAP.get(key, 'unknown')
    week_num = WEEK_MAP.get(key, -1)
    sem_num  = int(sem.split('_')[1]) if sem != 'unknown' else -1
    is_mid   = int(key in MIDTERM_SET)
    is_fin   = int(key in FINAL_SET)
    return {
        'week_num':    week_num,
        'sem_num':     sem_num,
        'is_exam':     int(is_mid or is_fin),
        'is_exam_mid': is_mid,
        'is_exam_fin': is_fin,
        'is_pre_exam': int((sem, week_num) in PRE_EXAM_WEEKS),
        'is_holiday':  int(key in HOLIDAYS),
    }

# ── 날씨 조회 (기상청 단기예보 → Open-Meteo fallback) ────────────────────
KMA_URL = 'https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst'
KMA_NX, KMA_NY = 57, 119  # 화성시 봉담읍 (수원대 근처)

def _kma_base_time(dt: datetime) -> tuple[str, str]:
    base_hours = [2, 5, 8, 11, 14, 17, 20, 23]
    valid = [t for t in base_hours if t <= dt.hour]
    if not valid:
        prev = dt - timedelta(days=1)
        return prev.strftime('%Y%m%d'), '2300'
    return dt.strftime('%Y%m%d'), f'{max(valid):02d}00'

def get_weather(dt: datetime) -> dict:
    fallback = {'temp_avg': 15.0, 'precip_mm': 0.0, 'is_rainy': 0, 'is_cold': 0, 'is_hot': 0}
    date_str = dt.strftime('%Y%m%d')
    try:
        base_date, base_time = _kma_base_time(dt)
        r = requests.get(KMA_URL, params={
            'serviceKey': API_KEY,
            'pageNo': 1, 'numOfRows': 1000,
            'dataType': 'JSON',
            'base_date': base_date, 'base_time': base_time,
            'nx': KMA_NX, 'ny': KMA_NY,
        }, timeout=8)
        items = r.json()['response']['body']['items']['item']
        tmps, pcps = [], []
        for item in items:
            if item['fcstDate'] != date_str:
                continue
            cat, val = item['category'], item['fcstValue']
            if cat == 'TMP':
                try: tmps.append(float(val))
                except: pass
            elif cat == 'PCP':
                if val == '강수없음':
                    pcps.append(0.0)
                else:
                    try: pcps.append(float(str(val).replace('mm', '').strip()))
                    except: pass
        if not tmps:
            raise ValueError('no TMP data')
        t_avg = sum(tmps) / len(tmps)
        precip = sum(pcps)
        return {
            'temp_avg':  round(t_avg, 1),
            'precip_mm': round(precip, 1),
            'is_rainy':  int(precip > 0.5),
            'is_cold':   int(t_avg < 5),
            'is_hot':    int(t_avg > 28),
        }
    except Exception:
        try:
            r2 = requests.get('https://api.open-meteo.com/v1/forecast', params={
                'latitude': 37.27, 'longitude': 126.99,
                'daily': 'temperature_2m_max,temperature_2m_min,precipitation_sum',
                'timezone': 'Asia/Seoul',
                'start_date': dt.strftime('%Y-%m-%d'), 'end_date': dt.strftime('%Y-%m-%d'),
            }, timeout=8)
            d = r2.json()['daily']
            t_avg = ((d['temperature_2m_max'][0] or 15) + (d['temperature_2m_min'][0] or 10)) / 2
            precip = d['precipitation_sum'][0] or 0
            return {
                'temp_avg':  round(t_avg, 1),
                'precip_mm': round(precip, 1),
                'is_rainy':  int(precip > 0.5),
                'is_cold':   int(t_avg < 5),
                'is_hot':    int(t_avg > 28),
            }
        except Exception:
            return fallback

# ── 전날 탑승 인원 (lag1) ────────────────────────────────────────────────
def get_lag1(stop: str, hour: int, dt: datetime) -> float:
    if history is None:
        return 0.0
    yesterday = (dt - timedelta(days=1)).strftime('%Y_%m_%d')
    rows = history[
        (history['stop'] == stop) &
        (history['hour'] == hour) &
        (history['date'] == yesterday)
    ]
    if len(rows) > 0:
        return float(rows['boardings'].values[0])
    # 없으면 같은 요일 평균
    same_wd = history[
        (history['stop'] == stop) &
        (history['hour'] == hour) &
        (history['weekday'] == dt.weekday())
    ]
    return float(same_wd['boardings'].mean()) if len(same_wd) > 0 else 0.0

# ── GBIS 버스 도착정보 ────────────────────────────────────────────────────
def fetch_arrival(station_id: str) -> dict | None:
    try:
        r = requests.get(GBIS_URL, params={'serviceKey': API_KEY, 'stationId': station_id}, timeout=8)
        items = r.json()['response']['msgBody']['busArrivalList']
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if item.get('routeId') == ROUTE_ID and item.get('vehId1'):
                low  = int(item.get('lowPlate1', 0) or 0)
                rem  = item.get('remainSeatCnt1', -1)
                rem  = int(rem) if str(rem).lstrip('-').isdigit() else -1
                cap  = CAPACITY.get(low, 45)
                pred = item.get('predictTime1', '')
                return {
                    'plateNo':    str(item.get('plateNo1', '')).strip(),
                    'busType':    low,
                    'capacity':   cap,
                    'remainSeat': rem if rem >= 0 else None,
                    'passengers': cap - rem if rem >= 0 else None,
                    'predictMin': int(pred) if str(pred).isdigit() else None,
                }
    except Exception:
        pass
    return None

# ── 예측 함수 ─────────────────────────────────────────────────────────────
def predict_stop(stop: str, hour: int, dt: datetime, arrival: dict | None) -> dict:
    model = models.get(stop)
    if model is None:
        return {'stop': stop, 'error': '모델 없음'}

    cal     = get_calendar_features(dt)
    weather = get_weather(dt)
    lag1    = get_lag1(stop, hour, dt)

    feats = {
        'hour':    hour,
        'weekday': dt.weekday(),
        **cal,
        'boardings_lag1': lag1,
        **weather,
    }
    X    = pd.DataFrame([{k: feats.get(k, 0) for k in FEATURES}])
    pred = float(model.predict(X)[0])

    # 정류장별 수요 과소추정 보정 (Censored Data 보정)
    DEMAND_CORRECTION = {
        ('수원대입구', 15): 2.0,
        ('수원대입구', 16): 2.0,
        ('수원대입구', 17): 2.0,
    }
    pred *= DEMAND_CORRECTION.get((stop, hour), 1.0)

    cap    = arrival['capacity'] if arrival else None
    remain = arrival['remainSeat'] if arrival else None
    pred   = max(0, pred)

    # 잔여석 실시간 데이터가 있을 때: 탑승 가능 / 다음 버스 인원 계산
    if remain is not None:
        can_board = min(round(pred), remain)   # 이번 버스에 탈 수 있는 인원
        overflow  = max(0, round(pred) - remain)  # 다음 버스로 넘어가는 인원
    else:
        can_board = None
        overflow  = None

    # 혼잡도 (잔여석 기준 우선, 없으면 예측값 기준)
    threshold = (cap or 45) * 0.9
    base      = remain if remain is not None else pred
    if base >= threshold or (overflow or 0) > 0:
        status = '혼잡'
    elif base >= threshold * 0.6:
        status = '보통'
    else:
        status = '여유'

    return {
        'stop':      stop,
        'predicted': round(pred, 1),    # ML 예측 수요 (포화 보정 전)
        'can_board': can_board,          # 이번 버스 탑승 가능 인원 (실시간)
        'overflow':  overflow,           # 다음 버스로 넘어가는 인원 (실시간)
        'status':    status,
        'capacity':  cap,
        'remainSeat': remain,
        'weather':   weather,
    }

# ── 엔드포인트 ────────────────────────────────────────────────────────────
@app.get('/health')
def health():
    return {'status': 'ok', 'models': list(models.keys()), 'time': datetime.now().isoformat()}


@app.get('/arrival')
def arrival():
    result = {}
    for stop in ALL_STOPS:
        sid  = STATION_IDS.get(stop)
        info = fetch_arrival(sid) if sid else None
        result[stop] = info
    return result


@app.get('/predict')
def predict(
    hour: int  = Query(default=None, description='시간대 (7~18)'),
    date: str  = Query(default=None, description='날짜 YYYY-MM-DD'),
):
    now  = datetime.now()
    dt   = datetime.strptime(date, '%Y-%m-%d') if date else now
    hour = hour if hour is not None else now.hour

    # 실시간 도착정보 병렬 조회
    arrivals = {}
    for stop in ALL_STOPS:
        sid = STATION_IDS.get(stop)
        arrivals[stop] = fetch_arrival(sid) if sid else None

    direction = 'arrive' if hour <= 10 else 'depart'
    stops     = [ARRIVE_STOP] if direction == 'arrive' else DEPART_STOPS

    results = [predict_stop(s, hour, dt, arrivals.get(s)) for s in stops]

    return {
        'date':      dt.strftime('%Y-%m-%d'),
        'hour':      hour,
        'direction': direction,
        'stops':     results,
        'arrivals':  arrivals,
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run('server:app', host='0.0.0.0', port=8000, reload=True)