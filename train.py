import pandas as pd
import numpy as np
import pickle
import os
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

DATA_PATH   = './preprocessed.csv'
MODEL_DIR   = './models'
os.makedirs(MODEL_DIR, exist_ok=True)

CAPACITY    = 70
SAT_THRESH  = CAPACITY * 0.9   # 63 이상이면 포화 근접

FEATURES = [
    'hour',
    'weekday',
    'week_num',
    'sem_num',
    'is_exam',
    'is_exam_mid',
    'is_exam_fin',
    'is_pre_exam',
    'is_holiday',
    'boardings_lag1',
    'boardings_lag7',
    'boardings_roll3',
    # 날씨
    'temp_avg',
    'precip_mm',
    'is_rainy',
    'is_cold',
    'is_hot',
]

# ── 데이터 로드 ───────────────────────────────────────────────────
df = pd.read_csv(DATA_PATH)
df['year'] = df['date'].str[:4].astype(int)

# lag 결측치는 같은 stop+hour 평균으로 채움
for col in ['boardings_lag1', 'boardings_lag7', 'boardings_roll3']:
    df[col] = df.groupby(['stop','direction','hour'])[col]\
                .transform(lambda x: x.fillna(x.mean()))

# ── Train / Test 분리 ─────────────────────────────────────────────
# 시계열 분리: 2025 전체 + 2026 1~6주차 학습, 2026 7~8주차(시험기간 포함) 평가
# 이유: 연도 간 패턴 차이 해소 + 실제 배포 상황(최근 데이터로 학습)과 동일
TRAIN_CUTOFF = '2026_04_10'   # 2026 6주차 마지막 날
train_df = df[df['date'] <= TRAIN_CUTOFF].copy()
test_df  = df[df['date'] >  TRAIN_CUTOFF].copy()

print(f'Train: {train_df["date"].nunique()}일  ({len(train_df)}샘플)')
print(f'Test:  {test_df["date"].nunique()}일   ({len(test_df)}샘플)')
print(f'  └ 시험기간: {test_df[test_df["is_exam"]==1]["date"].nunique()}일 '
      f'/ 비시험: {test_df[test_df["is_exam"]==0]["date"].nunique()}일')
print()

# ── 정류장별 overflow 비율 계산 (train 데이터 기준) ───────────────
def calc_overflow_ratio(train, stop):
    dep = train[(train['stop'] == stop) & (train['direction'] == 'depart')].copy()
    dep = dep.sort_values(['date', 'hour']).reset_index(drop=True)
    dep['next_hour_board'] = dep.groupby('date')['boardings'].shift(-1)

    sat = dep[dep['boardings'] >= SAT_THRESH].copy()
    not_sat = dep[dep['boardings'] < SAT_THRESH].copy()

    normal_avg = not_sat.groupby('hour')['boardings'].mean()

    def overflow(row):
        next_h = row['hour'] + 1
        if pd.isna(row['next_hour_board']) or next_h not in normal_avg:
            return np.nan
        return max(0, row['next_hour_board'] - normal_avg[next_h])

    sat['overflow'] = sat.apply(overflow, axis=1)
    sat['ratio']    = sat['overflow'] / sat['boardings'].clip(lower=1)

    median_ratio = sat['ratio'].dropna().median()
    return round(median_ratio, 3) if not pd.isna(median_ratio) else 0.2

# ── 모델 학습 함수 ────────────────────────────────────────────────
def train_model(train, test, stop, direction):
    tr = train[(train['stop'] == stop) & (train['direction'] == direction)].dropna(subset=FEATURES)
    te = test[(test['stop'] == stop)  & (test['direction'] == direction)].dropna(subset=FEATURES)

    if len(tr) < 10:
        print(f'  [{stop}] 학습 데이터 부족 ({len(tr)}개) - 스킵')
        return None, None, None

    X_tr, y_tr = tr[FEATURES], tr['boardings']
    X_te, y_te = te[FEATURES], te['boardings']

    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=8,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_tr, y_tr)

    # 평가
    y_pred_tr = model.predict(X_tr)
    y_pred_te = model.predict(X_te) if len(te) > 0 else []

    metrics = {}
    if len(te) > 0:
        metrics = {
            'train_mae': mean_absolute_error(y_tr, y_pred_tr),
            'test_mae':  mean_absolute_error(y_te, y_pred_te),
            'test_rmse': np.sqrt(mean_squared_error(y_te, y_pred_te)),
            'test_r2':   r2_score(y_te, y_pred_te),
        }

    # 피처 중요도 상위 5개
    importances = sorted(zip(FEATURES, model.feature_importances_),
                         key=lambda x: -x[1])[:5]

    return model, metrics, importances

# ── 전체 학습 실행 ────────────────────────────────────────────────
DEPART_STOPS = ['효행초등학교정문', '아이파크정문', '신명아파트', '수원대입구']
ARRIVE_STOP  = '사당역9번출구앞'

results      = {}
overflow_map = {}

print('='*55)
print('하교 방향 (13~18시)')
print('='*55)

for stop in DEPART_STOPS:
    model, metrics, importances = train_model(train_df, test_df, stop, 'depart')
    overflow_ratio = calc_overflow_ratio(train_df, stop)
    overflow_map[stop] = overflow_ratio

    if model:
        results[stop] = metrics
        fname = os.path.join(MODEL_DIR, f'model_{stop}.pkl')
        with open(fname, 'wb') as f:
            pickle.dump(model, f)

        print(f'\n[{stop}]  overflow_ratio={overflow_ratio}')
        print(f'  Train MAE: {metrics["train_mae"]:.2f}명')
        print(f'  Test  MAE: {metrics["test_mae"]:.2f}명  '
              f'RMSE: {metrics["test_rmse"]:.2f}  R²: {metrics["test_r2"]:.3f}')
        print(f'  주요 피처: {[f"{k}({v:.3f})" for k,v in importances[:3]]}')

print()
print('='*55)
print('등교 방향 (07~10시)')
print('='*55)

model, metrics, importances = train_model(train_df, test_df, ARRIVE_STOP, 'arrive')
overflow_map[ARRIVE_STOP] = 0.0   # 첫 정류장이라 overflow 개념 없음

if model:
    results[ARRIVE_STOP] = metrics
    fname = os.path.join(MODEL_DIR, f'model_{ARRIVE_STOP}.pkl')
    with open(fname, 'wb') as f:
        pickle.dump(model, f)

    print(f'\n[{ARRIVE_STOP}]')
    print(f'  Train MAE: {metrics["train_mae"]:.2f}명')
    print(f'  Test  MAE: {metrics["test_mae"]:.2f}명  '
          f'RMSE: {metrics["test_rmse"]:.2f}  R²: {metrics["test_r2"]:.3f}')
    print(f'  주요 피처: {[f"{k}({v:.3f})" for k,v in importances[:3]]}')

# overflow_map 저장
with open(os.path.join(MODEL_DIR, 'overflow_map.pkl'), 'wb') as f:
    pickle.dump(overflow_map, f)

print()
print('='*55)
print(f'모델 저장 완료 → {MODEL_DIR}/')
print(f'overflow_map: {overflow_map}')
