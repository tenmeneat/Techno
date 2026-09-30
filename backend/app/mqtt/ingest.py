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
from app.domain.risk_state import STALE_AFTER_S, RiskMachine
from app.workers import notifier

log = logging.getLogger(__name__)


class Telemetry(BaseModel):
    """§9.2 텔레메트리 페이로드 (하드웨어↔백엔드 계약)."""
    v: Literal[1]
    ts: int
    seq: int
    t_air: float
    rh: float
    t_surf: list[float] = Field(min_length=1)
    probe_ids: list[str]
    rssi: int | None = None
    fw: str | None = None

    @model_validator(mode="after")
    def _same_len(self):
        if len(self.t_surf) != len(self.probe_ids):
            raise ValueError("t_surf와 probe_ids 길이 불일치")
        return self


@dataclass
class Runtime:
    """기기별 메모리 상태.
    ponytail: 프로세스 재시작 시 초기화(상태 SAFE부터 다시 dwell). 파일럿에서 문제되면 events에서 복원."""
    machine: RiskMachine = field(default_factory=RiskMachine)
    rhs: deque = field(default_factory=lambda: deque(maxlen=90))  # (epoch, 최악 프로브 RHs)
    state: str = "SAFE"  # 외부에 보이는 상태 (STALE 포함)
    event_id: int | None = None
    forecast: Forecast | None = None
    last_ts: float = 0.0


runtimes: dict[str, Runtime] = defaultdict(Runtime)


async def set_state(device_id: str, rt: Runtime, new: str, at: datetime):
    if new == rt.state:
        return
    async with db().acquire() as con:
        if rt.event_id:
            await con.execute("UPDATE events SET ended_at = $2 WHERE id = $1", rt.event_id, at)
        rt.event_id = None
        if new != "SAFE":
            rt.event_id = await con.fetchval(
                "INSERT INTO events (device_id, state, started_at) VALUES ($1, $2, $3) RETURNING id",
                device_id, new, at)
    rt.state = new
    await broadcast(device_id, {"type": "state", "device_id": device_id, "state": new, "at": at.isoformat()})
    await notifier.on_state(device_id, new)


async def handle_telemetry(home_id: str, device_id: str, msg: Telemetry):
    at = datetime.fromtimestamp(msg.ts, UTC)
    async with db().acquire() as con:
        await con.execute("INSERT INTO homes (id) VALUES ($1) ON CONFLICT DO NOTHING", home_id)
        cal = await con.fetchrow(
            """INSERT INTO devices (id, home_id, fw, last_seen, online) VALUES ($1, $2, $3, now(), true)
               ON CONFLICT (id) DO UPDATE SET fw = EXCLUDED.fw, last_seen = now(), online = true
               RETURNING calib_t_air, calib_rh, calib_t_surf""",
            device_id, home_id, msg.fw)

        probes = []
        for probe_id, ts_raw in zip(msg.probe_ids, msg.t_surf):
            ta, rh, ts, sat = clamp_inputs(msg.t_air + cal["calib_t_air"], msg.rh + cal["calib_rh"],
                                           ts_raw + cal["calib_t_surf"])
            td, rhs = dew_point(ta, rh), rh_surface(ta, rh, ts)
            inserted = await con.fetchval(
                """INSERT INTO readings (time, device_id, probe_id, t_air, rh, t_surf, t_dew, rh_surf, delta_t, rssi, saturated)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT DO NOTHING RETURNING 1""",
                at, device_id, probe_id, ta, rh, ts, td, rhs, ts - td, msg.rssi, sat)
            if not inserted:
                return  # QoS1 중복 수신
            probes.append(dict(time=at, probe_id=probe_id, t_air=ta, rh=rh, t_surf=ts, t_dew=td,
                               t80=t80(ta, rh), rh_surf=rhs))

    # 판정은 가장 위험한 프로브 기준
    rt = runtimes[device_id]
    rt.last_ts = msg.ts
    worst = max(p["rh_surf"] for p in probes)
    rt.rhs.append((msg.ts, worst))
    median5 = statistics.median(y for t, y in rt.rhs if msg.ts - t < 300)  # §5.5 5분 중앙값
    state = rt.machine.update(median5, msg.ts).name
    rt.forecast = forecast(list(rt.rhs))

    await set_state(device_id, rt, state, at)
    if rt.event_id:
        await db().execute(
            """UPDATE events SET peak_rh_surf = GREATEST(peak_rh_surf, $2), min_delta_t = LEAST(min_delta_t, $3)
               WHERE id = $1""", rt.event_id, worst, min(p["t_surf"] - p["t_dew"] for p in probes))

    await broadcast(device_id, {
        "type": "reading", "device_id": device_id, "state": rt.state,
        "forecast": asdict(rt.forecast) if rt.forecast else None,
        "probes": [{**p, "time": at.isoformat()} for p in probes],
    })
    if rt.forecast:
        await notifier.on_forecast(device_id, rt.state, rt.forecast)


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
        if not isinstance(e, ValidationError):
            log.exception("ingest 실패 %s", m.topic.value)
        await db().execute("INSERT INTO dead_letters (topic, payload, error) VALUES ($1, $2, $3)",
                           m.topic.value, m.payload.decode(errors="replace"), str(e)[:2000])


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


async def watch_stale():
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for device_id, rt in list(runtimes.items()):
            if rt.state != "STALE" and now - rt.last_ts > STALE_AFTER_S:
                await set_state(device_id, rt, "STALE", datetime.now(UTC))
