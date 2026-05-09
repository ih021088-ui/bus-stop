from fastapi import FastAPI, HTTPException, Query
import pickle, os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from preprocess import (
    build_week_map, build_exam_sets,
    HOLIDAYS, STOP_SEQ, DEPART_HOURS, ARRIVE_HOURS,
)
from weather_kma import fetch_weather
from bus_arrival import get_arrival, get_all_arrivals

app = FastAPI(title="7790 버스 대기 인원 예측 API")

# ── 상수 ──────────────────────────────────────────────────────────
MODEL_DIR  = './models'
CAPACITY   = 70
SAT_THRESH = CAPACITY * 0.9   # 63

DEPART_STOPS = ['효행초등학교정문', '아이파크정문', '신명아파트', '수원대입구']
ARRIVE_STOP  = '사당역9번출구앞'

FEATURES = [
    'hour', 'weekday', 'week_num', 'sem_num',
    'is_exam', 'is_exam_mid', 'is_exam_fin', 'is_pre_exam', 'is_holiday',
    'boardings_lag1',
    'temp_avg', 'precip_mm', 'is_rainy', 'is_cold', 'is_hot',
]

# ── 시작 시 로드 ──────────────────────────────────────────────────
def _load_models():
    result = {}
    for stop in STOP_SEQ.values():
        path = os.path.join(MODEL_DIR, f'model_{stop}.pkl')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                result[stop] = pickle.load(f)
    return result

def _load_overflow_map():
    path = os.path.join(MODEL_DIR, 'overflow_map.pkl')
    if not os.path.exists(path):
        return {}
    with open(path, 'rb') as f:
        return pickle.load(f)

models       = _load_models()
overflow_map = _load_overflow_map()
week_map, semester_map = build_week_map()
midterm_set, final_set = build_exam_sets()

_preprocessed: Optional[pd.DataFrame] = None


# ── 날짜 피처 계산 ────────────────────────────────────────────────
def get_date_features(date_str: str) -> dict:
    key      = date_str.replace('-', '_')
    dt       = datetime.strptime(date_str, '%Y-%m-%d')
    semester = semester_map.get(key, 'unknown')
    week_num = week_map.get(key, -1)

    is_exam_mid = int(key in midterm_set)
    is_exam_fin = int(key in final_set)
    is_exam     = int(is_exam_mid or is_exam_fin)

    pre_exam_weeks = {('2025_1', 6), ('2026_1', 6), ('2025_1', 13)}
    is_pre_exam    = int((semester, week_num) in pre_exam_weeks)
    sem_num        = int(semester.split('_')[1]) if semester != 'unknown' else -1

    return {
        'weekday':      dt.weekday(),
        'week_num':     week_num,
        'sem_num':      sem_num,
        'is_exam':      is_exam,
        'is_exam_mid':  is_exam_mid,
        'is_exam_fin':  is_exam_fin,
        'is_pre_exam':  is_pre_exam,
        'is_holiday':   int(key in HOLIDAYS),
    }


# ── lag1 조회 ─────────────────────────────────────────────────────
def get_lag1(stop: str, direction: str, hour: int, date_str: str) -> float:
    global _preprocessed
    if _preprocessed is None:
        if os.path.exists('./preprocessed.csv'):
            _preprocessed = pd.read_csv('./preprocessed.csv')
        else:
            return float('nan')

    dt = datetime.strptime(date_str, '%Y-%m-%d')
    for i in range(1, 8):
        prev = (dt - timedelta(days=i)).strftime('%Y_%m_%d')
        row  = _preprocessed[
            (_preprocessed['stop']      == stop) &
            (_preprocessed['direction'] == direction) &
            (_preprocessed['hour']      == hour) &
            (_preprocessed['date']      == prev)
        ]
        if not row.empty:
            return float(row.iloc[0]['boardings'])

    subset = _preprocessed[
        (_preprocessed['stop']      == stop) &
        (_preprocessed['direction'] == direction) &
        (_preprocessed['hour']      == hour)
    ]
    return float(subset['boardings'].mean()) if not subset.empty else 0.0


# ── 단건 예측 ─────────────────────────────────────────────────────
def predict_one(stop: str, date_str: str, hour: int,
                weather: Optional[dict] = None) -> dict:
    direction = 'arrive' if stop == ARRIVE_STOP else 'depart'

    if stop not in models:
        raise HTTPException(status_code=404, detail=f"모델 없음: {stop}")

    if weather is None:
        weather = fetch_weather(date_str)

    date_feats = get_date_features(date_str)
    lag1       = get_lag1(stop, direction, hour, date_str)

    X = pd.DataFrame([{
        'hour': hour,
        **date_feats,
        'boardings_lag1': lag1,
        **weather,
    }])[FEATURES]

    pred  = max(0.0, round(float(models[stop].predict(X)[0]), 1))
    ratio = overflow_map.get(stop, 0.0)

    if pred >= SAT_THRESH and ratio > 0:
        next_hour  = hour + 1
        valid_next = ARRIVE_HOURS if direction == 'arrive' else DEPART_HOURS
        if next_hour in valid_next:
            X_next         = X.copy()
            X_next['hour'] = next_hour
            pred_next      = max(0.0, float(models[stop].predict(X_next)[0]))
        else:
            pred_next = pred
        high   = round(pred + pred_next * ratio, 1)
        status = '혼잡'
    elif pred >= SAT_THRESH * 0.7:
        high   = pred
        status = '보통'
    else:
        high   = pred
        status = '여유'

    return {
        'stop':      stop,
        'date':      date_str,
        'hour':      hour,
        'direction': direction,
        'predicted': pred,
        'low':       pred,
        'high':      high,
        'status':    status,
        'weather':   weather,
    }


# ── 엔드포인트 ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": list(models.keys())}


@app.get("/stops")
def list_stops():
    return {"arrive": [ARRIVE_STOP], "depart": DEPART_STOPS}


@app.get("/predict")
def predict(
    stop: str = Query(..., description="정류장명"),
    date: str = Query(..., description="날짜 (YYYY-MM-DD)"),
    hour: int = Query(..., ge=7, le=18, description="시간 (7~10 등교 / 13~18 하교)"),
):
    return predict_one(stop, date, hour)


@app.get("/predict/all")
def predict_all(
    date: str = Query(..., description="날짜 (YYYY-MM-DD)"),
    hour: Optional[int] = Query(None, ge=7, le=18, description="특정 시간만 조회 (생략 시 전체)"),
):
    weather = fetch_weather(date)
    results = []

    arrive_hours = ARRIVE_HOURS if hour is None else ([hour] if hour in ARRIVE_HOURS else [])
    for h in arrive_hours:
        results.append(predict_one(ARRIVE_STOP, date, h, weather))

    depart_hours = DEPART_HOURS if hour is None else ([hour] if hour in DEPART_HOURS else [])
    for stop in DEPART_STOPS:
        for h in depart_hours:
            results.append(predict_one(stop, date, h, weather))

    return {"date": date, "weather": weather, "predictions": results}


@app.get("/bus/arrival")
def bus_arrival(
    stop: str = Query(..., description="정류장명"),
):
    return get_arrival(stop)


@app.get("/bus/arrival/all")
def bus_arrival_all():
    return {"arrivals": get_all_arrivals()}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
