"""수집 파이프라인 (§9.5). 기기 하나가 이상해도 멈추지 않는다."""
import asyncio
import json
import logging
import ssl
import statistics
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Literal

import aiomqtt
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.api.v1.ws import broadcast
from app.core import config
from app.db.pool import db
from app.domain.forecast import Forecast, forecast
from app.domain.psychrometrics import clamp_inputs, dew_point, rh_surface, t80
from app.domain.risk_state import STALE_AFTER_S, RiskMachine, State
from app.mqtt import validate
from app.workers import notifier

log = logging.getLogger(__name__)


class Telemetry(BaseModel):
    """§9.2 텔레메트리 페이로드 (하드웨어↔백엔드 계약).
    센서 읽기 실패는 null/NaN으로 올 수 있으므로 타입에서 막지 않고 validate에서 사유와 함께 거른다."""
    v: Literal[1]
    ts: int
    seq: int
    t_air: float | None
    rh: float | None
    t_surf: list[float | None] = Field(min_length=1)
    probe_ids: list[str]
    rssi: int | None = None
    fw: str | None = None

    @model_validator(mode="after")
    def _same_len(self):
        if len(self.t_surf) != len(self.probe_ids):
            raise ValueError("t_surf와 probe_ids 길이 불일치")
        return self


class Rejected(Exception):
    """계약은 지켰지만 값이 쓸 수 없는 메시지. dead-letter로 보내되 스택트레이스는 남기지 않는다."""


@dataclass
class Runtime:
    """기기별 메모리 상태. 재시작 시 restore()가 events·readings에서 복원한다."""
    machine: RiskMachine = field(default_factory=RiskMachine)
    rhs: deque = field(default_factory=lambda: deque(maxlen=90))  # (epoch, 최악 프로브 RHs), ts 오름차순
    state: str = "SAFE"  # 외부에 보이는 상태 (STALE 포함)
    event_id: int | None = None
    event_started: datetime | None = None
    forecast: Forecast | None = None
    last_rx: float = 0.0  # 수신한 벽시계 시각. STALE은 '마지막 수신 후' 기준(백로그의 과거 ts와 무관)
    last_ts: int = 0      # 판정에 반영한 마지막 기기 시각. 이 이하로 오는 메시지는 저장만 한다
    unnotified_from: str | None = None  # 백로그로 상태가 바뀌어 아직 알리지 못했을 때, 사용자가 마지막으로 안 상태
    pre_stale: str = "SAFE"  # STALE 직전 상태. 통신 끊김은 위험도를 바꾸지 않으므로 알림 비교는 이 값 기준


runtimes: dict[str, Runtime] = defaultdict(Runtime)


async def _notify(coro) -> None:
    """알림 실패가 수집을 멈추지 않게 한다 (notifier 자체도 예외를 던지지 않는 계약이지만 이중으로 막는다)."""
    try:
        await coro
    except Exception:
        log.exception("알림 처리 실패 — 수집은 계속")


async def set_state(device_id: str, rt: Runtime, new: str, at: datetime, notify: bool = True):
    if new == rt.state:
        return
    # 사용자가 알고 있는 위험 상태. STALE은 통신 문제일 뿐이라, STALE→ALERT는 'ALERT를 이미 안다'로 본다
    known = rt.pre_stale if rt.state == "STALE" else rt.state
    if new == "STALE":
        rt.pre_stale = known
    async with db().acquire() as con:
        if new == "STALE":  # 화면의 '연결됨' 표시와 상태가 어긋나지 않게
            await con.execute("UPDATE devices SET online = false WHERE id = $1", device_id)
        if rt.event_id:  # STALE(벽시계 시작) 뒤 과거 ts 백로그가 와도 종료가 시작보다 앞서지 않게
            at = max(at, rt.event_started)
            await con.execute("UPDATE events SET ended_at = $2 WHERE id = $1", rt.event_id, at)
        rt.event_id = None
        if new != "SAFE":
            rt.event_id = await con.fetchval(
                "INSERT INTO events (device_id, state, started_at) VALUES ($1, $2, $3) RETURNING id",
                device_id, new, at)
            rt.event_started = at
    rt.state = new
    await broadcast(device_id, {"type": "state", "device_id": device_id, "state": new, "at": at.isoformat()})
    if not notify:  # 백로그로 인한 전이 — 지금 알리면 '지난 일'이다. 다음 실시간 데이터에서 요약해 알린다
        if rt.unnotified_from is None:
            rt.unnotified_from = known
        return
    await _flush_notify(device_id, rt, at, known)


