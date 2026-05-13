"""
7790 버스 혼잡도 예측 API
GET /predict?hour=15
GET /predict?hour=15&date=2026-05-13
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import pickle
from datetime import date, timedelta
from pathlib import Path

app = FastAPI(title="7790 버스 혼잡도 예측 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── 정류장 정의 ───────────────────────────────────────────────────
DEPART_STOPS = ['효행초등학교정문', '아이파크정문', '신명아파트', '수원대입구']
ARRIVE_STOP  = '사당역9번출구앞'
CAPACITY     = 45   # 혼잡도 표시 기준 (1층 버스)

# ── 학사 일정 (하드코딩) ──────────────────────────────────────────
# 2026 1학기: 3/4(수) 개강, 6/26 종강
SEM_2026_1_START  = date(2026, 3, 2)   # 주차 계산 기준 (개강 직전 일요일)
EXAM_MID_2026_1   = (date(2026, 4, 16), date(2026, 4, 30))
EXAM_FIN_2026_1   = (date(2026, 6,  4), date(2026, 6, 17))
PRE_MID_2026_1    = (date(2026, 4,  6), date(2026, 4, 10))
PRE_FIN_2026_1    = (date(2026, 5, 28), date(2026, 6,  3))
SEM_2026_1_END    = date(2026, 6, 26)

HOLIDAYS_2026 = {
    date(2026, 5,  5),   # 어린이날
    date(2026, 6,  6),   # 현충일 (토요일이지만 혹시 대체)
}

# ── 모델 로드 ─────────────────────────────────────────────────────
MODEL_DIR = Path("./models")

def load_models():
    models = {}
    for stop in DEPART_STOPS + [ARRIVE_STOP]:
        path = MODEL_DIR / f"model_{stop}.pkl"
        with open(path, "rb") as f:
            models[stop] = pickle.load(f)
    with open(MODEL_DIR / "overflow_map.pkl", "rb") as f:
        overflow_map = pickle.load(f)
    return models, overflow_map

models, overflow_map = load_models()

# ── 데이터 로드 ───────────────────────────────────────────────────
df_hist    = pd.read_csv("./preprocessed.csv")
df_weather = pd.read_csv("./weather.csv")

# ── 학사 피처 계산 ────────────────────────────────────────────────
def get_academic_features(target: date) -> dict:
    in_sem = date(2026, 3, 4) <= target <= SEM_2026_1_END
    if not in_sem:
        return {
            "week_num": 1, "sem_num": 1,
            "is_exam": 0, "is_exam_mid": 0, "is_exam_fin": 0,
            "is_pre_exam": 0,
        }

    week_num = (target - SEM_2026_1_START).days // 7 + 1

    in_mid = EXAM_MID_2026_1[0] <= target <= EXAM_MID_2026_1[1]
    in_fin = EXAM_FIN_2026_1[0] <= target <= EXAM_FIN_2026_1[1]
    in_pre_mid = PRE_MID_2026_1[0] <= target <= PRE_MID_2026_1[1]
    in_pre_fin = PRE_FIN_2026_1[0] <= target <= PRE_FIN_2026_1[1]

    return {
        "week_num":    min(week_num, 17),
        "sem_num":     1,
        "is_exam":     int(in_mid or in_fin),
        "is_exam_mid": int(in_mid),
        "is_exam_fin": int(in_fin),
        "is_pre_exam": int(in_pre_mid or in_pre_fin),
    }

# ── 날씨 피처 ────────────────────────────────────────────────────
def get_weather_features(target: date) -> dict:
    date_key = target.strftime("%Y_%m_%d")
    row = df_weather[df_weather["date"] == date_key]
    if row.empty:
        # 없으면 최근 7일 평균
        row = df_weather.tail(7)
        return {
            "temp_avg":  round(row["temp_avg"].mean(), 1),
            "precip_mm": round(row["precip_mm"].mean(), 1),
            "is_rainy":  int(row["precip_mm"].mean() > 0.5),
            "is_cold":   int(row["temp_avg"].mean() < 5),
            "is_hot":    int(row["temp_avg"].mean() > 28),
        }
    r = row.iloc[0]
    return {
        "temp_avg":  float(r["temp_avg"]),
        "precip_mm": float(r["precip_mm"]),
        "is_rainy":  int(r["is_rainy"]),
        "is_cold":   int(r["is_cold"]),
        "is_hot":    int(r["is_hot"]),
    }

# ── lag1 (전날 같은 시간 탑승 수) ────────────────────────────────
def get_lag1(stop: str, direction: str, hour: int, target: date) -> float:
    yesterday = (target - timedelta(days=1)).strftime("%Y_%m_%d")
    row = df_hist[
        (df_hist["stop"] == stop) &
        (df_hist["direction"] == direction) &
        (df_hist["hour"] == hour) &
        (df_hist["date"] == yesterday)
    ]
    if not row.empty:
        return float(row.iloc[0]["boardings"])
    # 없으면 같은 요일 + 같은 시간 최근 4주 평균
    recent = df_hist[
        (df_hist["stop"] == stop) &
        (df_hist["direction"] == direction) &
        (df_hist["hour"] == hour) &
        (df_hist["weekday"] == target.weekday())
    ].tail(4)
    if not recent.empty:
        return round(float(recent["boardings"].mean()), 1)
    # 최후 fallback: 전체 해당 stop+hour 평균
    fallback = df_hist[
        (df_hist["stop"] == stop) &
        (df_hist["direction"] == direction) &
        (df_hist["hour"] == hour)
    ]
    return round(float(fallback["boardings"].mean()), 1) if not fallback.empty else 10.0

# ── 혼잡도 판정 ──────────────────────────────────────────────────
def get_congestion(boardings: float) -> str:
    if boardings >= 36:
        return "혼잡"
    if boardings >= 22:
        return "보통"
    return "여유"

# ── 예측 실행 ─────────────────────────────────────────────────────
def run_predict(stop: str, direction: str, hour: int, target: date) -> dict:
    acad    = get_academic_features(target)
    weather = get_weather_features(target)
    lag1    = get_lag1(stop, direction, hour, target)

    features = {
        "hour":          hour,
        "weekday":       target.weekday(),
        "boardings_lag1": lag1,
        "is_holiday":    int(target in HOLIDAYS_2026),
        **acad,
        **weather,
    }

    FEATURE_ORDER = [
        "hour", "weekday", "week_num", "sem_num",
        "is_exam", "is_exam_mid", "is_exam_fin", "is_pre_exam",
        "is_holiday", "boardings_lag1",
        "temp_avg", "precip_mm", "is_rainy", "is_cold", "is_hot",
    ]
    X = pd.DataFrame([[features[f] for f in FEATURE_ORDER]], columns=FEATURE_ORDER)

    pred = float(models[stop].predict(X)[0])
    pred = max(0, round(pred, 1))

    overflow = overflow_map.get(stop, 0)
    if pred >= CAPACITY * 0.9 and overflow > 0:
        high = round(pred + pred * overflow, 1)
        status = "혼잡"
    else:
        high = pred
        status = get_congestion(pred)

    return {
        "stop":       stop,
        "boardings":  pred,
        "high":       high,
        "congestion": status,
        "lag1_used":  lag1,
    }

# ── API 엔드포인트 ────────────────────────────────────────────────
@app.get("/predict")
def predict(
    hour: int = Query(..., description="시간대 (7~10: 등교, 13~18: 하교)"),
    date_str: str = Query(None, alias="date", description="날짜 (YYYY-MM-DD), 생략 시 오늘"),
):
    # 날짜 파싱
    if date_str:
        try:
            target = date.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(400, "날짜 형식 오류. YYYY-MM-DD로 입력하세요.")
    else:
        target = date.today()

    # 방향 결정
    if 7 <= hour <= 10:
        direction = "arrive"
        stops = [ARRIVE_STOP]
    elif 13 <= hour <= 18:
        direction = "depart"
        stops = DEPART_STOPS
    else:
        raise HTTPException(400, f"지원하지 않는 시간대입니다. (등교: 7~10시, 하교: 13~18시)")

    results = [run_predict(stop, direction, hour, target) for stop in stops]

    return {
        "date":      target.isoformat(),
        "hour":      hour,
        "direction": direction,
        "weekday":   ["월","화","수","목","금","토","일"][target.weekday()],
        "weather":   get_weather_features(target),
        "stops":     results,
    }

@app.get("/health")
def health():
    return {"status": "ok", "models_loaded": list(models.keys())}
