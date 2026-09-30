# 원룸 결로·곰팡이 예측 시스템

기술설계서 v1.3 구현체. ESP32 → MQTT(HiveMQ) → FastAPI + TimescaleDB → Next.js 웹 대시보드(PWA).
판정 기준은 ISO 13788 표면 상대습도 80%(§3), 단열 진단은 fRsi/TDR(§4).

## 진행 현황 (2026-09-30 기준)

| 영역 | 상태 | 검증 |
|---|---|---|
| 계산·판정 도메인 (Td, RHs, T80, fRsi, 상태머신, 예측) | 완료 | 단위테스트 통과 (§2.4·§3.2 표 값, 히스테리시스·dwell, 예측 게이팅) |
| DB 스키마 (hypertable, 1분·1시간 연속 집계, 압축·보존) | 완료 | **미검증** — Docker로 한 번도 띄워보지 않음 |
| 수집 파이프라인 (검증 → 중복 제거 → 보정 → 판정 → WS) | 완료 | **미검증** (DB·MQTT 필요) |
| REST API 10종 + WebSocket | 완료 | 임포트·OpenAPI 생성 확인. 실제 응답 **미검증** |
| 워커: Web Push, 외기온(KMA→Open-Meteo 폴백), 일간 진단 | 완료 | **미검증** |
| 가상 센서 퍼블리셔 (시나리오 재생) | 완료 | 문법 확인만 |
| 프런트 5개 화면 (홈·상세·진단·리포트·설정) | 완료 | 타입체크·정적 빌드 통과. 실데이터 화면 **미확인** |
| PWA (서비스워커, manifest, 알림 어댑터) | 완료 | 실제 푸시 수신 **미확인** |
| 배포 구성 (FastAPI가 프런트 서빙 + Tailscale Funnel) | 완료 | 정적 라우팅만 확인. `docker compose build` **미확인** |
| 펌웨어 | 없음 | 하드웨어 파트 담당. `test_vectors.csv`로 계산 일치 확인할 것 |

**다음 할 일:** Docker 설치 후 `docker compose --profile offline up --build` → 시뮬레이터로 파이프라인 전체를 처음 관통시키는 것.

## 설계서와 다른 점

| 설계서 | 구현 | 이유 |
|---|---|---|
| SQLAlchemy 모델 | `schema.sql` + asyncpg | hypertable·연속 집계가 어차피 원시 SQL |
| 서버에서 PDF 생성 | 인쇄용 페이지 → 브라우저 PDF 저장 | PDF 라이브러리 불필요 |
| Cloudflare Tunnel (§7.3) | **Tailscale Funnel** | 고정 주소를 도메인 비용 없이. **§11.4 팀장 승인 필요** |
| 프런트 별도 호스트 | FastAPI가 정적 빌드를 같은 출처로 서빙 | 주소 하나, CORS·재빌드 불필요, Capacitor 래핑에도 그대로 사용 |
| `/devices/{id}` 화면 경로 | `/device/?id=...` | 정적 export는 동적 경로 불가 |
| MSW 목 서버 | 없음 | 로컬 `docker compose` + 시뮬레이터로 대체. Docker 없이 프런트 작업이 필요하면 추가 |
| next-pwa | `public/sw.js` 직접 작성 | 푸시 수신만 필요 |
| cmd 토픽 (서버→기기) | 미구현 | 캘리브레이션은 서버에서 적용하므로 아직 쓸 곳 없음 |

**알려진 한계**
- 판정 상태는 메모리에만 있다. API 재시작 시 SAFE부터 다시 dwell을 센다(열려 있던 events는 기동 시 닫음).
- KMA 응답 컬럼 위치(TA=12번째, HM=14번째)는 추정값. 키 발급 후 `help=1`로 확인 필요 (`workers/weather_sync.py`).
- TDR 부위별 기준값 미확보(§14.3). 지금은 fRsi 0.70 기준만 사용.
- API 토큰은 빌드 시 프런트에 들어가 브라우저에 노출되는 단순 토큰(§7.3 학기 범위).

## 구조