async def _flush_notify(device_id: str, rt: Runtime, at: datetime, old: str | None = None):
    """사용자가 마지막으로 안 상태 → 현재 상태로 알린다. 백로그 동안 오르내리다 제자리면 알리지 않는다."""
    frm = rt.unnotified_from or old
    rt.unnotified_from = None
    if frm is not None and frm != rt.state:
        await _notify(notifier.on_state(device_id, frm, rt.state, at))


async def store(home_id: str, device_id: str, msg: Telemetry, good: list[tuple[str, float]]) -> list[dict]:
    """한 메시지의 프로브들을 한 트랜잭션으로 저장. 새로 저장된 프로브만 돌려준다(QoS1 재수신분은 제외)."""
    at = datetime.fromtimestamp(msg.ts, UTC)
    probes = []
    async with db().acquire() as con, con.transaction():
        await con.execute("INSERT INTO homes (id) VALUES ($1) ON CONFLICT DO NOTHING", home_id)
        cal = await con.fetchrow(
            """INSERT INTO devices (id, home_id, fw, last_seen, online) VALUES ($1, $2, $3, now(), true)
               ON CONFLICT (id) DO UPDATE SET fw = EXCLUDED.fw, last_seen = now(), online = true
               RETURNING calib_t_air, calib_rh, calib_t_surf""",
            device_id, home_id, msg.fw)
        for probe_id, ts_raw in good:
            ta, rh, ts, sat = clamp_inputs(msg.t_air + cal["calib_t_air"], msg.rh + cal["calib_rh"],
                                           ts_raw + cal["calib_t_surf"])
            td, rhs = dew_point(ta, rh), rh_surface(ta, rh, ts)
            inserted = await con.fetchval(
                """INSERT INTO readings (time, device_id, probe_id, t_air, rh, t_surf, t_dew, rh_surf, delta_t, rssi, saturated)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT DO NOTHING RETURNING 1""",
                at, device_id, probe_id, ta, rh, ts, td, rhs, ts - td, msg.rssi, sat)
            if inserted:
                probes.append(dict(time=at, probe_id=probe_id, t_air=ta, rh=rh, t_surf=ts, t_dew=td,
                                   t80=t80(ta, rh), rh_surf=rhs))
    return probes


