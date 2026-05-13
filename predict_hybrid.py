"""
하이브리드 예측기
- 기본: RandomForest (lag1, 날씨, 시험기간 등)
- 실시간 보정: seat_log.csv 기반 전 정류장 만차 여부로 과거 유사일 평균 합산

하교 정류장 순서: 효행초등학교정문 → 아이파크정문 → 신명아파트 → 수원대입구
"""

import pickle
import os
import pandas as pd
import numpy as np
from datetime import datetime, date

MODEL_DIR       = './models'
PREPROCESSED    = './preprocessed.csv'
SEAT_LOG        = './seat_log.csv'

DEPART_STOPS = ['효행초등학교정문', '아이파크정문', '신명아파트', '수원대입구']
ARRIVE_STOP  = '사당역9번출구앞'
CAPACITY     = {0: 45, 1: 45, 2: 70}  # busType → 정원

# 하교 방향 정류장 순서 (이전 정류장 매핑)
PREV_STOP = {
    '아이파크정문':     '효행초등학교정문',
    '신명아파트':       '아이파크정문',
    '수원대입구':       '신명아파트',
}

FEATURES = [
    'hour', 'weekday', 'week_num', 'sem_num',
    'is_exam', 'is_exam_mid', 'is_exam_fin', 'is_pre_exam', 'is_holiday',
    'boardings_lag1',
    'temp_avg', 'precip_mm', 'is_rainy', 'is_cold', 'is_hot',
]


def load_models() -> dict:
    models = {}
    for stop in DEPART_STOPS + [ARRIVE_STOP]:
        path = os.path.join(MODEL_DIR, f'model_{stop}.pkl')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                models[stop] = pickle.load(f)
    return models


def load_history() -> pd.DataFrame:
    df = pd.read_csv(PREPROCESSED)
    df.columns = [c.lstrip('﻿') for c in df.columns]
    return df


def load_seat_log_today() -> pd.DataFrame | None:
    if not os.path.exists(SEAT_LOG):
        return None
    df = pd.read_csv(SEAT_LOG)
    today = date.today().strftime('%Y-%m-%d')
    df = df[df['date'] == today]
    return df if len(df) > 0 else None


def get_rt_signal(seat_today: pd.DataFrame, stop: str, hour: int) -> dict | None:
    """전 정류장의 오늘 실시간 데이터 반환"""
    prev = PREV_STOP.get(stop)
    if prev is None or seat_today is None:
        return None

    rows = seat_today[(seat_today['stop'] == prev) & (seat_today['hour'] == hour)]
    if len(rows) == 0:
        # 같은 시간대 없으면 1시간 이내 데이터 허용
        rows = seat_today[
            (seat_today['stop'] == prev) &
            (seat_today['hour'].between(hour - 1, hour))
        ]
    if len(rows) == 0:
        return None

    latest = rows.iloc[-1]
    return {
        'is_full':  int(latest['isFullFlag']),
        'bus_type': int(latest['busType']),
        'capacity': int(latest['capacity']),
        'est_passengers': int(latest['est_passengers']),
        'est_remain':     int(latest['est_remain']),
    }


def hist_lookup(history: pd.DataFrame, stop: str, hour: int, weekday: int, is_full: int) -> float | None:
    """
    전 정류장 만차 여부(is_full)가 비슷했던 과거 날들의 현재 정류장 탑승 평균
    - is_full=1 (만차): 상위 40% 혼잡일 평균
    - is_full=0 (여유): 하위 60% 평균
    """
    base = history[
        (history['stop'] == stop) &
        (history['hour'] == hour) &
        (history['weekday'] == weekday)
    ]['boardings'].dropna()

    if len(base) < 5:
        # 요일 조건 완화
        base = history[
            (history['stop'] == stop) &
            (history['hour'] == hour)
        ]['boardings'].dropna()

    if len(base) < 3:
        return None

    q60 = base.quantile(0.60)
    if is_full == 1:
        similar = base[base >= q60]
    else:
        similar = base[base < q60]

    return float(similar.mean()) if len(similar) >= 2 else float(base.mean())


def predict(
    stop: str,
    features: dict,
    history: pd.DataFrame,
    models: dict,
    seat_today: pd.DataFrame | None = None,
    weight_rf: float = 0.6,
) -> dict:
    """
    Returns:
        rf_pred       : RandomForest 단독 예측
        hybrid_pred   : 하이브리드 예측 (실시간 보정 포함)
        rt_signal     : 실시간 전 정류장 데이터 (없으면 None)
        capacity      : 접근 버스 정원 (알 수 없으면 None)
        est_remain    : 추정 잔여석 (알 수 없으면 None)
        capped_pred   : 잔여석 상한 적용 최종값
    """
    model = models.get(stop)
    if model is None:
        return {'error': f'모델 없음: {stop}'}

    # 1. RandomForest 예측
    X = pd.DataFrame([{k: features.get(k, 0) for k in FEATURES}])
    rf_pred = float(model.predict(X)[0])

    # 2. 실시간 전 정류장 데이터
    hour    = features.get('hour', datetime.now().hour)
    weekday = features.get('weekday', datetime.now().weekday())
    rt      = get_rt_signal(seat_today, stop, hour)

    # 3. 과거 유사일 평균 (친구 방식)
    hist_pred = None
    if rt is not None:
        hist_pred = hist_lookup(history, stop, hour, weekday, rt['is_full'])

    # 4. 하이브리드 합산
    if hist_pred is not None:
        hybrid = weight_rf * rf_pred + (1 - weight_rf) * hist_pred
    else:
        hybrid = rf_pred

    # 5. 잔여석 상한 적용
    est_remain = rt['est_remain'] if rt else None
    if est_remain is not None:
        capped = min(hybrid, est_remain)
    else:
        capped = hybrid

    return {
        'stop':        stop,
        'rf_pred':     round(rf_pred, 1),
        'hist_pred':   round(hist_pred, 1) if hist_pred else None,
        'hybrid_pred': round(hybrid, 1),
        'capped_pred': round(capped, 1),
        'rt_signal':   rt,
    }


if __name__ == '__main__':
    now     = datetime.now()
    models  = load_models()
    history = load_history()
    seat_today = load_seat_log_today()

    print(f"=== 하이브리드 예측 ({now:%Y-%m-%d %H:%M}) ===")
    print(f"실시간 seat_log: {'있음' if seat_today is not None else '없음 (RF만 사용)'}\n")

    sample_features = {
        'hour':          now.hour,
        'weekday':       now.weekday(),
        'week_num':      1,
        'sem_num':       1,
        'is_exam':       0,
        'is_exam_mid':   0,
        'is_exam_fin':   0,
        'is_pre_exam':   0,
        'is_holiday':    0,
        'boardings_lag1': 20,
        'temp_avg':      18.0,
        'precip_mm':     0.0,
        'is_rainy':      0,
        'is_cold':       0,
        'is_hot':        0,
    }

    for stop in DEPART_STOPS:
        result = predict(stop, sample_features, history, models, seat_today)
        rt = result.get('rt_signal')
        print(f"[{stop}]")
        print(f"  RF 예측:     {result['rf_pred']}명")
        if result['hist_pred']:
            print(f"  과거유사일:  {result['hist_pred']}명  (전 정류장 {'만차' if rt['is_full'] else '여유'})")
        print(f"  하이브리드:  {result['hybrid_pred']}명")
        if result['capped_pred'] != result['hybrid_pred']:
            print(f"  잔여석상한:  {result['capped_pred']}명  (잔여 {rt['est_remain']}석)")
        print()
