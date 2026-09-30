# 원룸 결로·곰팡이 예측 시스템

기술설계서 v1.3 구현. ESP32 → MQTT(HiveMQ) → FastAPI + TimescaleDB → Next.js.

```
test_vectors.csv            §11.3 서버·펌웨어 공유 테스트 벡터
docker-compose.yml          db + api (+ offline 프로필: 로컬 mosquitto)
backend/                    조의혁·문승현
  app/main.py               진입점. 워커(ingest, stale 감시, 외기온, 일간 진단)를 같은 프로세스에서 띄운다
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
  src/lib/api.ts            fetch + 생성 타입 (src/lib/openapi.d.ts)
  src/lib/live.ts           WS → query cache 갱신            §10.4
  src/lib/notifications.ts  NotificationAdapter (Web Push / 추후 FCM) §10.5
  src/components/RiskChart.tsx  Ts/Td/T80 + 위험 밴드       §10.3
  src/app/                  홈 · devices/[id] · diagnostics · report · settings
  public/sw.js, manifest    PWA
```

## 실행

```bash
cp .env.example .env          # HiveMQ 접속 정보 채우기
docker compose up -d --build  # 오프라인이면: --profile offline, .env의 MQTT_HOST=mosquitto
```

```bash
cd backend && pip install -r requirements.txt paho-mqtt && python tools/simulator.py --scenario mould --speed 60
```

```bash
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

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
