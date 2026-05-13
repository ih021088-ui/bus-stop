# 7790 버스 혼잡도 프로젝트 - 구현 현황

## 파일 구조
```
bus-stop/
├── frontend/
│   ├── index.html   ← 네이버 지도 기반 혼잡도 + 도착정보 표시 페이지
│   ├── README.md
│   └── README2.md   ← 이 파일
├── server.py        ← FastAPI 예측 서버
└── train.py         ← 혼잡도 예측 모델 학습
```

---

## 정류장 정보

| 정류장 | 위도 | 경도 | 방향 | GBIS stationId |
|--------|------|------|------|----------------|
| 효행초등학교정문 | 37.2160 | 126.9691 | 하교 | 233002245 |
| 아이파크정문 | 37.2138 | 126.9707 | 하교 | 233002371 |
| 신명아파트 | 37.2136 | 126.9722 | 하교 | 233002255 |
| 수원대입구 | 37.2143 | 126.9779 | 하교 | 233003021 |
| 사당역9번출구앞 | 37.4776 | 126.9815 | 등교 | 119000302 |

> **stationId 주의:** gbis.go.kr UI의 5자리 정류소 번호(55244 등)와 다름.  
> GBIS API 내부 ID이며, GGB prefix 없이 숫자만 사용.  
> 사당역9번출구앞은 서울 정류장이지만 GBIS API로 조회 가능 (stId: 119000302).

---

## 혼잡도 기준 (1층 버스 45석 기준)

| 등급 | 탑승 인원 | 색상 |
|------|-----------|------|
| 여유 | 22명 미만 | 초록 |
| 보통 | 22 ~ 35명 | 주황 |
| 혼잡 | 36명 이상 | 빨강 |

---

## API 설정

| 항목 | 값 |
|------|----|
| 사용 API | 경기도버스도착정보조회서비스 v2 (GBIS) |
| 엔드포인트 | `https://apis.data.go.kr/6410000/busarrivalservice/v2/getBusArrivalListv2` |
| 파라미터 | `serviceKey`, `stationId` |
| CORS | `Access-Control-Allow-Origin: *` 반환 → 브라우저 직접 호출 가능 |

> 서울시 버스 API(`ws.bus.go.kr`)는 제거됨. 사당역9번출구앞 포함 5개 정류장 모두 GBIS API로 통일.

---

## 도착정보 표시 형식

```
5분 후 도착 · 잔여 39석     ← 정상
곧 도착 · 잔여 12석         ← 1분 이하
도착 정보 없음              ← 운행 종료 또는 데이터 없음
```

> `7790(예약)` 노선(수요응답형 예약버스, routeId: 233000384)은 별도 운행 방식이므로 코드에서 제외하고 일반 7790(routeId: 200000149)만 사용.

---

## 네이버 지도 API

| 항목 | 값 |
|------|----|
| 파라미터 | `ncpKeyId` |
| Client ID | `0puucmux88` |
| 등록 URL | `https://busway.pages.dev` |

---

## 배포

| 항목 | 내용 |
|------|------|
| 플랫폼 | Cloudflare Pages |
| 배포 URL | `busway.pages.dev` |
| 배포 방법 | `index.html` 직접 업로드 |

---

## 구현 완료

- [x] 네이버 지도 위 정류장 마커 표시 (혼잡도 색상 구분)
- [x] 사이드바 정류장 카드 UI (예상 탑승 인원 + 혼잡도 배지)
- [x] 시간대 선택 드롭다운 (현재 시각 기준 자동 선택)
- [x] 마커 / 카드 클릭 시 지도 이동 및 팝업 표시
- [x] 현재 시각 자동 표시 (1분마다 갱신)
- [x] API 연결 실패 시 mock 데이터 자동 폴백
- [x] Cloudflare Pages 배포 (`busway.pages.dev`)
- [x] GBIS API 연동 - 5개 정류장 버스 도착 시간 표시
- [x] GBIS API 잔여 좌석 수 표시 (`remainSeatCnt1`)
- [x] 사당역9번출구앞 GBIS API 전환 (서울 정류장이지만 GBIS로 조회 + 잔여 좌석 확인)
- [x] `7790(예약)` 노선 필터링 (일반 7790과 구분)
- [x] 서울시 버스 API 코드 제거 (GBIS로 통일)
- [x] server.py 구현 (FastAPI 예측 API)
- [x] train.py 버그 수정 (날씨 merge, 반환값, overflow 계산)
- [x] GitHub `frontend` 브랜치 푸쉬 (`ih021088-ui/bus-stop`)

---

## 미완료 (추후 구현 필요)

- [ ] **server.py 외부 배포** - 현재 로컬에서만 실행 가능. 외부에서 접근 가능한 서버에 배포 필요 (예: Railway, Render, fly.io 등)
- [ ] **프론트엔드 ↔ server.py 실제 연결** - `index.html`의 `API_BASE_URL`을 실제 배포된 서버 주소로 교체
- [ ] **효행초등학교정문, 아이파크정문 좌표 현장 검증** - 현재 좌표는 추정값, 실제 정류장 위치 확인 필요
- [ ] **도착정보 자동 갱신** - 현재는 페이지 로드 시 1회만 호출. 일정 주기(예: 30초~1분)마다 자동 재호출 기능 추가
- [ ] **운행 시간 외 안내 메시지** - 7790 운행 시간(등교: 07~10시, 하교: 13~18시) 외에는 별도 안내 문구 표시

---

## 백엔드 연결 방법 (server.py)

`index.html` 내 `API_BASE_URL`을 실제 서버 주소로 변경:

```javascript
const API_BASE_URL = 'http://localhost:8000';  // → 실제 서버 주소로 교체
```

server.py 실행:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

API 응답 형식:
```json
{
  "date": "2026-05-12",
  "hour": 15,
  "direction": "depart",
  "stops": [
    { "stop": "효행초등학교정문", "boardings": 10.9, "congestion": "여유" },
    { "stop": "아이파크정문",    "boardings": 8.3,  "congestion": "여유" },
    { "stop": "신명아파트",      "boardings": 12.1, "congestion": "여유" },
    { "stop": "수원대입구",      "boardings": 19.4, "congestion": "여유" },
    { "stop": "사당역9번출구앞", "boardings": 31.2, "congestion": "보통" }
  ]
}
```
