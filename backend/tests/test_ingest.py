"""수집 파이프라인 테스트 — DB·MQTT 없이 돈다. `pytest` 또는 `python tests/test_ingest.py`.

validate.py(순수 함수)는 직접, handle()/handle_telemetry()는 가짜 DB·알림·WS를 끼워서 검증한다.
SQL 자체(트랜잭션 등)는 실제 Postgres에서 확인해야 한다 — 여기서는 판정·알림 흐름만 본다.
"""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.mqtt import ingest, validate

NOW = 1_800_000_000  # 고정 '현재' 시각 (2027-01)


# ───────── validate (순수 함수) ─────────

def test_check_ts():
    assert validate.check_ts(NOW, NOW) is None
    assert validate.check_ts(NOW - 6 * 3600, NOW) is None   # 오프라인 버퍼 한도 안
    assert validate.check_ts(NOW * 1000, NOW)                # 밀리초
    assert validate.check_ts(30, NOW)                        # NTP 동기 전(1970)
    assert validate.check_ts(NOW + 3600, NOW)                # 시계 앞섬


def test_check_air():
    assert validate.check_air(20, 50) is None
    for t, rh in [(None, 50), (float("nan"), 50), (20, None), (20, float("nan")), (20, 0), (20, 120), (-40, 50)]:
        assert validate.check_air(t, rh), (t, rh)


def test_surface_ok():
    assert validate.surface_ok(15.0)
    for bad in (-127.0, 85.0, None, float("nan"), float("inf"), -40.0, 60.0):
        assert not validate.surface_ok(bad), bad


def test_classify():
    assert validate.classify(NOW, 0, NOW) == "live"
    assert validate.classify(NOW - 3600, 0, NOW) == "late"
    assert validate.classify(NOW - 60, NOW, NOW) == "out_of_order"
    assert validate.classify(NOW, NOW, NOW) == "out_of_order"  # 같은 시각 재전송


# ───────── 가짜 환경 ─────────

class FakeCon:
    def __init__(self, fdb):
        self.f = fdb

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, sql, *a):
        if "dead_letters" in sql:
            self.f.dead.append(a)

    async def fetchrow(self, sql, *a):
        return {"calib_t_air": 0.0, "calib_rh": 0.0, "calib_t_surf": 0.0}

    async def fetchval(self, sql, *a):
        if "INTO readings" in sql:
            key = (a[0], a[1], a[2])
            if key in self.f.readings:
                return None
            self.f.readings.add(key)
            return 1
        if "INTO events" in sql:
            self.f.event_seq += 1
            return self.f.event_seq


class FakeDB:
    def __init__(self):
        self.readings, self.dead, self.event_seq = set(), [], 0

    def acquire(self):
        return FakeCon(self)

    async def execute(self, sql, *a):
        await FakeCon(self).execute(sql, *a)


class Env:
    """ingest 모듈의 db / broadcast / notifier를 갈아끼운다."""

    def __init__(self, notify_raises=False):
        self.db, self.states, self.forecasts, self.ws = FakeDB(), [], [], []
        ingest.runtimes.clear()
        ingest.db = lambda: self.db

        async def on_state(dev, old, new, at):
            if notify_raises:
                raise RuntimeError("push 서버 오류")
            self.states.append((old, new))

        async def on_forecast(dev, state, fc):
            self.forecasts.append(state)

        async def broadcast(dev, msg):
            self.ws.append(msg["type"])

        ingest.notifier = SimpleNamespace(on_state=on_state, on_forecast=on_forecast)
        ingest.broadcast = broadcast

    @property
    def rt(self):
        return ingest.runtimes["dev1"]


def payload(ts, rh=50.0, t_surf=(15.0, 16.2), t_air=20.0):
    return {"v": 1, "ts": ts, "seq": 0, "t_air": t_air, "rh": rh, "t_surf": list(t_surf),
            "probe_ids": [f"p{i}" for i in range(len(t_surf))]}


def run(env, msgs, now):
    """메시지 목록을 handle()로 흘린다 (dead-letter 경로까지 포함)."""
    async def go():
        for p in msgs:
            raw = p if isinstance(p, str) else json.dumps(p)
            m = SimpleNamespace(topic=SimpleNamespace(value="dg/v1/home/dev1/telemetry"), payload=raw.encode())
            orig = ingest.handle_telemetry
            ingest_now = now if not callable(now) else now(p)

            async def ht(h, d, msg, _now=ingest_now):
                return await orig(h, d, msg, now=_now)
            ingest.handle_telemetry = ht
            try:
                await ingest.handle(m)
            finally:
                ingest.handle_telemetry = orig
    asyncio.run(go())


def series(start, minutes, **kw):
    return [payload(start + i * 30, **kw) for i in range(minutes * 2)]


