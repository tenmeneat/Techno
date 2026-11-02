"""Web Push 발송 (§9.7, §6.5). 앱 전환 시 send()만 FCM으로 교체."""
import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime

from pywebpush import WebPushException, webpush

from app.core import config
from app.db.pool import db
from app.domain.forecast import Forecast

log = logging.getLogger(__name__)

STATE_PUSH = {
    "ALERT": ("곰팡이 위험 구간", "벽면 습도가 80%를 넘었습니다. 환기하세요."),
    "CONDENSING": ("결로 발생 중", "벽면에 물이 맺히는 조건입니다. 지금 환기하세요."),
}
_forecast_sent: dict[str, list[float]] = defaultdict(list)


def _quiet(hour: int, start: int, end: int) -> bool:
    return (start <= hour or hour < end) if start > end else (start <= hour < end)


async def send(title: str, body: str, url: str, bypass_quiet: bool = False):
    if not config.VAPID_PRIVATE_KEY:
        log.info("[push 미설정] %s — %s", title, body)
        return
    hour = datetime.now(config.TZ).hour
    payload = json.dumps({"title": title, "body": body, "url": url})
    for s in await db().fetch("SELECT endpoint, keys, quiet_start, quiet_end FROM push_subscriptions"):
        if not bypass_quiet and _quiet(hour, s["quiet_start"], s["quiet_end"]):
            continue
        try:
            await asyncio.to_thread(
                webpush, subscription_info={"endpoint": s["endpoint"], "keys": json.loads(s["keys"])},
                data=payload, vapid_private_key=config.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": config.VAPID_SUBJECT})
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):  # 만료된 구독
                await db().execute("DELETE FROM push_subscriptions WHERE endpoint = $1", s["endpoint"])
            else:
                log.warning("push 실패: %s", e)


async def on_state(device_id: str, old: str, new: str, at: datetime) -> None:
    """상태 전이 시 1회 호출된다 (ingest.set_state).

    계약 (A·B 공통):
    - old/new: SAFE / WATCH / ALERT / CONDENSING / STALE, at: 전이 시각(UTC).
    - ingest는 '실시간 데이터'일 때만 이 함수를 부른다. 지연된 백로그로 인한 전이는 부르지 않는다.
    - 이 함수는 예외를 밖으로 던지지 않아야 한다(B 구현). 상승 여부·재발송 제한·무음 시간 판단은 전부 여기서 한다.
    TODO(B): 현재는 기존 동작 그대로 — new 기준으로만 발송.
    """
    if new in STATE_PUSH:
        title, body = STATE_PUSH[new]
        await send(title, body, f"/device/?id={device_id}", bypass_quiet=new == "CONDENSING")


async def on_forecast(device_id: str, state: str, fc: Forecast) -> None:
    """§6.5: SAFE/WATCH일 때만, 24시간 내 최대 2회, 최소 간격 3시간.
    on_state와 같은 계약: 실시간 데이터일 때만 호출되며, 예외를 밖으로 던지지 않아야 한다(B 구현)."""
    if state not in ("SAFE", "WATCH"):
        return
    now = time.time()
    sent = _forecast_sent[device_id] = [t for t in _forecast_sent[device_id] if now - t < 86400]
    if len(sent) >= 2 or (sent and now - sent[-1] < 3 * 3600):
        return
    sent.append(now)
    what = "곰팡이 위험 구간" if fc.target < 100 else "결로"
    await send("곧 습해집니다",
               f"약 {fc.hours_low:.1f}–{fc.hours_high:.1f}시간 뒤 {what} 진입 예상. 미리 환기하세요.",
               f"/device/?id={device_id}")
