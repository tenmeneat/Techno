"""안정성 테스트 — 수집 루프·워커·WS가 한 곳의 실패로 멈추지 않는지. DB 없이 돈다.
restore()는 실제 SQL을 타므로 Postgres로 따로 확인한다 (PR 설명 참고)."""
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main
from app.api.v1 import ws as wsmod
from app.core import config
from app.mqtt import ingest
from tests.test_ingest import Env


def test_dead_letter_failure_does_not_kill_ingest():
    env = Env()

    async def broken(sql, *a):
        raise ConnectionError("DB 잠깐 끊김")
    env.db.execute = broken
    m = SimpleNamespace(topic=SimpleNamespace(value="dg/v1/home/dev1/telemetry"), payload=b"not json")
    asyncio.run(ingest.handle(m))  # 예외가 밖으로 나오지 않아야 한다


def test_supervise_restarts_crashed_worker():
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("워커 오류")
        await asyncio.sleep(3600)

    async def go():
        t = asyncio.create_task(main.supervise("t", flaky, delay=0))
        for _ in range(100):
            await asyncio.sleep(0.01)
            if len(calls) >= 3:
                break
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    asyncio.run(go())
    assert len(calls) == 3


class FakeWS:
    def __init__(self, stuck=False):
        self.stuck, self.got, self.closed = stuck, [], False

    async def send_json(self, msg):
        if self.stuck:
            await asyncio.sleep(3600)
        self.got.append(msg)

    async def close(self):
        self.closed = True


def test_stuck_websocket_does_not_block_broadcast():
    wsmod._subs.clear()
    wsmod.SEND_TIMEOUT_S = 0.1
    good, stuck = FakeWS(), FakeWS(stuck=True)
    wsmod._subs["dev1"].add(good)
    wsmod._subs["*"].add(stuck)

    async def go():
        t0 = asyncio.get_running_loop().time()
        await wsmod.broadcast("dev1", {"type": "reading"})
        return asyncio.get_running_loop().time() - t0
    elapsed = asyncio.run(go())
    assert elapsed < 1.0
    assert good.got == [{"type": "reading"}]
    assert stuck not in wsmod._subs["*"] and stuck.closed
    wsmod.SEND_TIMEOUT_S = 2.0


def test_stale_marks_device_offline():
    env = Env()
    sqls = []
    orig = type(env.db.acquire()).execute

    async def rec(self, sql, *a):
        sqls.append(sql)
        await orig(self, sql, *a)
    type(env.db.acquire()).execute = rec
    try:
        rt = ingest.runtimes["dev1"]
        asyncio.run(ingest.set_state("dev1", rt, "STALE", datetime.now(UTC)))
    finally:
        type(env.db.acquire()).execute = orig
    assert any("online = false" in s for s in sqls)
    assert rt.state == "STALE"


def test_wifi_blip_does_not_resend_alert():
    """ALERT 중 와이파이가 잠깐 끊겨 STALE이 됐다가 돌아와도 ALERT 알림이 다시 가지 않는다."""
    from tests.test_ingest import NOW, run, series
    env = Env()
    run(env, series(NOW, 15, rh=75.0), now=lambda p: p["ts"])                # 결로 진입
    asyncio.run(ingest.set_state("dev1", env.rt, "STALE", datetime.now(UTC)))  # 끊김(LWT)
    run(env, series(NOW + 900, 5, rh=75.0), now=lambda p: p["ts"])          # 복귀, 여전히 결로
    assert env.rt.state == "CONDENSING"
    assert env.states == [("SAFE", "CONDENSING"), ("CONDENSING", "STALE")]  # 결로 알림은 한 번뿐
    run(env, series(NOW + 1200, 15, rh=50.0), now=lambda p: p["ts"])        # 환기 후 회복
    # 5분 중앙값이 내려오며 CONDENSING→ALERT→SAFE로 단계적으로 내려간다(하강 알림 걸러내기는 notifier 몫)
    assert env.rt.state == "SAFE"
    assert [n for _, n in env.states].count("CONDENSING") == 1  # 끊김 전후로 결로 진입 알림은 한 번
    assert ("STALE", "CONDENSING") not in env.states


def test_public_without_token_refuses_to_start():
    saved = (config.PUBLIC, config.API_TOKEN)
    try:
        config.PUBLIC, config.API_TOKEN = True, ""
        try:
            main.check_public_config()
            raise AssertionError("기동이 거부되어야 함")
        except RuntimeError:
            pass
        config.API_TOKEN = "secret"
        main.check_public_config()
        config.PUBLIC, config.API_TOKEN = False, ""
        main.check_public_config()  # 로컬 개발은 경고만
    finally:
        config.PUBLIC, config.API_TOKEN = saved


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
