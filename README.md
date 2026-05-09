# 7790 버스 대기 인원 예측

수원대학교 7790번 버스 정류장의 대기 인원을 예측하는 머신러닝 모델 + FastAPI 서버

---

## 프로젝트 구조

```
bus-stop/
├── 해커톤데이터2/          # 원본 데이터 (xlsx, 1일 1파일)
├── collect_weather.py      # 날씨 데이터 수집 (Open-Meteo)
├── preprocess.py           # 전처리 + 피처 생성
├── train.py                # 모델 학습
├── server.py               # FastAPI 추론 서버
├── weather_kma.py          # 실시간 날씨 조회
├── bus_arrival.py          # 버스 도착 정보 조회
├── config.py               # API 키 설정
└── requirements.txt
```

---

## 설치

```bash
pip install -r requirements.txt
```

---

## 실행 순서

### 1. 날씨 데이터 수집

```bash
python collect_weather.py
```

- `weather.csv` 생성 (2025-03-01 ~ 2026-04-30)

### 2. 전처리

```bash
python preprocess.py
```

- `preprocessed.csv` 생성 (3,552행)
- 탑승 인원 역산, 피처 생성, 날씨 merge

### 3. 모델 학습

```bash
python train.py
```

- `models/model_*.pkl` 저장 (정류장별 5개)
- `models/overflow_map.pkl` 저장

### 4. 서버 실행

```bash
python server.py
```

- `http://localhost:8000` 에서 서버 시작
- `http://localhost:8000/docs` 에서 Swagger UI 확인

---

## API 엔드포인트

| 메서드 | URL | 설명 |
|--------|-----|------|
| GET | `/health` | 서버 상태 확인 |
| GET | `/stops` | 정류장 목록 |
| GET | `/predict` | 단건 예측 |
| GET | `/predict/all` | 전체 정류장 예측 |
| GET | `/bus/arrival` | 단건 버스 도착 정보 |
| GET | `/bus/arrival/all` | 전체 버스 도착 정보 |

### 예측 요청 예시

```
GET /predict?stop=수원대입구&date=2026-05-12&hour=15
GET /predict/all?date=2026-05-12
GET /predict/all?date=2026-05-12&hour=15
```

### 응답 예시

```json
{
  "stop": "수원대입구",
  "date": "2026-05-12",
  "hour": 15,
  "direction": "depart",
  "predicted": 32.5,
  "low": 32.5,
  "high": 32.5,
  "status": "여유",
  "weather": {
    "temp_avg": 18.6,
    "precip_mm": 0.0,
    "is_rainy": 0,
    "is_cold": 0,
    "is_hot": 0
  }
}
```

---

## 예측 대상

| 방향 | 정류장 | 시간대 |
|------|--------|--------|
| 하교 (수원대 → 사당) | 효행초등학교정문, 아이파크정문, 신명아파트, 수원대입구 | 13~18시 |
| 등교 (사당 → 수원대) | 사당역9번출구앞 | 7~10시 |

---

## 혼잡도 기준

| 상태 | 기준 |
|------|------|
| 여유 | 예측 인원 44명 미만 |
| 보통 | 44명 이상 ~ 63명 미만 |
| 혼잡 | 63명 이상 (버스 포화 예상) |

---

## API 키 설정

`config.py`에서 관리하거나 환경변수로 오버라이드 가능합니다.

```bash
export PUBLIC_DATA_API_KEY=발급받은키
```