```
test_vectors.csv            §11.3 서버·펌웨어 공유 테스트 벡터
docker-compose.yml          db + api(프런트 포함) + offline 프로필: 로컬 mosquitto
backend/                    조의혁·문승현
  Dockerfile                2단계: Node로 프런트 빌드 → Python 이미지에 static/으로 포함
  app/main.py               진입점. 워커(ingest, stale 감시, 외기온, 일간 진단)를 같은 프로세스에서 띄우고 정적 파일 서빙
  app/core/config.py        환경변수
  app/domain/               순수함수만 (I/O 금지)
    psychrometrics.py         Td, RHs, T80, fRsi            §2–§4
    risk_state.py             상태머신 (히스테리시스 + dwell) §3.3
    forecast.py               OLS 외삽 + 게이팅              §6
  app/mqtt/ingest.py        수집 파이프라인                   §9.5
  app/db/schema.sql         hypertable, 연속 집계, 압축·보존  §9.4
  app/api/v1/schemas.py     ★ 프런트 계약 (OpenAPI 원천)      §11.1
  app/api/v1/*.py           devices, readings, events, reports, push, ws
  app/workers/              notifier(Web Push), weather_sync(KMA→Open-Meteo), diagnostics(07:00)
  tools/simulator.py        가상 센서 퍼블리셔 + 시나리오 재생 §11.2
  tests/test_domain.py
  openapi.json              생성물 — 프런트 타입의 원천
frontend/                   나현웅·유민서
  next.config.ts            output: "export" → out/ 정적 파일
  src/lib/api.ts            fetch + 생성 타입 (src/lib/openapi.d.ts). 기본은 같은 출처
  src/lib/live.ts           WS → query cache 갱신            §10.4
  src/lib/notifications.ts  NotificationAdapter (Web Push / 추후 FCM) §10.5
  src/components/RiskChart.tsx  Ts/Td/T80 + 위험 밴드       §10.3
  src/app/                  홈 · device (?id=) · diagnostics · report · settings
  public/sw.js, manifest    PWA
```

### API

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/v1/devices` | 기기 목록 + 현재 상태 |
| GET·PATCH | `/api/v1/devices/{id}` | 기기 정보 / 라벨·위치 수정 |
| GET | `/api/v1/devices/{id}/current` | 프로브별 최신값, 상태, 예측 구간 |
| GET | `/api/v1/devices/{id}/series?from&to&bucket` | 시계열 (raw / 1m / 1h / 1d) |
| GET | `/api/v1/devices/{id}/events?from&to` | 상태 이벤트 구간 |
| GET | `/api/v1/devices/{id}/diagnostics?days=` | 일간 fRsi/TDR, ALERT 시간, 곰팡이 노출량 |
| POST | `/api/v1/devices/{id}/calibration` | 캘리브레이션 오프셋 |
| POST | `/api/v1/reports` | 리포트 데이터 |
| GET·POST | `/api/v1/push/vapid-public-key`, `/push/subscribe` | Web Push 구독 |
| WS | `/ws/live?device_id=` | `reading` / `state` 메시지 |

전체 스펙은 서버를 띄운 뒤 `http://localhost:8000/docs`.

## 개발 환경 준비 (Windows)

관리자 PowerShell에서 WSL 설치 후 재부팅, 그다음 Docker Desktop 설치·실행 (Engine running 확인).

```bash
wsl --install
```
```bash
winget install Docker.DockerDesktop
```

## 실행

```bash
cp .env.example .env
```

HiveMQ 계정 전이라면 `.env`의 MQTT를 로컬 브로커로: `MQTT_HOST=mosquitto`, `MQTT_PORT=1883`, `MQTT_TLS=false`, `MQTT_USER`·`MQTT_PASS` 비움.

```bash
docker compose --profile offline up -d --build
```

http://localhost:8000 에서 대시보드 확인. 가짜 센서 데이터 넣기 (5시간 곡선을 5분에 재생):

```bash
cd backend && pip install -r requirements.txt paho-mqtt && python tools/simulator.py --scenario mould --speed 60
```

프런트만 핫리로드로 개발할 때 (API는 docker로 띄워둔 상태):

```bash
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

## 배포 (웹사이트로 공개)

api 컨테이너가 프런트를 정적 빌드해서 `http://localhost:8000`에 API와 함께 서빙한다.
외부 공개는 호스트 PC에서 Tailscale Funnel로 HTTPS 고정 주소(`https://<pc이름>.<tailnet>.ts.net`)를 붙인다 — 무료, 도메인 불필요.
서비스워커·Web Push는 HTTPS에서만 동작하므로 이 단계가 필수다.

1. 호스트 PC(Windows 쪽)에 Tailscale 설치·로그인 — `winget install Tailscale.Tailscale`. 설치 후 터미널은 새로 연다
2. `.env`에 `API_TOKEN`, `VAPID_*` 채우고 `docker compose up -d --build` (토큰은 빌드 시 프런트에 들어간다)
3. 공개 (처음 실행 시 뜨는 링크에서 HTTPS·Funnel 허용):

```bash
tailscale funnel --bg 8000
```

끄기: `tailscale funnel --bg 8000 off`. DB(5432)와 API(8000) 포트는 127.0.0.1에만 열려 있어 Funnel 외 경로로는 노출되지 않는다.
파일럿 기간 호스트 PC는 절전 해제. 아이폰 사용자는 Safari → 홈 화면에 추가해야 푸시가 온다.

## 계약 변경 (§11.4)

`backend/app/api/v1/schemas.py` 수정 → 팀장 승인 → 아래로 스펙·타입 재생성 후 같이 커밋.

```bash
cd backend && python -c "import json; from app.main import app; json.dump(app.openapi(), open('openapi.json','w',encoding='utf8'), ensure_ascii=False, indent=1)"
```

```bash
cd frontend && npm run gen:api
```

## 테스트

```bash
cd backend && python tests/test_domain.py
```
