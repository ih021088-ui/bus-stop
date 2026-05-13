# Git 규칙 - 우리 프로젝트 규칙

> Git이 뭔지 모르겠으면 `git_guide.md`를 먼저 읽어.

---

## 1. 역할 분담

| 이름 | 역할 | 담당 브랜치 | 담당 폴더/파일 |
|------|------|------------|---------------|
| **조장 (PM)** | 전체 설계 + 모델 학습 + PR 리뷰/머지 | `feat/model-training` | `model/` 전체 |
| **정인** | 데이터 수집 파이프라인 | `feat/data-pipeline` | `data/collect/` 전체 |
| **승민** | FastAPI 백엔드 | `feat/backend-api` | `backend/` 전체 |
| **승주** | Next.js 프론트엔드 | `feat/frontend-map` | `frontend/` 전체 |
| **성빈** | 발표자료 + 수원대 검증 (선택) | `feat/validation` | `docs/validation/` |

**PR 머지는 조장만 한다.** 본인 PR 본인 머지 금지.

---

## 2. 브랜치 구조

```
main   (발표용 최종 버전 - 직접 수정 절대 금지)
 │
 └── dev (개발 통합 - 모든 PR은 여기로)
      │
      ├── feat/model-training    (조장)
      ├── feat/data-pipeline     (정인)
      ├── feat/backend-api       (승민)
      ├── feat/frontend-map      (승주)
      └── feat/validation        (성빈)
```

- **main**: 발표 때 보여줄 최종 코드. 건드리지 않음.
- **dev**: 팀원들 작업이 모이는 곳. PR로만 합침.
- **feat/xxx**: 각자 작업하는 브랜치. **여기서만 코딩한다.**

---

## 3. 브랜치 이름 규칙

| 접두사 | 용도 | 예시 |
|--------|------|------|
| `feat/` | 새 기능 개발 | `feat/tago-realtime` |
| `fix/` | 버그 수정 | `fix/weather-parsing` |
| `docs/` | 문서 작업 | `docs/api-guide` |

- 영어 소문자 + 하이픈(`-`)만 사용
- 한글, 공백, 대문자 사용 금지

---

## 4. 커밋 메시지 규칙

```
<타입>: <설명>
```

| 타입 | 의미 | 예시 |
|------|------|------|
| `feat` | 새 기능 추가 | `feat: TAGO 실시간 도착 API 연결` |
| `fix` | 버그 수정 | `fix: 기상청 격자 좌표 오류 수정` |
| `refactor` | 리팩토링 | `refactor: 날씨 파싱 함수 분리` |
| `docs` | 문서 수정 | `docs: README 실행 방법 추가` |
| `chore` | 설정, 패키지 등 | `chore: requirements.txt 업데이트` |

### 좋은 예 vs 나쁜 예

```bash
# 좋은 예
git commit -m "feat: 5분 폴링 스케줄러 및 SQLite 저장 구현"
git commit -m "fix: 공휴일 API 응답 단일 item 처리 오류 수정"
git commit -m "feat: 혼잡도 배지 컴포넌트 색상 분기 추가"

# 나쁜 예
git commit -m "수정"
git commit -m "됨"
git commit -m "update"
git commit -m "ㅋㅋ"
```

---

## 5. 매일 작업 흐름

### 작업 시작 (코딩 전 항상)

```bash
# ① 내 브랜치로 이동
git checkout feat/내브랜치

# ② dev의 최신 변경사항 가져오기
git pull origin dev

# ③ 충돌 있으면 해결 후
git add .
git commit -m "fix: dev 머지 충돌 해결"
```

### 작업 완료 (코딩 후)

```bash
# ① 수정한 파일 확인
git status

# ② 내가 수정한 파일만 추가 (git add . 보다 안전)
git add 수정한파일1 수정한파일2

# ③ 커밋
git commit -m "feat: 오늘 한 작업 설명"

# ④ 내 브랜치에 push
git push origin feat/내브랜치
```

### PR (Pull Request) 생성

1. GitHub 웹사이트 접속
2. "Compare & pull request" 버튼 클릭
3. **base: `dev`** ← **compare: `feat/내브랜치`** 확인 (중요!)
4. 제목: 커밋 메시지와 동일한 형식으로
5. 설명: 무엇을 했는지 간단히
6. "Create pull request" 클릭
7. **조장이 리뷰 후 머지** (본인이 직접 머지 금지)

---

## 6. PR 규칙

| 항목 | 규칙 |
|------|------|
| PR 대상 | 항상 `dev` 브랜치로 |
| 리뷰어 | 조장이 모든 PR 리뷰 |
| 본인 머지 | **금지** (조장만 머지) |
| PR 크기 | 가능하면 작게 (기능 하나씩) |
| 올리기 전 | 로컬에서 실행 확인 후 PR |

---

## 7. 충돌 방지 규칙

### 파일 소유권

**각 팀원은 자기 담당 폴더/파일만 수정한다.**

```
조장   → model/ 만
정인   → data/collect/ 만
승민   → backend/ 만
승주   → frontend/ 만
성빈   → docs/validation/ 만
```

다른 팀원의 파일을 수정해야 할 경우:
1. 카톡으로 먼저 알리기
2. 또는 조장에게 요청

### 공통 파일 수정 (조장 승인 후 진행)

아래 파일은 **조장 승인 후**에만 수정:
- `docker-compose.yml`
- `backend/requirements.txt` / `frontend/package.json`
- `.env.example`

패키지 추가가 필요하면 조장한테 카톡으로 먼저 물어보기.

---

## 8. 긴급 상황 대응

### 내 브랜치에서 실수했을 때

```bash
# 마지막 커밋 취소 (코드는 유지)
git reset --soft HEAD~1

# 특정 파일만 되돌리기 (주의: 수정 내용 사라짐)
git checkout -- 파일명
```

### 충돌 해결이 안 될 때

```bash
# 머지 취소하고 원래 상태로
git merge --abort

# → 조장에게 도움 요청
```

### 잘못된 브랜치에서 작업했을 때

```bash
# 변경사항을 임시 저장
git stash

# 올바른 브랜치로 이동
git checkout feat/내브랜치

# 임시 저장한 변경사항 복원
git stash pop
```

---

## 9. 금지 사항

| 금지 항목 | 이유 |
|-----------|------|
| `main`에 직접 push | 발표용 버전 망가질 수 있음 |
| `dev`에 직접 push | PR 리뷰 우회 |
| `git push --force` | 다른 팀원 작업 덮어씀 |
| 다른 팀원 파일 무단 수정 | 충돌 발생 |
| 본인 PR 본인 머지 | 코드 리뷰 우회 |
| `.env`, API 키 커밋 | 키 유출 → 과금 폭탄 |
| `git add .` 남용 | 불필요한 파일 포함 위험 |

---

## 10. 조장(PM) 워크플로우

### PR 머지 (수시)

1. GitHub에서 PR 확인
2. **Files changed** 탭에서 코드 리뷰
3. 문제 없으면 → **Squash and merge** 클릭
4. 문제 있으면 → 코멘트 남기고 **Request changes**

### 발표 직전 최종 배포

```bash
git checkout main
git pull origin main
git merge dev
git push origin main
```
