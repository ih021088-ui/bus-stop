# 7790 버스 대기 인원 예측 서비스

수원대학교 ↔ 사당역을 오가는 **7790 버스** 정류장별 대기 인원을 예측하고, 웹페이지에 실시간으로 표시하는 프로젝트입니다.

> "지금 수원대입구 정류장에 몇 명이나 줄 서 있을까?" — 예측 모델로 답합니다.

**팀**: 조장, 승민, 정인, 승주, 성빈

---

## 프로젝트 배경

7790 버스는 수원대학교에서 사당역으로 가는 **유일한 직행 버스**입니다. 등하교 시간대에 대기줄이 극심하게 길어져 한 대를 놓치면 다음 버스까지 오래 기다려야 하는 상황이 반복됩니다. 이 프로젝트는 과거 탑승 데이터와 날씨, 학사 일정을 기반으로 **대기 인원을 예측**하여 학생들이 미리 출발 시간을 조정할 수 있도록 도움을 줍니다.

---

## 예측 대상 정류장

| 방향 | 정류장 | 시간대 |
|------|--------|--------|
| 하교 (수원대 → 사당) | 효행초등학교정문, 아이파크정문, 신명아파트, 수원대입구 | 13~18시 |
| 등교 (사당 → 수원대) | 사당역 9번 출구 앞 | 07~10시 |

---

## 전체 파이프라인

```
[ 학습 파이프라인 ]

해커톤데이터2/*.xlsx ──→ preprocess.py ──→ preprocessed.csv ──→ train.py ──→ models/*.pkl


[ 서비스 파이프라인 ]

기상청 단기예보 API (→ Open-Meteo fallback) ──┐
경기도 버스도착정보 API ──────────────────────┼──→ server.py (FastAPI) ──→ frontend/index.html
학사 일정 (하드코딩) ─────────────────────────┤         ↑
preprocessed.csv (lag 피처 조회) ─────────────┘   models/*.pkl
```

---

## 프로젝트 구조

```
bus-stop/
├── 해커톤데이터2/              # 원본 탑승 데이터 (xlsx 130개, 2025-03 ~ 2026-04)
├── models/                    # 학습된 모델
│   ├── model_효행초등학교정문.pkl
│   ├── model_아이파크정문.pkl
│   ├── model_신명아파트.pkl
│   ├── model_수원대입구.pkl
│   ├── model_사당역9번출구앞.pkl
│   └── overflow_map.pkl       # 정류장별 포화 초과 비율 (Censored Data 보정용)
├── frontend/
│   └── index.html             # Leaflet.js 지도 + 사이드바 UI
├── preprocess.py              # 탑승 인원 역산 + 피처 생성
├── train.py                   # RandomForest 모델 학습 및 평가
├── server.py                  # FastAPI 추론 서버
├── preprocessed.csv           # 전처리 완료 데이터 (3,552행)
├── .env                       # API 키 (로컬 전용, Git 제외)
├── .env.example               # 환경변수 양식
└── requirements.txt           # 의존성 패키지
```

---

## 모델 성능

| 정류장 | Test MAE | Test RMSE | R² |
|--------|----------|-----------|-----|
| 사당역9번출구앞 | 9.34명 | 10.99 | **0.526** |
| 아이파크정문 | 6.12명 | 7.59 | 0.381 |
| 수원대입구 | 6.13명 | 7.71 | 0.190 |
| 효행초등학교정문 | 6.02명 | 8.20 | 0.105 |
| 신명아파트 | 2.73명 | 3.53 | -0.063 |

- 알고리즘: `RandomForestRegressor (n_estimators=200, max_depth=8, min_samples_leaf=3)`
- 학습 기간: 2025 전체 + 2026 1~6주차 (117일)
- 테스트 기간: 2026 7~8주차 (10일, 중간고사 기간 포함)
- 주요 피처: `boardings_roll3`(최근 3일 평균), `boardings_lag1`(전날), `boardings_lag7`(1주 전)

> R²가 전반적으로 낮은 이유: 테스트 10일 중 7일이 중간고사(모델이 처음 보는 패턴), 정류장별 탑승 수 변동성이 매우 큼(CV ≈ 1.0), 총 데이터 130일의 구조적 한계.

---

## 학습 피처 (17개)

| 카테고리 | 피처 |
|---|---|
| 시간 | `hour`, `weekday` |
| 학사일정 | `week_num`, `sem_num`, `is_exam`, `is_exam_mid`, `is_exam_fin`, `is_pre_exam`, `is_holiday` |
| 탑승 이력 | `boardings_lag1` (직전 평일), `boardings_lag7` (1주 전 같은 요일), `boardings_roll3` (최근 3일 평균) |
| 날씨 | `temp_avg`, `precip_mm`, `is_rainy`, `is_cold`, `is_hot` |

---

## 포화 상태 처리

버스가 꽉 찬 경우 못 탄 사람은 데이터에 기록되지 않습니다(Censored Data). `train.py`의 `calc_overflow_ratio()`로 정류장별 초과 수요 비율을 계산하고 `overflow_map.pkl`에 저장합니다. 서버는 이를 로드하여 예측값을 상향 보정합니다.

```
보정 배율 = max(1 + overflow_ratio, 수동_보정값)
# 수원대입구 15~17시: 수동 2.0x (overflow 계산 특성상 수동 보정 유지)
```

실시간 버스 잔여석(GBIS API)이 있을 때는 추가로:
- `can_board = min(예측 대기, 잔여석)` → 이번 버스에 탈 수 있는 인원
- `overflow = max(0, 예측 대기 - 잔여석)` → 다음 버스로 넘어가는 인원

---

## 환경 설정

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. API 키 설정

```bash
cp .env.example .env
# .env 파일에 공공데이터포털 API 키 입력
```

### 3. 전처리 및 학습

```bash
python preprocess.py   # preprocessed.csv 생성
python train.py        # models/*.pkl 생성
```

### 4. 서버 실행

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
# 브라우저에서 http://localhost:8000 접속
```

외부 접속이 필요한 경우 (Serveo SSH 터널):
```bash
ssh -R 80:localhost:8000 serveo.net
```

---

## API 엔드포인트

| 엔드포인트 | 설명 |
|---|---|
| `GET /` | 프론트엔드 (index.html) |
| `GET /predict?hour=15&date=2026-05-18` | 시간대별 혼잡도 예측 + 실시간 도착정보 |
| `GET /health` | 서버 상태 및 로드된 모델 확인 |

---

## 사용 API

| API | 용도 | 비고 |
|-----|------|------|
| 기상청 단기예보 | 실시간 날씨 (추론 입력값) | 공공데이터포털, 10분 캐시 |
| Open-Meteo | 날씨 fallback | 무료, 키 불필요 |
| 경기도 버스도착정보 (GBIS) | 수원대 방면 실시간 잔여석 | 공공데이터포털 |

> 사당역9번출구앞은 서울시 정류장(stationId: 119000302)이라 경기도 GBIS API로 조회 불가, 실시간 도착정보 없음.

---

## 주요 한계점

1. **데이터 130일** — 데이터가 더 쌓일수록 모델 정확도 향상
2. **포화 수요 과소추정** — 못 탄 사람은 데이터에 미포함 (overflow_map으로 보정 중)
3. **사당역 실시간 정보 없음** — 서울시 버스 API 별도 연동 필요
4. **주말·공휴일 예측 없음** — 7790 버스 운행 특성상 평일 전용 서비스
5. **2학기 데이터 14일** — 2학기 패턴 예측 신뢰도 낮음
