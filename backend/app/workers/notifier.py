"""Web Push delivery, persistent forecast limits and uncertain-result recovery."""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime
from uuid import uuid4

from pywebpush import WebPushException, webpush
from requests.exceptions import RequestException

from app.core import config
from app.db.pool import db
from app.domain.forecast import Forecast

log = logging.getLogger(__name__)
DB_TIMEOUT = 3
PUSH_TIMEOUT = 8

STATE_PUSH = {
    "ALERT": ("곰팡이 위험 구간", "벽면 습도가 80%를 넘었습니다. 환기하세요."),
    "CONDENSING": ("결로 발생 중", "벽면에 물이 맺히는 조건입니다. 지금 환기하세요."),
}
_forecast_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


async def _db_call(operation):
    return await asyncio.wait_for(operation, timeout=DB_TIMEOUT)


def _quiet(hour: int, start: int, end: int) -> bool:
    if start == end:
        return False
    return (hour >= start or hour < end) if start > end else start <= hour < end


async def reconcile_history(database=None, device_id=None):
    """Old PENDING rows are uncertain, never proof of failure or grounds to resend."""
    database = database if database is not None else db()
    return await _db_call(database.execute(
        """UPDATE notification_history
           SET status = 'UNKNOWN', error = '결과 확인 불가: PENDING 15분 초과'
           WHERE status = 'PENDING'
             AND created_at < now() - interval '15 minutes'
             AND ($1::text IS NULL OR device_id = $1)""", device_id))


async def maintain_history():
    while True:
        await asyncio.sleep(60)
        try:
            await reconcile_history()
        except Exception:
            log.error("알림 이력 정리 실패; 다음 주기에 재시도")


async def _update_history(database, history_id, status, error=None):
    for attempt in range(3):
        try:
            result = await _db_call(database.execute(
                """UPDATE notification_history
                   SET status = $2,
                       sent_at = CASE WHEN $2 = 'SENT' THEN now() ELSE NULL END,
                       error = $3
                   WHERE id = $1""", history_id, status, error))
            if result != "UPDATE 1":
                raise RuntimeError("Missing notification history row")
            return True
        except Exception:
            if attempt == 2:
                log.error("알림 이력 상태 갱신 실패: %s", history_id)
                return False
            await asyncio.sleep(0.5 * (attempt + 1))


async def _reserve_dispatch(database, device_id, notification_type, bypass_quiet=False):
    subscriptions = await _db_call(database.fetch(
        "SELECT endpoint, keys, quiet_start, quiet_end FROM push_subscriptions"))
    dispatch_id = uuid4()
    reservations = []
    for subscription in subscriptions:
        if not bypass_quiet and _quiet(datetime.now(config.TZ).hour,
                                       subscription["quiet_start"], subscription["quiet_end"]):
            continue
        history_id = await _db_call(database.fetchval(
            """INSERT INTO notification_history
                   (device_id, endpoint, notification_type, dispatch_id)
               VALUES ($1, $2, $3, $4) RETURNING id""",
            device_id, subscription["endpoint"], notification_type, dispatch_id))
        if history_id is None:
            raise RuntimeError("Missing notification history id")
        reservations.append((subscription, history_id))
    return reservations


