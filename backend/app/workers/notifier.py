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


async def on_state(device_id: str, state: str):
    """상태 진입 시 1회. events 행이 한 번만 생기므로 중복 발송 없음."""
    if state in STATE_PUSH:
        title, body = STATE_PUSH[state]
        await send(title, body, f"/devices/{device_id}", bypass_quiet=state == "CONDENSING")


async def on_forecast(device_id: str, state: str, fc: Forecast):
    """§6.5: SAFE/WATCH일 때만, 24시간 내 최대 2회, 최소 간격 3시간."""
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
               f"/devices/{device_id}")