# 실내 20°C, 벽 15°C 기준: RH 50 → RHs 68.5(SAFE), RH 62 → 약 85(ALERT), RH 75 → 100(CONDENSING)


# ───────── ① 센서 고장값 ─────────

def test_disconnected_probe_does_not_trigger_condensing():
    env = Env()
    run(env, series(NOW - 900, 15, t_surf=(-127.0, 15.0)), now=lambda p: p["ts"])
    assert env.rt.state == "SAFE"
    assert env.states == []
    assert all(k[2] == "p1" for k in env.db.readings)  # 고장 프로브는 저장도 안 함


def test_all_probes_broken_goes_to_dead_letter():
    env = Env()
    run(env, [payload(NOW, t_surf=(-127.0, 85.0))], now=NOW)
    assert len(env.db.dead) == 1 and not env.db.readings
    assert "dev1" not in ingest.runtimes or env.rt.state == "SAFE"


def test_nan_and_null_values():
    env = Env()
    run(env, ['{"v":1,"ts":%d,"seq":0,"t_air":NaN,"rh":50,"t_surf":[15],"probe_ids":["p0"]}' % NOW], now=NOW)
    assert len(env.db.dead) == 1                       # 실내 NaN → 메시지 전체 거부
    run(env, [payload(NOW + 30, t_surf=(None, 15.0))], now=NOW + 30)
    assert len(env.db.dead) == 1 and len(env.db.readings) == 1  # null 프로브만 제외


# ───────── ④ 기기 시각 ─────────

def test_bad_timestamps_rejected():
    env = Env()
    run(env, [payload(NOW * 1000), payload(30)], now=NOW)
    assert len(env.db.dead) == 2 and not env.db.readings


# ───────── ② 순서 역전 ─────────

def test_out_of_order_is_stored_but_not_judged():
    env = Env()
    run(env, series(NOW - 600, 10), now=NOW)          # 10분간 SAFE
    before = (env.rt.state, env.rt.last_ts, len(env.rt.rhs))
    run(env, [payload(NOW - 900, rh=75.0)], now=NOW)  # 그보다 과거의 결로 데이터가 뒤늦게 도착
    assert (env.rt.state, env.rt.last_ts, len(env.rt.rhs)) == before
    assert (NOW - 900) in {k[0].timestamp() for k in env.db.readings}  # 저장은 됨


# ───────── ③ 백로그 알림 ─────────

def test_backlog_does_not_notify_past_events():
    env = Env()
    # 3시간 전 20분간 결로 → 이후 회복. 재접속 후 순서대로 한꺼번에 도착
    backlog = series(NOW - 3 * 3600, 20, rh=75.0) + series(NOW - 3 * 3600 + 1200, 30, rh=50.0)
    run(env, backlog, now=NOW)
    assert env.states == [] and env.forecasts == []
    run(env, series(NOW, 2, rh=50.0), now=lambda p: p["ts"])  # 실시간 재개, 여전히 안전
    assert env.states == []  # 백로그 동안 올랐다 내려와 제자리 → 알릴 것 없음


def test_backlog_into_danger_notifies_once_when_live():
    env = Env()
    run(env, series(NOW - 1800, 20, rh=75.0), now=NOW)  # 30분 전부터 결로 (백로그)
    assert env.rt.state == "CONDENSING" and env.states == []
    run(env, series(NOW, 3, rh=75.0), now=lambda p: p["ts"])  # 실시간도 여전히 결로
    assert env.states == [("SAFE", "CONDENSING")]  # 한 번만, 사용자가 마지막으로 안 상태 기준


def test_live_transition_notifies():
    env = Env()
    run(env, series(NOW, 15, rh=75.0), now=lambda p: p["ts"])
    assert env.states == [("SAFE", "CONDENSING")]


# ───────── ⑤ 중복 ─────────

def test_duplicate_message_ignored():
    env = Env()
    msgs = series(NOW, 15, rh=75.0)
    run(env, msgs, now=lambda p: p["ts"])
    n, rhs, states = len(env.db.readings), len(env.rt.rhs), list(env.states)
    run(env, msgs[-3:], now=lambda p: p["ts"])  # QoS1 재수신
    assert (len(env.db.readings), len(env.rt.rhs), env.states) == (n, rhs, states)


# ───────── ⑩ 알림 실패 격리 ─────────

def test_notifier_failure_does_not_break_ingest():
    env = Env(notify_raises=True)
    run(env, series(NOW, 15, rh=75.0), now=lambda p: p["ts"])
    assert env.rt.state == "CONDENSING"
    assert env.db.dead == []                    # 측정값 처리는 실패로 기록되지 않음
    assert env.ws.count("reading") == 30        # 실시간 전송도 계속됨


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