async def handle_telemetry(home_id: str, device_id: str, msg: Telemetry, now: float | None = None):
    now = time.time() if now is None else now

    # 1) 값 검증 — 실내 온습도·시각이 틀리면 메시지 전체, 벽면 프로브는 고장난 것만 뺀다
    if why := validate.check_ts(msg.ts, now) or validate.check_air(msg.t_air, msg.rh):
        raise Rejected(why)
    good = [(p, t) for p, t in zip(msg.probe_ids, msg.t_surf) if validate.surface_ok(t)]
    if len(good) < len(msg.t_surf):
        log.warning("%s 고장 프로브 제외: %s", device_id,
                    [(p, t) for p, t in zip(msg.probe_ids, msg.t_surf) if not validate.surface_ok(t)])
    if not good:
        raise Rejected(f"유효한 벽면 프로브 없음: {msg.t_surf}")

    # 2) 저장 (트랜잭션)
    probes = await store(home_id, device_id, msg, good)
    rt = runtimes[device_id]
    rt.last_rx = time.time()
    if not probes:
        return  # 전부 QoS1 재수신

    # 3) 판정 여부 결정 — 순서가 뒤집힌 과거 데이터는 저장만, 오래된 백로그는 알림 없이 판정만
    kind = validate.classify(msg.ts, rt.last_ts, now)
    if kind == "out_of_order":
        log.info("%s 순서 역전 데이터(ts=%s ≤ %s) — 저장만", device_id, msg.ts, rt.last_ts)
        return
    rt.last_ts = msg.ts
    live = kind == "live"
    at = probes[0]["time"]

    # 4) 판정은 가장 위험한 프로브 기준
    worst = max(p["rh_surf"] for p in probes)
    rt.rhs.append((msg.ts, worst))
    median5 = statistics.median(y for t, y in rt.rhs if msg.ts - t < 300)  # §5.5 5분 중앙값
    state = rt.machine.update(median5, msg.ts).name
    rt.forecast = forecast(list(rt.rhs))

    await set_state(device_id, rt, state, at, notify=live)
    if live and rt.unnotified_from is not None:  # 이번 메시지에서 전이는 없었지만 백로그 중 바뀐 상태가 남아 있음
        await _flush_notify(device_id, rt, at)
    if rt.event_id:
        await db().execute(
            """UPDATE events SET peak_rh_surf = GREATEST(peak_rh_surf, $2), min_delta_t = LEAST(min_delta_t, $3)
               WHERE id = $1""", rt.event_id, worst, min(p["t_surf"] - p["t_dew"] for p in probes))

    await broadcast(device_id, {
        "type": "reading", "device_id": device_id, "state": rt.state,
        "forecast": asdict(rt.forecast) if rt.forecast else None,
        "probes": [{**p, "time": at.isoformat()} for p in probes],
    })
    if rt.forecast and live:
        await _notify(notifier.on_forecast(device_id, rt.state, rt.forecast))


async def handle(m: aiomqtt.Message):
    _, _, home_id, device_id, kind = m.topic.value.split("/", 4)
    try:
        if kind == "telemetry":
            await handle_telemetry(home_id, device_id, Telemetry.model_validate_json(m.payload))
        elif kind == "status":
            online = m.payload.decode() == "online"
            await db().execute("UPDATE devices SET online = $2 WHERE id = $1", device_id, online)
            if not online and device_id in runtimes:  # LWT → 즉시 STALE (§8.2)
                await set_state(device_id, runtimes[device_id], "STALE", datetime.now(UTC))
    except Exception as e:  # 검증 실패든 뭐든 dead-letter로 보내고 계속
        if not isinstance(e, (ValidationError, Rejected)):
            log.exception("ingest 실패 %s", m.topic.value)
        try:  # DB가 잠깐 끊긴 경우 여기서 또 실패한다 — 그래도 수집 루프는 살아 있어야 한다
            await db().execute("INSERT INTO dead_letters (topic, payload, error) VALUES ($1, $2, $3)",
                               m.topic.value, m.payload.decode(errors="replace"), str(e)[:2000])
        except Exception:
            log.exception("dead-letter 기록도 실패 %s: %s", m.topic.value, m.payload[:500])


async def run():
    tls = ssl.create_default_context() if config.MQTT_TLS else None
    while True:
        try:
            async with aiomqtt.Client(
                config.MQTT_HOST, config.MQTT_PORT, username=config.MQTT_USER, password=config.MQTT_PASS,
                tls_context=tls, identifier="dg-server", clean_session=False,  # 서버 다운 중 메시지는 브로커가 보관
            ) as client:
                await client.subscribe("dg/v1/+/+/telemetry", qos=1)
                await client.subscribe("dg/v1/+/+/status", qos=1)
                log.info("MQTT 연결 %s:%s", config.MQTT_HOST, config.MQTT_PORT)
                async for m in client.messages:
                    await handle(m)
        except aiomqtt.MqttError as e:
            log.warning("MQTT 끊김: %s — 5초 후 재접속", e)
            await asyncio.sleep(5)
        except Exception:  # handle()은 예외를 삼키지만, 그 밖의 무엇이든 루프를 죽이지 않는다
            log.exception("수집 루프 오류 — 5초 후 재접속")
            await asyncio.sleep(5)