async def send(
    title: str,
    body: str,
    url: str,
    bypass_quiet: bool = False,
    *,
    device_id: str,
    notification_type: str,
    _reservations=None,
) -> bool:
    """True means at least one push service accepted delivery, not device receipt."""
    database = db()
    try:
        if not config.VAPID_PRIVATE_KEY:
            return False
        if _reservations is None:
            try:
                async with database.acquire(timeout=DB_TIMEOUT) as connection, connection.transaction():
                    _reservations = await _reserve_dispatch(
                        connection, device_id, notification_type, bypass_quiet)
            except Exception:
                # Unrecorded sends bypass persistent limits. Do not send without a reservation.
                log.error("알림 이력 예약 실패로 발송 생략: %s", device_id)
                return False
        payload = json.dumps({"title": title, "body": body, "url": url})
        successes = 0
        for subscription, history_id in _reservations:

            try:
                keys = subscription["keys"]
                if isinstance(keys, str):
                    keys = json.loads(keys)
                await asyncio.wait_for(asyncio.to_thread(
                    webpush,
                    subscription_info={"endpoint": subscription["endpoint"], "keys": keys},
                    data=payload,
                    vapid_private_key=config.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": config.VAPID_SUBJECT},
                    timeout=5,
                ), timeout=PUSH_TIMEOUT)
            except asyncio.CancelledError:
                # The thread may still be transmitting; cancellation is not a failed send.
                await _update_history(database, history_id, "UNKNOWN", "발송 취소: 결과 확인 불가")
                raise
            except (asyncio.TimeoutError, RequestException):
                await _update_history(database, history_id, "UNKNOWN", "푸시 서비스 응답 없음 또는 네트워크 오류: 결과 확인 불가")
                log.warning("푸시 결과 불확실; 재발송하지 않음")
            except WebPushException as exc:
                response = exc.response
                code = response.status_code if response is not None else None
                # Raw exception text can contain subscription URLs or service response data.
                await _update_history(database, history_id, "FAILED",
                                      f"WebPushException: HTTP {code}" if code else "WebPushException: 응답 코드 없음")
                if code in (404, 410):
                    try:
                        await _db_call(database.execute(
                            "DELETE FROM push_subscriptions WHERE endpoint = $1", subscription["endpoint"]))
                    except Exception:
                        log.error("만료된 푸시 구독 삭제 실패")
            except Exception as exc:
                await _update_history(database, history_id, "FAILED", type(exc).__name__)
                log.warning("구독자별 푸시 처리 실패: %s", type(exc).__name__)
            else:
                successes += 1
                await _update_history(database, history_id, "SENT")
        return successes > 0
    except Exception:
        log.error("알림 시스템 처리 실패: %s", device_id)
        return False


async def on_state(device_id: str, old: str, new: str, at: datetime) -> None:
    """Only known risk increases send a push. STALE is not a risk level."""
    levels = {"SAFE": 0, "WATCH": 1, "ALERT": 2, "CONDENSING": 3}
    if old not in levels or new not in STATE_PUSH or levels[new] <= levels[old]:
        return
    try:
        title, body = STATE_PUSH[new]
        await send(title, body, f"/device/?id={device_id}",
                   bypass_quiet=new == "CONDENSING", device_id=device_id, notification_type="STATE")
    except Exception:
        log.error("상태 알림 처리 실패: %s", device_id)


async def on_forecast(device_id: str, state: str, fc: Forecast) -> None:
    """Persist 2/24h and 3h limits, serialized across API processes by PostgreSQL."""
    if state not in ("SAFE", "WATCH"):
        return
    lock = _forecast_locks[device_id]
    if lock.locked():
        return  # Do not queue old forecasts behind a slow push.
    if not config.VAPID_PRIVATE_KEY:
        return
    try:
        async with lock:
            # Commit quota reservations before HTTP. Do not hold a database connection
            # during slow pushes: ingestion must retain access to the shared pool.
            async with db().acquire(timeout=DB_TIMEOUT) as connection, connection.transaction():
                key = "notification-forecast:" + device_id
                locked = await _db_call(connection.fetchval(
                    "SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0))", key))
                if not locked:
                    return
                await reconcile_history(connection, device_id)
                history = await _db_call(connection.fetchrow(
                    """SELECT count(DISTINCT coalesce(dispatch_id::text, 'legacy:' || id::text)) AS sent_count,
                              coalesce(max(coalesce(sent_at, created_at)) > now() - interval '3 hours', false) AS too_recent
                       FROM notification_history
                       WHERE device_id = $1 AND notification_type = 'FORECAST'
                         AND status IN ('SENT', 'UNKNOWN', 'PENDING')
                         AND coalesce(sent_at, created_at) > now() - interval '24 hours'""", device_id))
                if history["sent_count"] >= 2 or history["too_recent"]:
                    return
                reservations = await _reserve_dispatch(connection, device_id, "FORECAST")
            what = "곰팡이 위험 구간" if fc.target < 100 else "결로"
            await send(
                "곧 습해집니다",
                f"약 {fc.hours_low:.1f}–{fc.hours_high:.1f}시간 뒤 {what} 진입 예상. 미리 환기하세요.",
                f"/device/?id={device_id}", device_id=device_id,
                notification_type="FORECAST", _reservations=reservations)
    except Exception:
        log.error("예측 알림 처리 실패: %s", device_id)