async def watch_stale():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for device_id, rt in list(runtimes.items()):
            if rt.state != "STALE" and now - rt.last_rx > STALE_AFTER_S:
                try:  # 기기 하나의 DB 오류가 다른 기기 감시를 막지 않게
                    await set_state(device_id, rt, "STALE", datetime.now(UTC))
                except Exception:
                    log.exception("%s STALE 전환 실패", device_id)


RESTORE_WINDOW_S = 45 * 60  # rhs 버퍼(90개 × 30초)와 같은 길이 — 재시작 직후에도 중앙값·예측이 바로 동작


async def restore(now: float | None = None):
    """재시작 시 메모리 상태 복원 (§known-limit 해소).

    - 기기가 최근(STALE_AFTER_S 이내)까지 데이터를 보냈다면: 열린 이벤트를 그대로 이어받고 상태·버퍼를 복원
      → 재시작만으로 ALERT가 SAFE로 떨어졌다가 다시 올라가며 알림이 또 가는 일이 없다
    - 아니면: 열린 이벤트를 '마지막 측정 시각'에 닫는다 (서버가 꺼져 있던 시간을 위험 시간에 넣지 않음)
      STALE 이벤트는 실제로 끊겨 있던 것이므로 지금 닫는다
    """
    now = time.time() if now is None else now
    runtimes.clear()
    async with db().acquire() as con:
        rows = await con.fetch(
            """SELECT d.id AS device_id, d.last_seen, e.id AS event_id, e.state, e.started_at,
                      (SELECT max(r.time) FROM readings r
                        WHERE r.device_id = d.id AND r.time > now() - interval '7 hours') AS last_time
               FROM devices d LEFT JOIN events e ON e.device_id = d.id AND e.ended_at IS NULL
               ORDER BY d.id, e.started_at DESC NULLS LAST""")
        for r in rows:
            dev, last = r["device_id"], r["last_time"]
            recent = last is not None and now - last.timestamp() <= STALE_AFTER_S
            keep_event = (r["event_id"] is not None and recent and r["state"] != "STALE"
                          and dev not in runtimes)  # 한 기기에 열린 이벤트가 여럿이면 최신 하나만 잇는다
            if r["event_id"] is not None and not keep_event:
                end = (datetime.fromtimestamp(now, UTC) if r["state"] == "STALE"
                       else max(last or r["last_seen"] or r["started_at"], r["started_at"]))
                await con.execute("UPDATE events SET ended_at = $2 WHERE id = $1", r["event_id"], end)
            if not recent or dev in runtimes:
                continue

            rt = runtimes[dev]
            pts = await con.fetch(
                """SELECT time, max(rh_surf) AS rhs FROM readings
                   WHERE device_id = $1 AND time > $2 GROUP BY time ORDER BY time""",
                dev, datetime.fromtimestamp(now - RESTORE_WINDOW_S, UTC))
            for p in pts:
                rt.rhs.append((int(p["time"].timestamp()), p["rhs"]))
            rt.last_ts = int(last.timestamp())
            rt.last_rx = now  # 유예: 재시작 직후 바로 STALE로 보지 않는다
            if keep_event:
                rt.state = r["state"]
                rt.machine.state = State[r["state"]]
                rt.event_id, rt.event_started = r["event_id"], r["started_at"]
            log.info("%s 상태 복원: %s (버퍼 %d개)", dev, rt.state, len(rt.rhs))
